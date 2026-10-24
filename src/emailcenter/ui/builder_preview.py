"""Local editor previews with no automatic links, remote resources or playback."""

from ..language import translate as _ui_tr, format_text as _ui_format
from . import localization as _ui_locale

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QSize, Qt, QUrl
from PySide6.QtGui import QImageReader, QPixmap, QTextDocument
from PySide6.QtWidgets import QLabel, QStackedWidget, QTextBrowser, QVBoxLayout, QWidget

from .dialogs import PdfWidget
from .pages import button, label


class LocalTextBrowser(QTextBrowser):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setOpenExternalLinks(False)
        self.setOpenLinks(False)

    def loadResource(self, resource_type, name):
        # HTML email content must not fetch trackers or arbitrary local files.
        if name.scheme() == 'cid':
            return getattr(self,'local_images',{}).get(name.path(),QByteArray())
        return QByteArray()


class LocalTextDocument(QTextDocument):
    def loadResource(self, resource_type, name):
        return QByteArray()


def image_thumbnail(content, size=QSize(320, 240)):
    """Decode bounded local pixels for both the editor and canvas."""
    buffer = QBuffer()
    buffer.setData(QByteArray(content))
    buffer.open(QIODevice.OpenModeFlag.ReadOnly)
    reader = QImageReader(buffer)
    reader.setAutoTransform(True)
    dimensions = reader.size()
    if not dimensions.isValid() or dimensions.width() * dimensions.height() > 80_000_000:
        return None
    reader.setScaledSize(dimensions.scaled(size, Qt.AspectRatioMode.KeepAspectRatio))
    result = reader.read()
    return None if result.isNull() else QPixmap.fromImage(result)


class MailRenderer(QWidget):
    """Finished mail view with plain headers and a locally rendered message."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.value = None
        self.setMinimumHeight(170)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        self.headers = label("", "muted")
        self.headers.setTextFormat(Qt.TextFormat.PlainText)
        self.headers.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.headers)
        self.body = BuilderPreview(self)
        self.body.caption.hide()
        self.text = self.body.text
        layout.addWidget(self.body, 1)
        self.attachments = label("", "muted")
        self.attachments.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.attachments)
        self.notice = label("", "muted")
        self.notice.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.notice)
        self.clear()

    def clear(self, message=None):
        message = _ui_tr('Alle Zeilen vorschauen, um die fertige Mail zu sehen.') if message is None else message
        self.value = None
        _ui_locale.clear_text(self.headers)
        _ui_locale.clear_text(self.attachments)
        _ui_locale.clear_text(self.notice)
        self.notice.hide()
        self.body.clear(message)

    def display(self, row):
        self.value = row
        sender = row.get("sender", "")
        _ui_locale.set_text(self.headers, _ui_format('{0}An: {1}\nBetreff: {2}', _ui_format('Von: {0}\n', sender) if sender else '', row.get('email', ''), row.get('subject', '')))
        self.text.local_images={}
        for cid,content in row.get('inline_content',{}).items():
            pixmap=image_thumbnail(content,QSize(1200,1200))
            if pixmap:self.text.local_images[cid]=pixmap.toImage()
        self.text.document().clear()
        self.body.display({"format": row.get("body_format", "plain"), "text": row.get("preview_body", row.get("body", ""))})
        files = row.get("attachments", [])
        _ui_locale.set_text(self.attachments, _ui_format('Anhänge: {0}', ' · '.join((file['filename'] for file in files)) if files else _ui_tr('Keine')))
        _ui_locale.set_text(self.notice, _ui_tr('Ungeprüfter Entwurf · Daten und Anhänge mit Zeilenvorschau prüfen.') if row.get('live') else _ui_format('Zeile nicht bereit: {0}', row['error']) if row.get('error') else '')
        self.notice.setVisible(bool(self.notice.text()))


class BuilderPreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(100)
        self.pixmap, self.pdf, self.player = None, None, None
        self.value = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.caption = label(_ui_tr('Vorschau'), 'muted')
        self.caption.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.caption)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)
        self.text = LocalTextBrowser()
        self.stack.addWidget(self.text)
        self.image = QLabel()
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setMinimumSize(80, 80)
        self.stack.addWidget(self.image)
        self.clear()

    def clear(self, message=None):
        message = _ui_tr('Baustein auswählen oder Vorschau laden.') if message is None else message
        if self.player:
            self.player.stop()
            self.player.setSource(QUrl())
        if self.pdf:
            self.pdf.dispose()
            self.stack.removeWidget(self.pdf)
            self.pdf.deleteLater()
            self.pdf = None
        self.value, self.pixmap = None, None
        _ui_locale.clear_text(self.image)
        _ui_locale.set_plain_text(self.text, message)
        self.stack.setCurrentWidget(self.text)

    def display(self, value):
        self.clear()
        self.value = value
        _ui_locale.set_text(self.caption, value.get('filename', _ui_tr('Lokale Vorschau')))
        kind = value.get("format", "text")
        if kind == "html":
            _ui_locale.set_html(self.text, value.get("text", ""))
        elif kind == "image":
            buffer = QBuffer(self)
            buffer.setData(QByteArray(value["content"]))
            buffer.open(QIODevice.OpenModeFlag.ReadOnly)
            reader = QImageReader(buffer)
            reader.setAutoTransform(True)
            size = reader.size()
            if size.isValid() and size.width() * size.height() <= 80_000_000:
                reader.setScaledSize(size.scaled(QSize(1280, 1280), Qt.AspectRatioMode.KeepAspectRatio))
                image = reader.read()
                if not image.isNull():
                    self.pixmap = QPixmap.fromImage(image)
                    self.stack.setCurrentWidget(self.image)
                    self.scale_image()
                else:
                    _ui_locale.set_plain_text(self.text, _ui_format('Bild konnte nicht gelesen werden: {0}', reader.errorString()))
            else:
                _ui_locale.set_plain_text(self.text, _ui_tr('Bildgröße ungültig oder größer als 80 Megapixel.'))
            buffer.close()
            buffer.deleteLater()
        elif kind == "pdf":
            self.pdf = PdfWidget(value["content"], self)
            self.stack.addWidget(self.pdf)
            self.stack.setCurrentWidget(self.pdf)
        elif kind == "video":
            if self.player is None:
                from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
                from PySide6.QtMultimediaWidgets import QVideoWidget
                self.video_pane = QWidget()
                layout = QVBoxLayout(self.video_pane)
                layout.setContentsMargins(0, 0, 0, 0)
                video = QVideoWidget()
                video.setMinimumSize(80, 100)
                layout.addWidget(video, 1)
                self.play = button(_ui_tr('Abspielen / Pause'), self.toggle_playback)
                layout.addWidget(self.play)
                self.video_notice = label(_ui_tr('Lokales Video · Wiedergabe ausdrücklich starten.'), 'muted')
                layout.addWidget(self.video_notice)
                self.player = QMediaPlayer(self)
                self.audio = QAudioOutput(self)
                self.audio.setVolume(.25)
                self.player.setAudioOutput(self.audio)
                self.player.setVideoOutput(video)
                self.player.errorOccurred.connect(lambda *args: _ui_locale.set_text(self.video_notice, _ui_format('Video nicht lesbar: {0}', self.player.errorString())))
                self.stack.addWidget(self.video_pane)
            _ui_locale.set_text(self.video_notice, _ui_tr('Lokales Video · Wiedergabe ausdrücklich starten.'))
            self.player.setSource(QUrl.fromLocalFile(value["path"]))
            self.stack.setCurrentWidget(self.video_pane)
        else:
            _ui_locale.set_plain_text(self.text, value.get('text', _ui_tr('Keine Vorschau verfügbar.')))

    def toggle_playback(self):
        from PySide6.QtMultimedia import QMediaPlayer
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def scale_image(self):
        if self.pixmap:
            self.image.setPixmap(self.pixmap.scaled(self.image.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.scale_image()

    def hideEvent(self, event):
        if self.player:
            self.player.pause()
        super().hideEvent(event)
