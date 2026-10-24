"""Visual, typed drag/drop graph editor with shared rows and reviewed draft output."""

from ..language import translate as _ui_tr, format_text as _ui_format
from . import localization as _ui_locale

import json

from copy import deepcopy
from collections import OrderedDict
import html
from pathlib import Path
from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from PySide6.QtCore import Qt, Signal, QPointF, QRectF, QMimeData, QTimer, QDateTime, QTime, QSize
from PySide6.QtGui import QColor, QDrag, QPainter, QPainterPath, QPen, QPalette, QKeySequence
from PySide6.QtWidgets import (
    QInputDialog,QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout, QGraphicsEllipseItem,
    QGraphicsItem, QGraphicsObject, QGraphicsPathItem, QGraphicsScene, QGraphicsView, QGridLayout, QHBoxLayout,
    QHeaderView, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QScrollArea, QSplitter,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QMenu, QTabWidget, QDateTimeEdit, QSpinBox, QTimeEdit)

from ..bulk_sources import SOURCE_FIELDS, FIELD_NAME
from ..email_builder import NODE_TYPES, TEXT_KINDS, FILE_KINDS, EXTENSIONS, CONDITION_OPERATORS, node, starter_graph, validate_graph, body_part, TOKEN
from .pages import button, label
from .builder_preview import BuilderPreview, MailRenderer, LocalTextDocument, image_thumbnail
from ..builder_workspace import arrange_graph
from ..mail_bulk import digest
from ..shortcuts import normalize_canvas_shortcut
from ..word_replace import WordRuleError, validate_rules
from ..builder_values import DATE_FORMATS, TIME_FORMATS


PORT_COLORS = {"fields": "#9b68d9", "recipient": "#e19a35", "text": "#368dc5", "subject": "#e1b64a", "html": "#ad6dda", "docx": "#568cdd", "pdf": "#cf6674", "file": "#45a58d", "image": "#45a58d", "video": "#45a58d"}
MIME = "application/x-emailcenter-builder-node"


class Palette(QListWidget):
    def startDrag(self, supported):
        if self.currentItem():
            mime = QMimeData()
            mime.setData(MIME, self.currentItem().data(Qt.ItemDataRole.UserRole).encode())
            drag = QDrag(self)
            drag.setMimeData(mime)
            drag.exec(Qt.DropAction.CopyAction)


class Port(QGraphicsEllipseItem):
    def __init__(self, parent, name, output, index, kind):
        super().__init__(-7, -7, 14, 14, parent)
        self.name, self.output = name, output
        self.setPos(248 if output else 0, 58 + index * 29)
        self.setBrush(QColor(PORT_COLORS[kind]))
        self.setPen(QPen(QColor("#ffffff"), 1))
        self.setZValue(3)
        self.setToolTip(("Ausgang " if output else "Eingang ") + name + " · " + kind)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def mousePressEvent(self, event):
        scene = self.scene()
        if self.output:
            scene.pending = self
            _ui_locale.set_text(scene.page.status, _ui_tr('Mit passendem Eingang verbinden: ziehen oder Eingang anklicken.'))
        elif scene.pending:
            scene.page.connect_ports(scene.pending, self)
            scene.pending = None
        event.accept()

    def mouseMoveEvent(self, event):
        if self.output and self.scene().pending:
            self.scene().draw_connection(event.scenePos())
        event.accept()

    def mouseReleaseEvent(self, event):
        self.scene().clear_connection()
        if self.output and self.scene().pending:
            target = next((i for i in self.scene().items(event.scenePos()) if isinstance(i, Port) and not i.output), None)
            if target:
                self.scene().page.connect_ports(self, target)
                self.scene().pending = None
        event.accept()


class NodeCard(QGraphicsObject):
    def __init__(self, item, page):
        super().__init__()
        self.value, self.page = item, page
        self.preview_value, self.preview_document, self.preview_pixmap = None, None, None
        spec = NODE_TYPES[item["kind"]]
        self.height = max(115, 88 + max(len(spec["inputs"]), len(spec["outputs"])) * 29)
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setPos(item["x"], item["y"])
        self.ports = {}
        for index, (name, (kinds, _, _)) in enumerate(spec["inputs"].items()):
            self.ports[(name, False)] = Port(self, name, False, index, kinds[0])
        for index, (name, kind) in enumerate(spec["outputs"].items()):
            self.ports[(name, True)] = Port(self, name, True, index, kind)

    def boundingRect(self):
        return QRectF(-8, -2, 264, self.height + 4)

    def paint(self, painter, option, widget=None):
        palette = QApplication.palette()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(palette.color(QPalette.ColorRole.Base))
        painter.setPen(QPen(palette.color(QPalette.ColorRole.Highlight) if self.isSelected() else palette.color(QPalette.ColorRole.Mid), 2))
        painter.drawRoundedRect(QRectF(0, 0, 248, self.height), 9, 9)
        painter.setPen(palette.color(QPalette.ColorRole.Text))
        spec = NODE_TYPES[self.value["kind"]]
        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(QRectF(14, 8, 220, 28), str(_ui_tr(spec['title'])))
        font.setBold(False)
        font.setPointSize(max(8, font.pointSize() - 1))
        painter.setFont(font)
        for index, name in enumerate(spec["inputs"]):
            painter.drawText(QRectF(13, 47 + index * 29, 120, 22), Qt.AlignmentFlag.AlignLeft, name)
        for index, name in enumerate(spec["outputs"]):
            painter.drawText(QRectF(125, 47 + index * 29, 110, 22), Qt.AlignmentFlag.AlignRight, name)
        config = self.value["config"]
        caption = _ui_format("{0} Datenzeilen", len(config["sources"])) if self.value["kind"] == "data" else config.get("text", config.get("path", config.get("body_format", "")))
        if self.value["kind"] == "replace":
            caption = _ui_format("{0} Ersetzungsregeln", len(config["rules"]))
        elif self.value['kind'] == 'convert':
            caption = config.get('filename', '') or _ui_tr('PDF-Name aus DOCX')
        if self.preview_value:
            caption = self.preview_value.get("subject", self.preview_value.get("text", self.preview_value.get("filename", caption)))
            if self.preview_document:
                caption = self.preview_document.toPlainText().splitlines()[0] if self.preview_document.toPlainText() else caption
            if self.value["kind"] == "email":
                caption = self.preview_value.get("subject", "")
        preview_rect = QRectF(123, 47 if self.value["kind"] == "email" else 79, 112, max(16, self.height - (82 if self.value["kind"] == "email" else 110)))
        if self.preview_pixmap:
            size = self.preview_pixmap.size().scaled(preview_rect.size().toSize(), Qt.AspectRatioMode.KeepAspectRatio)
            target = QRectF(preview_rect.x(), preview_rect.y(), size.width(), size.height())
            painter.drawPixmap(target, self.preview_pixmap, QRectF(self.preview_pixmap.rect()))
        elif self.preview_document:
            painter.save()
            painter.setClipRect(preview_rect)
            painter.translate(preview_rect.topLeft())
            scale = preview_rect.width() / self.preview_document.textWidth()
            painter.scale(scale, scale)
            self.preview_document.drawContents(painter, QRectF(0, 0, self.preview_document.textWidth(), preview_rect.height() / scale))
            painter.restore()
        painter.drawText(QRectF(14, self.height - 24, 220, 20), str(caption).replace("\n", " ")[:32])

    def set_preview(self, value=None, pixmap=None):
        self.preview_value, self.preview_pixmap = value, pixmap
        self.preview_document = None
        if value:
            kind = value.get("format", "text")
            text = value.get("text", "")
            if kind == "mail":
                text = '<b>' + html.escape(value.get("subject", "")) + '</b><br>' + html.escape(value.get("email", "")) + '<hr>'
                body = value.get("preview_body", "")[:12000]
                text += body if value.get("body_format") == "html" else html.escape(body).replace("\n", "<br>")
            if text and kind in ("mail", "html"):
                document = LocalTextDocument()
                document.setDefaultStyleSheet("body, p { color: " + QApplication.palette().color(QPalette.ColorRole.Text).name() + "; }")
                document.setHtml(text[:16000])
                document.setTextWidth(260)
                self.preview_document = document
            caption = value.get("subject", value.get("text", value.get("filename", "")))
            _ui_locale.set_tooltip(self, _ui_format('<pre>{0}</pre>', html.escape(str(caption)[:1000])))
        else:
            self.setToolTip("")
        self.update()

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene() and self.page.preferences.builder_snap:
            return QPointF(round(value.x() / 20) * 20, round(value.y() / 20) * 20)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self.scene():
            self.scene().redraw_edges()
        return super().itemChange(change, value)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self.page.capture_positions()


class GraphScene(QGraphicsScene):
    def __init__(self, page):
        super().__init__(page)
        self.page, self.cards, self.lines, self.pending = page, {}, [], None
        self.setSceneRect(-1000, -1000, 5000, 4000)

    def rebuild(self, graph, selected=None):
        if hasattr(self.page, "view"):
            self.page.view.keyboard_port = None
        self.pending = None
        self.clear_connection()
        self.clear()
        self.cards, self.lines = {}, []
        for value in graph["nodes"]:
            card = NodeCard(value, self.page)
            self.addItem(card)
            self.cards[value["id"]] = card
            if value["id"] == selected:
                card.setSelected(True)
        self.redraw_edges()
        bounds = self.itemsBoundingRect().adjusted(-300, -300, 300, 300)
        self.setSceneRect(QRectF(-1000, -1000, 5000, 4000).united(bounds))
        self.page.refresh_node_jump()

    def redraw_edges(self):
        if len(self.lines) != len(self.page.graph["edges"]):
            for line in self.lines:
                self.removeItem(line)
            self.lines = []
        for index, edge in enumerate(self.page.graph["edges"]):
            a = self.cards.get(edge["from"])
            b = self.cards.get(edge["to"])
            if not a or not b:
                continue
            start, end = a.ports[(edge["output"], True)].scenePos(), b.ports[(edge["input"], False)].scenePos()
            path = QPainterPath(start)
            offset = max(70, abs(end.x() - start.x()) / 2)
            path.cubicTo(start + QPointF(offset, 0), end - QPointF(offset, 0), end)
            existing = index < len(self.lines)
            line = self.lines[index] if existing else QGraphicsPathItem()
            line.setPath(path)
            line.setPen(QPen(QColor(PORT_COLORS[NODE_TYPES[a.value["kind"]]["outputs"][edge["output"]]]), 4))
            line.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
            line.setData(0, index)
            line.setZValue(-1)
            if not existing:
                self.addItem(line)
                self.lines.append(line)

    def draw_connection(self, end):
        self.clear_connection()
        if self.pending:
            start = self.pending.scenePos()
            path = QPainterPath(start)
            path.cubicTo(start + QPointF(90, 0), end - QPointF(90, 0), end)
            self.connection = self.addPath(path, QPen(QApplication.palette().color(QPalette.ColorRole.Highlight), 3, Qt.PenStyle.DashLine))
            self.connection.setZValue(-1)

    def clear_connection(self):
        if getattr(self, "connection", None):
            self.removeItem(self.connection)
            self.connection = None

    def drawBackground(self, painter, rect):
        painter.fillRect(rect, QApplication.palette().color(QPalette.ColorRole.Window))
        if self.page.preferences.builder_grid:
            painter.setPen(QPen(QApplication.palette().color(QPalette.ColorRole.Mid), 0))
            for x in range(int(rect.left()) // 20 * 20, int(rect.right()) + 20, 20):
                for y in range(int(rect.top()) // 20 * 20, int(rect.bottom()) + 20, 20):
                    painter.drawPoint(QPointF(x, y))


class GraphView(QGraphicsView):
    def __init__(self, scene, page):
        super().__init__(scene)
        self.page = page
        self.pan_position = None
        self.keyboard_port = None
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        _ui_locale.set_accessible_name(self, _ui_tr('E-Mail-Builder Zeichenfläche'))
        self.setAcceptDrops(True)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setMinimumSize(250, 230)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self.pan_position = event.position()
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.pan_position is not None:
            delta = event.position() - self.pan_position
            self.pan_position = event.position()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - round(delta.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - round(delta.y()))
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self.pan_position = None
            self.viewport().unsetCursor()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(MIME) or event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        self.dragEnterEvent(event)

    def dropEvent(self, event):
        if self.page.busy:
            return
        point = self.mapToScene(event.position().toPoint())
        if event.mimeData().hasFormat(MIME):
            self.page.add_node(bytes(event.mimeData().data(MIME)).decode(), point.x(), point.y())
        elif event.mimeData().hasUrls():
            self.page.drop_files([url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()], point)
        event.acceptProposedAction()

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.page.zoom(1.15 if event.angleDelta().y() > 0 else 1 / 1.15)
            event.accept()
        else:
            super().wheelEvent(event)

    def keyPressEvent(self, event):
        if self.page.busy:
            event.accept()
            return
        sequence = QKeySequence(event.keyCombination()).toString(QKeySequence.SequenceFormat.PortableText)
        try:
            sequence = normalize_canvas_shortcut(sequence)
        except ValueError:
            super().keyPressEvent(event)
            return
        action = next((key for key, value in self.page.preferences.canvas_shortcuts.items() if value and value == sequence), None)
        callbacks = {"next_node": lambda: self.cycle_node(1), "previous_node": lambda: self.cycle_node(-1),
                     "next_port": lambda: self.cycle_port(1), "previous_port": lambda: self.cycle_port(-1),
                     "connect": self.activate_port, "cancel": self.cancel_connection, "next_edge": self.cycle_edge,
                     "delete": self.page.delete_selected, "duplicate": self.page.duplicate_selected,
                     "undo": self.page.undo, "redo": self.page.redo, "zoom_in": lambda: self.page.zoom(1.15),
                     "zoom_out": lambda: self.page.zoom(1/1.15), "fit": self.page.fit}
        if action:
            if not event.isAutoRepeat() or action not in ("connect", "delete", "duplicate"):
                callbacks[action]()
            event.accept()
        else:
            super().keyPressEvent(event)

    def announce(self, text):
        _ui_locale.set_text(self.page.status, text)
        _ui_locale.set_accessible_description(self, text)

    def highlight_port(self, port=None):
        for card in self.scene().cards.values():
            for value in card.ports.values():
                value.setPen(QPen(QApplication.palette().color(QPalette.ColorRole.Highlight) if value is port else QColor("#ffffff"), 4 if value is port else 1))
        self.keyboard_port = (port.parentItem().value["id"], (port.name, port.output)) if port else None
        if port:
            self.ensureVisible(port.sceneBoundingRect(), 30, 30)
            self.announce(_ui_format('{0} · Aktivieren verbindet einen Ausgang mit einem passenden Eingang.', port.toolTip()))

    def cycle_node(self, direction):
        identifiers = list(self.scene().cards)
        if not identifiers:
            return
        current = self.page.selected_id
        index = (identifiers.index(current) + direction) % len(identifiers) if current in identifiers else (0 if direction > 0 else -1)
        self.highlight_port()
        self.page._painting = True
        self.scene().clearSelection()
        card = self.scene().cards[identifiers[index]]
        card.setSelected(True)
        self.page._painting = False
        self.page.selection_changed()
        self.ensureVisible(card.sceneBoundingRect(), 30, 30)
        self.announce(_ui_format('{0} gewählt. Nächsten Stecker auswählen.', NODE_TYPES[card.value['kind']]['title']))

    def cycle_port(self, direction):
        card = self.scene().cards.get(self.page.selected_id)
        if card is None:
            self.cycle_node(direction)
            card = self.scene().cards.get(self.page.selected_id)
        if not card or not card.ports:
            return
        keys = list(card.ports)
        current = self.keyboard_port[1] if self.keyboard_port and self.keyboard_port[0] == card.value["id"] else None
        index = (keys.index(current) + direction) % len(keys) if current in keys else (0 if direction > 0 else -1)
        self.highlight_port(card.ports[keys[index]])

    def activate_port(self):
        if not self.keyboard_port:
            self.announce(_ui_tr('Zuerst einen Baustein und einen Stecker wählen.'))
            return
        identifier, key = self.keyboard_port
        card = self.scene().cards.get(identifier)
        if not card or key not in card.ports:
            return
        port = card.ports[key]
        if port.output:
            self.scene().pending = port
            self.announce(_ui_format('Ausgang {0} gewählt. Zielbaustein und Eingang wählen, dann erneut aktivieren.', port.name))
        elif self.scene().pending:
            source = self.scene().pending
            self.scene().pending = None
            self.scene().clear_connection()
            self.page.connect_ports(source, port)
            self.announce(_ui_tr('Verbindung wird geprüft. Rückgängig ist verfügbar.'))
        else:
            self.announce(_ui_tr('Zuerst einen Ausgang aktivieren, anschließend diesen Eingang.'))

    def cancel_connection(self):
        self.highlight_port()
        self.scene().clear_connection()
        self.scene().pending = None
        self.scene().clearSelection()
        self.announce(_ui_tr('Verbindung und Auswahl aufgehoben.'))

    def cycle_edge(self):
        lines = self.scene().lines
        if not lines:
            self.announce(_ui_tr('Keine Verbindungen vorhanden.'))
            return
        selected = next((index for index, line in enumerate(lines) if line.isSelected()), -1)
        self.highlight_port()
        self.scene().clearSelection()
        line = lines[(selected + 1) % len(lines)]
        line.setSelected(True)
        self.ensureVisible(line.sceneBoundingRect(), 30, 30)
        self.announce(_ui_format('Verbindung {0} gewählt; Löschen entfernt sie.', str((selected + 1) % len(lines) + 1)))


class EmailBuilderPage(QWidget):
    panel_preferences_requested = Signal(object)
    operation_requested = Signal(str, object)
    source_requested = Signal(str)
    cancel_requested = Signal()
    delivery_requested = Signal(str)
    settings_requested = Signal()
    checkpoint_requested = Signal(str, object)
    asset_autoload_requested = Signal(str, object)

    def __init__(self, preferences):
        super().__init__()
        self.preferences, self.busy, self.data = preferences, False, {}
        self.graph, self.history, self.future = starter_graph(self.preferences.builder_default_blocks), [], []
        self.version_id, self.builder_id, self.preview, self.last_batch = None, None, None, None
        self.project_path = None
        self.saved_graph, self.selected_id = None, None
        self._painting = False
        self._asset_request_id = None
        self._first_fit = True
        self.inline_preview = None
        self.inline_mail = None
        self._preview_epoch = 0
        self._asset_cache, self._asset_queue, self._asset_errors = OrderedDict(), [], {}
        self._auto_asset_inflight = None
        self.autoload_timer = QTimer(self)
        self.autoload_timer.setSingleShot(True)
        self.autoload_timer.timeout.connect(self.autoload_next)
        self.project_id = None
        self._workspace_loaded, self._restoring, self._autosave_blocked = False, False, False
        self._workspace_revision, self._autosave_hash = 0, None
        self._checkpoint_force = False
        self.autosave_timer = QTimer(self)
        self.autosave_timer.setSingleShot(True)
        self.autosave_timer.timeout.connect(self.request_checkpoint)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        body = QWidget()
        self.scroll.setWidget(body)
        outer.addWidget(self.scroll, 1)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.addWidget(label(_ui_tr('E-Mail-Builder'), 'pageTitle'))
        layout.addWidget(label(_ui_tr('Bausteine ziehen · Ausgang mit Eingang verbinden · Daten und Ergebnisse prüfen · lokale Entwürfe erstellen'), 'muted'))
        bar = QGridLayout()
        self.name = QLineEdit("Mein E-Mail-Ablauf")
        self.name.setMaxLength(200)
        self.saved = QComboBox()
        self.versions = QComboBox()
        self.load_button = button(_ui_tr('Öffnen'), self.load_selected)
        self.new_button = button(_ui_tr('Neu'), self.new_graph)
        self.save_button = button(_ui_tr('Version speichern'), self.save)
        self.copy_button = button(_ui_tr('Als Kopie speichern'), lambda: self.save(copy=True))
        self.dirty = label(_ui_tr('Noch keine gespeicherte Version'), 'muted')
        bar.addWidget(self.name, 0, 0, 1, 2)
        bar.addWidget(self.new_button, 0, 2)
        bar.addWidget(self.save_button, 0, 3)
        bar.addWidget(self.copy_button, 0, 4)
        bar.addWidget(self.saved, 1, 0, 1, 2)
        bar.addWidget(self.versions, 1, 2, 1, 2)
        bar.addWidget(self.load_button, 1, 4)
        layout.addLayout(bar)
        layout.addWidget(self.dirty)
        self.tools = QGridLayout()
        self.add_button = button(_ui_tr('Baustein +'))
        menu = QMenu(self.add_button)
        for kind, spec in NODE_TYPES.items():
            action = _ui_locale.add_action(menu, _ui_tr(spec['title']))
            action.triggered.connect(lambda checked=False, kind=kind: self.add_node(kind))
        self.add_button.setMenu(menu)
        self.transfer_button = button(_ui_tr('Graph / Optionen …'))
        transfer = QMenu(self.transfer_button)
        _ui_locale.add_action(transfer, _ui_tr('Mitgelieferte Builder-Vorlagen …'), self.use_builtin_graph)
        _ui_locale.add_action(transfer, _ui_tr('Graphvorlage exportieren …'), self.export_graph)
        _ui_locale.add_action(transfer, _ui_tr('Graphvorlage importieren …'), self.import_graph)
        _ui_locale.add_action(transfer, _ui_tr('Auswahl als Bausteingruppe speichern …'), self.save_node_group)
        _ui_locale.add_action(transfer, _ui_tr('Bausteingruppe einfügen …'), lambda: self.request_node_groups('insert'))
        _ui_locale.add_action(transfer, _ui_tr('Bausteingruppe löschen …'), lambda: self.request_node_groups('delete'))
        transfer.addSeparator()
        _ui_locale.add_action(transfer, _ui_tr('Builder-Einstellungen'), self.settings_requested.emit)
        transfer.addSeparator()
        _ui_locale.add_action(transfer, _ui_tr('Palette ein / aus'), lambda: self.toggle_panel('builder_show_palette'))
        _ui_locale.add_action(transfer, _ui_tr('Eigenschaften ein / aus'), lambda: self.toggle_panel('builder_show_inspector'))
        _ui_locale.add_action(transfer, _ui_tr('Werkzeugleiste kompakt / ausführlich'), lambda: self.toggle_panel('builder_compact_tools'))
        _ui_locale.add_action(transfer, _ui_tr('Aktuelle Panelbreiten als Vorgabe speichern'), self.save_panel_sizes)
        self.transfer_button.setMenu(transfer)
        self.undo_button = button(_ui_tr('Rückgängig'), self.undo)
        self.redo_button = button(_ui_tr('Wiederholen'), self.redo)
        self.tool_buttons = (self.add_button, self.undo_button, self.redo_button, button(_ui_tr('Duplizieren'), self.duplicate_selected), button(_ui_tr('Löschen'), self.delete_selected),
                        button("−", lambda: self.zoom(1 / 1.15)), button("+", lambda: self.zoom(1.15)), button(_ui_tr('Einpassen'), self.fit), button(_ui_tr('Anordnen'), self.arrange), self.transfer_button)
        # This page may never be shown: resizeEvent must not establish ownership.
        # Menus follow their buttons when the hidden page/window is destroyed.
        for control in self.tool_buttons:
            control.setParent(self)
        layout.addLayout(self.tools)
        self.tabs = QSplitter(Qt.Orientation.Horizontal)
        self.palette = Palette()
        self.palette.setDragEnabled(True)
        self.palette.setMinimumWidth(150)
        self.palette.setMaximumWidth(190)
        for kind, spec in NODE_TYPES.items():
            item = _ui_locale.item(QListWidgetItem, _ui_tr(spec['title']))
            item.setData(Qt.ItemDataRole.UserRole, kind)
            item.setToolTip(str(_ui_tr(spec['title'])))
            self.palette.addItem(item)
        self.palette.setWordWrap(True)
        self.palette.itemDoubleClicked.connect(lambda item: self.add_node(item.data(Qt.ItemDataRole.UserRole)))
        self.palette_pane = QWidget()
        palette_layout = QVBoxLayout(self.palette_pane)
        palette_layout.setContentsMargins(0, 0, 0, 0)
        self.palette_search = QLineEdit()
        _ui_locale.set_placeholder(self.palette_search, _ui_tr('Bausteine suchen …'))
        self.palette_search.textChanged.connect(self.filter_palette)
        palette_layout.addWidget(self.palette_search)
        palette_layout.addWidget(self.palette, 1)
        self.palette_pane.setMaximumWidth(200)
        self.tabs.addWidget(self.palette_pane)
        self.scene = GraphScene(self)
        self.view = GraphView(self.scene, self)
        self.tabs.addWidget(self.view)
        self.view.horizontalScrollBar().valueChanged.connect(self.schedule_checkpoint)
        self.view.verticalScrollBar().valueChanged.connect(self.schedule_checkpoint)
        self.properties = QScrollArea()
        self.properties.setWidgetResizable(True)
        self.properties.setMinimumWidth(180)
        self.inspector = QTabWidget()
        self.inspector.setStyleSheet("QTabBar::tab { padding: 7px 6px; }")
        _ui_locale.add_tab(self.inspector, self.properties, _ui_tr('Baustein'))
        preview_pane = QWidget()
        preview_layout = QVBoxLayout(preview_pane)
        _ui_locale.add_tab(self.inspector, preview_pane, _ui_tr('Mail'))
        self.node_preview = BuilderPreview()
        _ui_locale.add_tab(self.inspector, self.node_preview, _ui_tr('Medien'))
        planning = QWidget()
        plan_layout = QFormLayout(planning)
        plan_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.delivery_mode = QComboBox()
        _ui_locale.add_item(self.delivery_mode, _ui_tr('Nur lokale Entwürfe'), 'drafts')
        _ui_locale.add_item(self.delivery_mode, _ui_tr('Sofortversand vorbereiten'), 'now')
        _ui_locale.add_item(self.delivery_mode, _ui_tr('Versandtermin planen'), 'scheduled')
        _ui_locale.add_row(plan_layout, _ui_tr('Ausgabe'), self.delivery_mode)
        self.schedule = QDateTimeEdit(datetime.now(ZoneInfo(preferences.timezone_id)).replace(tzinfo=None) + timedelta(hours=1))
        self.schedule.setDisplayFormat("dd.MM.yyyy HH:mm")
        self.schedule.setCalendarPopup(True)
        self.schedule.setEnabled(False)
        _ui_locale.add_row(plan_layout, _ui_tr('Start'), self.schedule)
        self.timezone = QComboBox()
        self.timezone.setEditable(True)
        self.timezone.addItems(list(dict.fromkeys([preferences.timezone_id, "Europe/Berlin", "UTC"])))
        _ui_locale.add_row(plan_layout, _ui_tr('Zeitzone'), self.timezone)
        self.interval = QSpinBox()
        self.interval.setRange(1, 3600)
        self.interval.setValue(2)
        _ui_locale.set_suffix(self.interval, _ui_tr(' Sekunden'))
        _ui_locale.add_row(plan_layout, _ui_tr('Abstand'), self.interval)
        self.daily_budget = QSpinBox()
        self.daily_budget.setRange(1, 10000)
        self.daily_budget.setValue(100)
        _ui_locale.add_row(plan_layout, _ui_tr('Versandversuche / Konto / Tag'), self.daily_budget)
        self.window_start, self.window_end = QTimeEdit(), QTimeEdit()
        for control in (self.window_start, self.window_end):
            control.setDisplayFormat("HH:mm")
            control.timeChanged.connect(self.plan_changed)
        window = QHBoxLayout()
        window.addWidget(self.window_start)
        window.addWidget(label(_ui_tr('bis')))
        window.addWidget(self.window_end)
        _ui_locale.add_row(plan_layout, _ui_tr('Versandfenster (gleich = ganztägig)'), window)
        self.daily_budget.valueChanged.connect(self.plan_changed)
        plan_layout.addRow(label(_ui_tr('Eine Nachricht je Datenzeile. Planung und Entwürfe werden gemeinsam gespeichert. Versandkopien danach prüfen, freigeben und starten.'), 'muted'))
        self.checkpoint_label = label(_ui_tr('Arbeitsstand noch nicht gesichert'), 'muted')
        plan_layout.addRow(self.checkpoint_label)
        plan_layout.addRow(button(_ui_tr('Arbeitsstand jetzt sichern'), lambda: self.request_checkpoint(force=True)))
        plan_layout.addRow(button(_ui_tr('Gesicherten Arbeitsstand laden'), self.reload_workspace))
        plan_scroll = QScrollArea()
        plan_scroll.setWidgetResizable(True)
        plan_scroll.setWidget(planning)
        _ui_locale.add_tab(self.inspector, plan_scroll, _ui_tr('Plan'))
        for index, hint in enumerate(("Eigenschaften und Live-Textvorschau", "Nachricht je Empfänger prüfen", "Bilder, Videos, PDF und Dokumenttext", "Bulk-Aufträge sofort vorbereiten oder planen")):
            self.inspector.setTabToolTip(index, hint)
        self.inspector_pane = QWidget()
        inspector_layout = QVBoxLayout(self.inspector_pane)
        inspector_layout.setContentsMargins(0, 0, 0, 0)
        self.node_jump = QComboBox()
        self.node_jump.setMinimumWidth(180)
        self.node_jump.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.node_jump.currentIndexChanged.connect(self.jump_to_node)
        inspector_layout.addWidget(self.node_jump)
        inspector_layout.addWidget(self.inspector, 1)
        self.tabs.addWidget(self.inspector_pane)
        self.tabs.setSizes([160, 650, 260])
        self.canvas_container = QWidget()
        canvas_layout = QVBoxLayout(self.canvas_container)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        canvas_layout.addWidget(self.tabs)
        layout.addWidget(self.canvas_container, 3)
        self.recipient = QComboBox()
        self.recipient.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        _ui_locale.set_tooltip(self.recipient, _ui_tr('Vorschauzeile für Mail und alle Bausteine'))
        self.recipient.currentIndexChanged.connect(self.show_row)
        inspector_layout.insertWidget(1, self.recipient)
        self.result = QPlainTextEdit()
        self.result.setReadOnly(True)
        self.result.setMinimumHeight(80)
        preview_layout.addWidget(self.result, 1)
        self.mail_preview = MailRenderer()
        self.mail_preview.hide()
        preview_layout.addWidget(self.mail_preview, 1)
        self.rendered = _ui_locale.widget(QCheckBox, _ui_tr('Nachricht gerendert anzeigen'))
        self.rendered.setChecked(True)
        self.rendered.toggled.connect(self.show_row)
        preview_layout.addWidget(self.rendered)
        self.footer = QWidget()
        footer = QVBoxLayout(self.footer)
        footer.setContentsMargins(16, 4, 16, 12)
        self.account = QComboBox()
        self.signature = QComboBox()
        self.delivery_options = QHBoxLayout()
        self.delivery_options.addWidget(label(_ui_tr('Konto')))
        self.delivery_options.addWidget(self.account, 1)
        self.delivery_options.addWidget(label(_ui_tr('Signatur')))
        self.delivery_options.addWidget(self.signature, 1)
        footer.addLayout(self.delivery_options)
        self.confirm = _ui_locale.widget(QCheckBox, _ui_tr('Alle Zeilen, Texte und Anhänge geprüft'))
        footer.addWidget(self.confirm)
        self.status = label(_ui_tr('Excel-/Datenliste im Datenbaustein auswählen. Vorschau und Speicherung arbeiten lokal.'), 'muted')
        footer.addWidget(self.status)
        self.workflow_hint = label('', 'muted')
        footer.addWidget(self.workflow_hint)
        self.actions_grid = QGridLayout()
        self.preview_button = button(_ui_tr('Alle Zeilen vorschauen'), self.request_preview)
        self.create_button = button(_ui_tr('Lokale Entwurfsgruppe erstellen'), self.create, primary=True)
        self.cancel_button = button(_ui_tr('Vorgang abbrechen'), self.cancel_requested.emit)
        self.delivery_button = button(_ui_tr('Gruppe prüfen / senden'), lambda: self.delivery_requested.emit(self.last_batch))
        self.footer_buttons = (self.preview_button, self.create_button, self.cancel_button, self.delivery_button)
        for control in self.footer_buttons:
            control.setParent(self.footer)
        footer.addLayout(self.actions_grid)
        outer.addWidget(self.footer)
        self.confirm.toggled.connect(self.update_buttons)
        self.account.currentIndexChanged.connect(self.invalidate)
        self.signature.currentIndexChanged.connect(self.invalidate)
        self.name.textChanged.connect(self.update_buttons)
        self.name.textChanged.connect(self.schedule_checkpoint)
        self.delivery_mode.currentIndexChanged.connect(self.plan_changed)
        self.schedule.dateTimeChanged.connect(self.plan_changed)
        self.timezone.currentTextChanged.connect(self.plan_changed)
        self.interval.valueChanged.connect(self.plan_changed)
        self.scene.selectionChanged.connect(self.selection_changed)
        self.scene.rebuild(self.graph)
        self.view.scale(preferences.builder_zoom / 100, preferences.builder_zoom / 100)
        self.apply_settings(preferences)
        from .mail_defaults import apply_plan_defaults
        apply_plan_defaults(self)
        self.update_buttons()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "footer_buttons"):
            self.canvas_container.setFixedHeight(max(230, min(520, self.height() - 485)))
            self.palette_pane.setVisible(self.width() >= 900 and self.preferences.builder_show_palette)
            columns = 10 if self.width() >= 1100 else 5 if self.width() >= 950 else 3
            for i, control in enumerate(self.tool_buttons):
                self.tools.addWidget(control, i // columns, i % columns)
            for i, control in enumerate(self.footer_buttons):
                self.actions_grid.addWidget(control, i // (4 if self.width() >= 950 else 2), i % (4 if self.width() >= 950 else 2))

    def reset(self, project_path=None, project_id=None):
        self._source_fields = []
        self.project_path = project_path
        self._load_workspace_explicitly = False
        self.autosave_timer.stop()
        self._workspace_loaded, self._autosave_blocked = False, False
        self.project_id = project_id
        self._workspace_revision, self._autosave_hash = 0, None
        self._checkpoint_force = False
        self.data = {}
        self._first_fit = True
        self.last_batch = None
        self.delivery_mode.setCurrentIndex(0)
        self.daily_budget.setValue(100)
        self.window_start.setTime(QTime(0, 0))
        self.window_end.setTime(QTime(0, 0))
        from .mail_defaults import apply_plan_defaults
        apply_plan_defaults(self)
        self.builder_id, self.version_id, self.saved_graph = None, None, None
        self.graph, self.history, self.future = starter_graph(self.preferences.builder_default_blocks), [], []
        self.scene.rebuild(self.graph)
        self.saved.clear()
        self.versions.clear()
        self.name.setText("Mein E-Mail-Ablauf")
        self.invalidate()
        self.setEnabled(bool(project_path))
        self.fit()
        self.refresh_node_jump()

    def request_load(self):
        self.operation_requested.emit("builder_details", {})

    def display_details(self, value):
        first_details = not self.data
        self.data = value
        self.saved.clear()
        for item in value["builders"]:
            _ui_locale.add_item(self.saved, _ui_format('{0} · v{1}', f"{item['name']}", f"{item['version_number']}"), item['version_id'])
        for combo, entries, caption, field in ((self.account, value["accounts"], "Später wählen", "account_email"), (self.signature, value["signatures"], "Ohne Signatur", "name")):
            previous = combo.currentData()
            if first_details and combo is self.account:
                previous = value.get("project_settings", {}).get("account_id")
            combo.blockSignals(True)
            combo.clear()
            _ui_locale.add_item(combo, _ui_tr(caption), None)
            for item in entries:
                combo.addItem(item[field], item["id"])
            combo.setCurrentIndex(max(0, combo.findData(previous)))
            combo.blockSignals(False)
            if previous != combo.currentData():
                self.invalidate()
        self.update_buttons()
        if first_details and not self.history and self.saved_graph is None:
            for item in self.graph["nodes"]:
                if item["kind"] == "email":
                    item["config"]["body_format"] = value.get("project_settings", {}).get("defaults", {}).get("body_format", "plain")
            self.scene.rebuild(self.graph)
        if self._first_fit:
            self.fit()
            self._first_fit = False
        if first_details:
            from .mail_defaults import apply_mail_defaults
            apply_mail_defaults(self, project_account=value.get("project_settings", {}).get("account_id"))
        workspace = value.get("workspace")
        if workspace and not self._workspace_loaded:
            self.project_id = workspace["project_id"]
            self._workspace_revision = workspace["revision"]
            self._workspace_loaded = True
            self._autosave_blocked = bool(workspace["warning"])
            if workspace["warning"]:
                _ui_locale.set_text(self.checkpoint_label, workspace['warning'])
            elif workspace["state"] and (self.preferences.builder_autosave or getattr(self, "_load_workspace_explicitly", False)):
                self.restore_workspace(workspace)
            else:
                _ui_locale.set_text(self.checkpoint_label, _ui_tr('Autosicherung deaktiviert; vorhandener Arbeitsstand manuell ladbar.') if not self.preferences.builder_autosave else _ui_tr('Arbeitsstand wird nach Eingabepause gesichert.'))
            self.schedule_checkpoint()
            self._load_workspace_explicitly = False

    def load_selected(self):
        identifier = self.versions.currentData() if self.versions.count() and self.saved.currentData() == self.versions.property("latest") else self.saved.currentData()
        if identifier and self.discard_confirm():
            self.operation_requested.emit("builder_load", {"version_id": identifier})

    def discard_confirm(self):
        return (self.saved_graph == self.graph and self.saved_name == self.name.text()) or (self.saved_graph is None and not self.history and self.name.text() == "Mein E-Mail-Ablauf") or QMessageBox.question(self, _ui_tr('Builder wechseln'), _ui_tr('Ungespeicherte Änderungen verwerfen?'), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes

    def new_graph(self):
        if self.discard_confirm():
            self.graph, self.history, self.future = starter_graph(self.preferences.builder_default_blocks), [], []
            for item in self.graph["nodes"]:
                if item["kind"] == "email":
                    item["config"]["body_format"] = self.data.get("project_settings", {}).get("defaults", {}).get("body_format", "plain")
            self.builder_id, self.version_id, self.saved_graph, self.last_batch = None, None, None, None
            self.name.setText("Mein E-Mail-Ablauf")
            self.delivery_mode.setCurrentIndex(0)
            self.daily_budget.setValue(100)
            self.window_start.setTime(QTime(0, 0))
            self.window_end.setTime(QTime(0, 0))
            from .mail_defaults import apply_plan_defaults
            apply_plan_defaults(self)
            self.scene.rebuild(self.graph)
            self.invalidate()
            self.fit()

    def loaded(self, value):
        self.builder_id, self.version_id = value["builder_id"], value["id"]
        self.graph, self.saved_graph = deepcopy(value["graph"]), deepcopy(value["graph"])
        self.history, self.future = [], []
        self.name.setText(value["name"])
        self.saved_name = value["name"]
        self.versions.clear()
        self.versions.setProperty("latest", value["versions"][0]["id"])
        for version in value["versions"]:
            _ui_locale.add_item(self.versions, _ui_format('Version {0}', str(version['version_number'])), version['id'])
        self.versions.setCurrentIndex(self.versions.findData(value["id"]))
        self.last_batch = None
        self.invalidate()
        self.scene.rebuild(self.graph)
        self.fit()
        _ui_locale.set_text(self.status, _ui_format('Version {0} geöffnet. Quellen werden bei Vorschau neu gelesen.', f"{value['version_number']}"))

    def save(self, copy=False):
        if self.busy:
            return
        self.operation_requested.emit("builder_save", {"name": self.name.text(), "graph": deepcopy(self.graph),
            "builder_id": None if copy else self.builder_id, "base_version_id": None if copy else self.version_id})

    def save_node_group(self):
        if self.busy:return
        selected=[card.value['id'] for card in self.scene.selectedItems() if hasattr(card,'value') and isinstance(card.value,dict) and 'id' in card.value]
        if not selected and self.selected_id:selected=[self.selected_id]
        if not selected:
            _ui_locale.set_text(self.status, _ui_tr('Bausteine auf der Zeichenfläche auswählen.'));return
        name,ok=QInputDialog.getText(self, _ui_tr('Bausteingruppe'), _ui_tr('Name der Auswahl'))
        if ok and name.strip():self.operation_requested.emit('builder_groups_save',{'name':name,'graph':deepcopy(self.graph),'selected_ids':selected})

    def request_node_groups(self,action):
        if self.busy:return
        self._group_action=action
        self.operation_requested.emit('builder_groups_list',{})

    def display_node_groups(self,groups,choose=False):
        if not choose:
            _ui_locale.set_text(self.status, _ui_tr('Bausteingruppen gespeichert.'));return
        if not groups:
            _ui_locale.set_text(self.status, _ui_tr('Noch keine Bausteingruppen gespeichert.'));return
        name,ok=QInputDialog.getItem(self, _ui_tr('Bausteingruppen'), _ui_tr('Gruppe wählen'), [g['name'] for g in groups], 0, False)
        if not ok:return
        group=next(g for g in groups if g['name']==name)
        if self._group_action=='delete':
            if QMessageBox.question(self, _ui_tr('Gruppe löschen'), _ui_tr('Gespeicherte Bausteingruppe löschen? Eingefügte Bausteine bleiben erhalten.'))==QMessageBox.StandardButton.Yes:
                self.operation_requested.emit('builder_groups_delete',{'group_id':group['id'],'expected_version':group['version']})
        else:
            from ..builder_groups import insert_group
            try:
                graph,ids=insert_group(self.graph,json.loads(group['graph_json']))
                self.commit(graph,ids[0])
                _ui_locale.set_text(self.status, _ui_tr('Gruppe eingefügt. Außenverbindungen und Datenquelle prüfen.'))
            except ValueError as error:_ui_locale.set_text(self.status, str(error))

    def move_attachment(self,direction):
        edges=[i for i,e in enumerate(self.graph['edges']) if e['to']==self.selected_id and e['input']=='attachments']
        index=self.attachment_order.currentIndex();target=index+direction
        if 0<=index<len(edges) and 0<=target<len(edges):
            graph=deepcopy(self.graph)
            graph['edges'][edges[index]],graph['edges'][edges[target]]=graph['edges'][edges[target]],graph['edges'][edges[index]]
            self.commit(graph,self.selected_id)
            self.attachment_order.setCurrentIndex(target)

    def export_graph(self):
        if self.busy:
            return
        path, _ = QFileDialog.getSaveFileName(self, _ui_tr('Graphvorlage exportieren · Texte/Regeln bleiben enthalten, Quellen neu zuordnen'), str(Path(self.project_path) / 'exports' / 'Builder.json'), _ui_tr('EmailCenter Graph (*.json)'), options=QFileDialog.Option.DontConfirmOverwrite)
        if not path:
            return
        target = Path(path)
        if not target.suffix:
            target = target.with_suffix(".json")
        overwrite = target.exists()
        if overwrite and QMessageBox.question(self, _ui_tr('Graphdatei ersetzen'), _ui_format('{0} ersetzen?', f'{target.name}')) != QMessageBox.StandardButton.Yes:
            return
        self.operation_requested.emit("builder_export", {"name": self.name.text(), "graph": deepcopy(self.graph), "target_path": str(target), "overwrite": overwrite})

    def import_graph(self):
        if self.busy:
            return
        path, _ = QFileDialog.getOpenFileName(self, _ui_tr('Graphvorlage importieren'), filter='EmailCenter Graph (*.json)')
        if path:
            self.operation_requested.emit("builder_import", {"path": path})

    def imported(self, value):
        sources = "\n".join("• " + source["title"] for source in value["sources"]) or "Keine"
        if QMessageBox.question(self, _ui_tr('Graphvorlage übernehmen'), _ui_format('{0} · {1} Bausteine\n\nAktuellen Graphen durch diese Vorlage ersetzen? Texte/Regeln bleiben enthalten. Datenquellen und Dateien neu zuordnen:\n{2}\n\nKonto, Signatur, Planung und Gruppenverknüpfung werden neu gewählt.', f"{value['name']}", f"{len(value['graph']['nodes'])}", f'{sources}'), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        self.builder_id, self.version_id = None, None
        self.saved_graph, self.saved_name, self.last_batch = None, None, None
        self.history, self.future = [], []
        self.graph = deepcopy(value["graph"])
        self.name.setText(value["name"])
        self.account.setCurrentIndex(0)
        self.signature.setCurrentIndex(0)
        self.delivery_mode.setCurrentIndex(0)
        self.versions.clear()
        self.invalidate()
        self._painting = True
        self.scene.rebuild(self.graph)
        self._painting = False
        self.selection_changed()
        self.fit()
        _ui_locale.set_text(self.status, _ui_tr('Graphvorlage übernommen. Daten und Dateipfade neu zuordnen, anschließend Vorschau prüfen und als eigene Version speichern.'))
        self.update_buttons()
        self.schedule_checkpoint()

    def saved_version(self, value):
        self.display_details({**self.data, "builders": value["builders"]})
        self.loaded(value["version"])
        self.saved.setCurrentIndex(self.saved.findData(value["version"]["id"]))

    def commit(self, graph, selected=None, *, rebuild=True):
        try:
            validate_graph(graph, editable=True)
        except ValueError as error:
            _ui_locale.set_text(self.status, str(error))
            return False
        if graph == self.graph:
            return True
        self.history.append(deepcopy(self.graph))
        self.history = self.history[-100:]
        self.future = []
        self.graph = deepcopy(graph)
        self.invalidate()
        if rebuild:
            self._painting = True
            self.scene.rebuild(self.graph, selected)
            self._painting = False
            self.selection_changed()
        else:
            for key, card in self.scene.cards.items():
                card.value = next(n for n in self.graph["nodes"] if n["id"] == key)
                card.update()
        self.update_buttons()
        return True

    def add_node(self, kind, x=None, y=None):
        if kind not in NODE_TYPES or self.busy:
            return
        point = self.view.mapToScene(self.view.viewport().rect().center())
        if x is None and y is None:
            height = max(115, 88 + max(len(NODE_TYPES[kind]["inputs"]), len(NODE_TYPES[kind]["outputs"])) * 29)
            for distance in range(12):
                candidates = [point + QPointF(dx * 340, dy * 220) for dy in range(-distance, distance + 1) for dx in range(-distance, distance + 1) if max(abs(dx), abs(dy)) == distance]
                free = next((candidate for candidate in candidates if not any(QRectF(candidate.x() - 15, candidate.y() - 10, 278, height + 20).intersects(card.sceneBoundingRect()) for card in self.scene.cards.values())), None)
                if free is not None:
                    point = free
                    break
        item = node(kind, point.x() if x is None else x, point.y() if y is None else y)
        graph = deepcopy(self.graph)
        graph["nodes"].append(item)
        if self.commit(graph, item["id"]):
            self.view.ensureVisible(self.scene.cards[item["id"]].sceneBoundingRect(), 30, 30)

    def arrange(self):
        if not self.busy:
            self.commit(arrange_graph(self.graph), self.selected_id)
            self.fit()

    def refresh_node_jump(self):
        if not hasattr(self, "node_jump"):
            return
        self.node_jump.blockSignals(True)
        self.node_jump.clear()
        _ui_locale.add_item(self.node_jump, _ui_tr('Baustein wählen / zentrieren'), None)
        for index, item in enumerate(self.graph["nodes"], 1):
            _ui_locale.add_item(self.node_jump, _ui_format('{0}. {1}', index, _ui_tr(NODE_TYPES[item['kind']]['title'])), item['id'])
        self.node_jump.setCurrentIndex(max(0, self.node_jump.findData(self.selected_id)))
        self.node_jump.blockSignals(False)

    def jump_to_node(self, *args):
        identifier = self.node_jump.currentData()
        if identifier and identifier in self.scene.cards:
            self._painting = True
            self.scene.clearSelection()
            card = self.scene.cards[identifier]
            card.setSelected(True)
            self._painting = False
            self.view.centerOn(card)
            self.selection_changed()

    def connect_ports(self, source, target):
        if self.busy:
            return
        graph = deepcopy(self.graph)
        graph["edges"].append({"from": source.parentItem().value["id"], "output": source.name, "to": target.parentItem().value["id"], "input": target.name})
        selected = target.parentItem().value["id"]
        # Finish the graphics mouse event before rebuilding/deleting its port item.
        QTimer.singleShot(0, lambda: self.commit(graph, selected))

    def capture_positions(self):
        graph = deepcopy(self.graph)
        for item in graph["nodes"]:
            point = self.scene.cards[item["id"]].pos()
            item["x"], item["y"] = point.x(), point.y()
        self.commit(graph, rebuild=False)

    def delete_selected(self):
        graph = deepcopy(self.graph)
        ids = {i.value["id"] for i in self.scene.selectedItems() if isinstance(i, NodeCard)}
        edges = {i.data(0) for i in self.scene.selectedItems() if isinstance(i, QGraphicsPathItem)}
        graph["nodes"] = [n for n in graph["nodes"] if n["id"] not in ids]
        graph["edges"] = [e for index, e in enumerate(graph["edges"]) if index not in edges and e["from"] not in ids and e["to"] not in ids]
        self.commit(graph)

    def duplicate_selected(self):
        graph = deepcopy(self.graph)
        for card in self.scene.selectedItems():
            if isinstance(card, NodeCard):
                item = node(card.value["kind"], card.pos().x() + 40, card.pos().y() + 40)
                item["config"] = deepcopy(card.value["config"])
                graph["nodes"].append(item)
        self.commit(graph)

    def undo(self):
        if self.history and not self.busy:
            self.future.append(deepcopy(self.graph))
            self.graph = self.history.pop()
            self.scene.rebuild(self.graph)
            self.invalidate()

    def redo(self):
        if self.future and not self.busy:
            self.history.append(deepcopy(self.graph))
            self.graph = self.future.pop()
            self.scene.rebuild(self.graph)
            self.invalidate()

    def selection_changed(self):
        if self._painting:
            return
        self.selected_id = next((i.value["id"] for i in self.scene.selectedItems() if isinstance(i, NodeCard)), None)
        if self.view.keyboard_port and self.view.keyboard_port[0] != self.selected_id:
            self.view.highlight_port()
        self.refresh_node_jump()
        if self.selected_id:
            self.inspector.setCurrentIndex(0)
        self._asset_request_id = None
        self.node_preview.clear()
        self.inline_preview = None
        self.inline_mail = None
        body = QWidget()
        form = QFormLayout(body)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.properties.setWidget(body)
        item = next((n for n in self.graph["nodes"] if n["id"] == self.selected_id), None)
        if not item:
            form.addRow(label(_ui_tr('Baustein auswählen, um Eigenschaften zu bearbeiten. Verbindungen auswählen und mit Entf löschen.'), 'muted'))
            return
        kind, config = item["kind"], item["config"]
        form.addRow(label(_ui_tr(NODE_TYPES[kind]['title'])))
        if kind != "email":
            form.addRow(label(_ui_tr('Stecker verbinden durch Ziehen oder Ausgang/Eingang anklicken.'), 'muted'))
        if kind == "data":
            form.addRow(label(_ui_format('{0} Datenzeilen', f"{len(config['sources'])}")))
            form.addRow(button(_ui_tr('Excel / CSV laden'), lambda: self.source_requested.emit('file')))
            form.addRow(button(_ui_tr('Excel / CSV auswählen'), lambda: self.source_requested.emit('import')))
            repeated = _ui_locale.widget(QCheckBox, _ui_tr('Mehrere Bewerbungsziele an dieselbe E-Mail-Adresse zulassen'))
            repeated.setChecked(config.get('allow_duplicate_recipients', False))
            repeated.toggled.connect(lambda value: self.property_changed('allow_duplicate_recipients', value))
            form.addRow(repeated)
            form.addRow(button(_ui_tr('Datenliste / manuelle Liste'), lambda: self.source_requested.emit('manual')))
            form.addRow(label(_ui_tr('Ausgang values versorgt Texte/Word Replace; email versorgt den Empfänger.'), 'muted'))
        elif kind in ('date', 'time', 'variable', 'clean'):
            def edit(key, caption, multiline=False):
                control = QPlainTextEdit(config[key]) if multiline else QLineEdit(config[key])
                control.setObjectName('value_' + key)
                if multiline:
                    control.setMaximumHeight(140)
                    control.textChanged.connect(lambda: self.property_changed(key, control.toPlainText(), draft=True))
                else:
                    control.textChanged.connect(lambda value: self.property_changed(key, value, draft=True))
                _ui_locale.add_row(form, _ui_tr(caption), control)
            def choice(key, caption, choices):
                control = QComboBox()
                for title, value in choices:
                    _ui_locale.add_item(control, _ui_tr(title), value)
                control.setCurrentIndex(control.findData(config[key]))
                control.setObjectName('value_' + key)
                control.currentIndexChanged.connect(lambda: self.property_changed(key, control.currentData(), draft=True))
                _ui_locale.add_row(form, _ui_tr(caption), control)
            def check(key, caption):
                control = _ui_locale.widget(QCheckBox, _ui_tr(caption))
                control.setChecked(config[key])
                control.toggled.connect(lambda value: self.property_changed(key, value, draft=True))
                form.addRow(control)
            if kind == 'clean':
                for key, caption in (('trim', 'Rand-Leerzeichen entfernen'), ('collapse_spaces', 'Mehrfache Leerzeichen zusammenfassen'), ('remove_empty_lines', 'Leerzeilen entfernen')):
                    check(key, caption)
                choice('case', 'Schreibweise', [('Unverändert', 'unchanged'), ('Kleinbuchstaben', 'lower'), ('Großbuchstaben', 'upper'), ('Wortanfänge groß', 'title')])
            else:
                edit('field', 'Variablenname')
                if kind == 'variable':
                    edit('value', 'Festwert / Text mit Platzhaltern', True)
                else:
                    choice('mode', 'Wertquelle', [('Aktuell', 'today' if kind == 'date' else 'now'), ('Festwert', 'fixed'), ('Excel / Datenfeld', 'source')])
                    edit('value', 'Festwert (YYYY-MM-DD / HH:mm)')
                    edit('source_field', 'Quellspaltenname')
                    edit('timezone', 'Zeitzone')
                    choice('format', 'Ausgabeformat', [(f, f) for f in (DATE_FORMATS if kind == 'date' else TIME_FORMATS)])
                    if kind == 'date':
                        offset = QSpinBox(); offset.setRange(-36500, 36500); offset.setValue(config['offset_days'])
                        offset.valueChanged.connect(lambda value: self.property_changed('offset_days', value))
                        _ui_locale.add_row(form, _ui_tr('Versatz in Tagen'), offset)
                check('overwrite', 'Vorhandenes Datenfeld überschreiben')
                form.addRow(label(_ui_tr('Excel values → Variable values → Text/Word Replace values verbinden. Den Variablennamen als {{datum}} im Text verwenden. Aktuelle Zeit wird bei der Zeilenvorschau für alle Zeilen festgehalten.'), 'muted'))
            self.inline_preview = BuilderPreview(body)
            form.addRow(self.inline_preview)
        elif kind in (*TEXT_KINDS, "recipient"):
            editor = QPlainTextEdit(config["text"])
            editor.setMinimumHeight(160)
            editor.textChanged.connect(lambda: self.property_changed("text", editor.toPlainText()))
            form.addRow(editor)
            if kind in ("link", "button"):
                target = QLineEdit(config["url"])
                target.textChanged.connect(lambda value: self.property_changed("url", value))
                _ui_locale.add_row(form, _ui_tr('Linkziel'), target)
                form.addRow(label(_ui_tr('HTTP(S) oder mailto:E-Mail. {{company.website}} kann aus values übernommen werden. Link und Beschriftung erscheinen in Text- und HTML-Mails.'), 'muted'))
            elif kind == "list":
                ordered = _ui_locale.widget(QCheckBox, _ui_tr('Nummerierte Liste'))
                ordered.setChecked(config["ordered"])
                ordered.toggled.connect(lambda value: self.property_changed("ordered", value))
                form.addRow(ordered)
                form.addRow(label(_ui_tr('Ein Eintrag je Zeile; leere Zeilen werden ausgelassen. Persönliche Datenfelder sind möglich.'), 'muted'))
            form.addRow(label(_ui_tr('{{company.name}}, {{contact.display_name}} usw. Werte-Stecker verbinden. HTML wird im E-Mail-Baustein gewählt; Datenwerte werden dann escaped.'), 'muted'))
            self.inline_preview = BuilderPreview(body)
            self.inline_preview.setMaximumHeight(160)
            form.addRow(self.inline_preview)
            self.update_text_preview()
        elif kind in ("condition", "merge"):
            if kind == "condition":
                for key, caption in (("field", "Datenfeld"), ("compare", "Vergleichswert")):
                    edit = QLineEdit(config[key])
                    edit.setObjectName("condition_" + key)
                    edit.textChanged.connect(lambda value, key=key: self.property_changed(key, value, draft=True))
                    _ui_locale.add_row(form, _ui_tr(caption), edit)
                operator = QComboBox()
                for key, caption in CONDITION_OPERATORS.items():
                    _ui_locale.add_item(operator, _ui_tr(caption), key)
                operator.setCurrentIndex(operator.findData(config["operator"]))
                operator.currentIndexChanged.connect(lambda: self.property_changed("operator", operator.currentData()))
                _ui_locale.add_row(form, _ui_tr('Prüfung'), operator)
                case = _ui_locale.widget(QCheckBox, _ui_tr('Groß-/Kleinschreibung beachten'))
                case.setChecked(config["case_sensitive"])
                case.toggled.connect(lambda value: self.property_changed("case_sensitive", value))
                form.addRow(case)
                for key, caption in (("yes", "Wenn erfüllt · Ersatztext"), ("no", "Sonst · Ersatztext")):
                    edit = QPlainTextEdit(config[key])
                    edit.setObjectName("condition_" + key)
                    edit.setMaximumHeight(100)
                    edit.textChanged.connect(lambda key=key, edit=edit: self.property_changed(key, edit.toPlainText(), draft=True))
                    _ui_locale.add_row(form, _ui_tr(caption), edit)
                form.addRow(label(_ui_tr('values verbinden. yes/no wählen verbundene Texte; ohne Verbindung wird der entsprechende Ersatztext benutzt. Nur der gewählte Text wird in der fertigen Mail benötigt.'), 'muted'))
            else:
                edit = QPlainTextEdit(config["separator"])
                edit.setObjectName("merge_separator")
                edit.setMaximumHeight(80)
                edit.textChanged.connect(lambda: self.property_changed("separator", edit.toPlainText()))
                _ui_locale.add_row(form, _ui_tr('Trenntext'), edit)
                form.addRow(label(_ui_tr('Mehrere parts-Stecker verbinden. Verbindungsreihenfolge bestimmt die Ausgabe. Für einen Betreff einen Trenntext ohne Zeilenumbruch wählen; HTML bleibt im Nachrichtentext erhalten.'), 'muted'))
            self.inline_preview = BuilderPreview(body)
            self.inline_preview.setMinimumHeight(120)
            form.addRow(self.inline_preview)
            self.update_text_preview()
        elif kind in FILE_KINDS:
            self.inline_preview = BuilderPreview(body)
            self.inline_preview.setMinimumHeight(140)
            form.addRow(self.inline_preview)
            path = QLineEdit(config["path"])
            path.textChanged.connect(lambda value: self.property_changed("path", value))
            _ui_locale.add_row(form, _ui_tr('Datei'), path)
            form.addRow(button(_ui_tr('Datei wählen'), lambda: self.choose_file(path)))
            form.addRow(button(_ui_tr('Vorschau im Editor'), self.request_asset_preview))
            form.addRow(label(_ui_tr('Dateipfad kann {{attachment.path}} aus einem verbundenen values-Stecker verwenden. Bild/Video werden angehängt; Links als Text verbinden. Maximal 20 MiB Anhänge pro Nachricht.'), 'muted'))
            if kind=='inline_image':
                alt=QLineEdit(config['alt']);alt.textChanged.connect(lambda value:self.property_changed('alt',value,draft=True))
                _ui_locale.add_row(form, _ui_tr('Bildbeschreibung'), alt)
                width=QSpinBox();width.setRange(1,1200);width.setValue(config['width']);width.valueChanged.connect(lambda value:self.property_changed('width',value))
                _ui_locale.add_row(form, _ui_tr('Breite (Pixel)'), width)
                form.addRow(label(_ui_tr('text → body verbinden; das Bild wird eingebettet. HTML erforderlich.'), 'muted'))
        elif kind == 'attachment':
            filename=QLineEdit(config['filename']);filename.textChanged.connect(lambda value:self.property_changed('filename',value,draft=True))
            _ui_locale.add_row(form, _ui_tr('Persönlicher Dateiname'), filename)
            form.addRow(label(_ui_tr('Platzhalter wie {{company.name}} verwenden; Dateiendung beibehalten.'), 'muted'))
        elif kind == "replace":
            form.addRow(button(_ui_tr('Persönliche DOCX-Textvorschau'), self.request_asset_preview))
            table = self.rule_table = QTableWidget(len(config["rules"]), 3)
            _ui_locale.headers(table, [_ui_tr('Suchen'), _ui_tr('Ersatz'), _ui_tr('Datenfeld')])
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            for row, rule in enumerate(config["rules"]):
                for col, key in enumerate(("find", "replacement", "field")):
                    table.setItem(row, col, QTableWidgetItem(rule[key]))
            def rules_changed():
                rules = [{key: table.item(row, col).text() if table.item(row, col) else "" for col, key in enumerate(("find", "replacement", "field"))} for row in range(table.rowCount())]
                # Keep unfinished editor rows until preview/save; do not lose typing on strict validation.
                self.property_changed("rules", rules, draft=True)
            table.itemChanged.connect(rules_changed)
            table.setMinimumHeight(180)
            form.addRow(table)
            self.rule_feedback = label('', 'muted')
            form.addRow(self.rule_feedback)
            form.addRow(label(_ui_tr('Suchen = exakter Text im DOCX, z. B. {{Anrede}}. Datenfeld = Excel-Spalte, z. B. Anrede. Bei Datenfeld bleibt Ersatz leer; ohne Datenfeld wird Ersatz als fester Text verwendet.'), 'muted'))
            def show_rule_feedback():
                rules = [{key: table.item(row, col).text() if table.item(row, col) else '' for col, key in enumerate(('find', 'replacement', 'field'))} for row in range(table.rowCount())]
                rows, message = (), _ui_tr('Regelstruktur gültig. Datenwerte und Treffer in der Zeilenvorschau prüfen.')
                try:
                    validate_rules(rules, next(n for n in self.graph['nodes'] if n['id'] == self.selected_id)['config']['case_sensitive'])
                except WordRuleError as error:
                    rows, message = error.rule_rows, error.args[0]
                blocked = table.blockSignals(True)
                try:
                    for row in range(table.rowCount()):
                        for col in range(table.columnCount()):
                            cell = table.item(row, col)
                            if cell is None:
                                cell = QTableWidgetItem('')
                                table.setItem(row, col, cell)
                            cell.setBackground(QColor(220, 80, 65, 70) if row in rows else QColor(Qt.GlobalColor.transparent))
                            cell.setToolTip(str(message) if row in rows else '')
                finally:
                    table.blockSignals(blocked)
                _ui_locale.set_text(self.rule_feedback, message)
            table.itemChanged.connect(show_rule_feedback)
            show_rule_feedback()
            def add_rule():
                table.insertRow(table.rowCount())
                rules_changed()
                show_rule_feedback()
            def remove_rule():
                if table.currentRow() >= 0:
                    table.removeRow(table.currentRow())
                    rules_changed()
                    show_rule_feedback()
            form.addRow(button(_ui_tr('Regel hinzufügen'), add_rule))
            form.addRow(button(_ui_tr('Regel entfernen'), remove_rule))
            for key, caption in (("case_sensitive", "Groß-/Kleinschreibung"), ("whole_words", "Nur ganze Wörter")):
                control = _ui_locale.widget(QCheckBox, _ui_tr(caption))
                control.setChecked(config[key])
                control.toggled.connect(lambda value, key=key: self.property_changed(key, value, draft=True))
                if key == 'case_sensitive':
                    control.toggled.connect(show_rule_feedback)
                form.addRow(control)
            self.inline_preview = BuilderPreview(body)
            form.addRow(self.inline_preview)
        elif kind == "email":
            self.inline_mail = MailRenderer(body)
            form.addRow(self.inline_mail)
            combo = QComboBox()
            _ui_locale.add_item(combo, _ui_tr('Text'), 'plain')
            _ui_locale.add_item(combo, _ui_tr('HTML'), 'html')
            combo.setCurrentIndex(combo.findData(config["body_format"]))
            combo.currentIndexChanged.connect(lambda: self.property_changed("body_format", combo.currentData()))
            _ui_locale.add_row(form, _ui_tr('Format'), combo)
            self.attachment_order=QComboBox()
            for edge in self.graph['edges']:
                if edge['to']==self.selected_id and edge['input']=='attachments':
                    origin=next(n for n in self.graph['nodes'] if n['id']==edge['from'])
                    self.attachment_order.addItem(NODE_TYPES[origin['kind']]['title']+' · '+origin['config'].get('filename',origin['config'].get('path','')),edge['from'])
            _ui_locale.add_row(form, _ui_tr('Anhang-Reihenfolge'), self.attachment_order)
            form.addRow(button(_ui_tr('Anhang nach oben'), lambda: self.move_attachment(-1)))
            form.addRow(button(_ui_tr('Anhang nach unten'), lambda: self.move_attachment(1)))
            form.addRow(label(_ui_tr('Mehrere body-/attachments-Verbindungen werden in Verbindungsreihenfolge übernommen. Eine Nachricht je Zeile.'), 'muted'))
        elif kind == "convert":
            filename = QLineEdit(config.get('filename', ''))
            filename.setObjectName('pdf_filename_pattern')
            filename.setMaxLength(250)
            _ui_locale.set_placeholder(filename, _ui_tr('Leer = ursprünglicher DOCX-Name.pdf'))
            filename.textChanged.connect(lambda value: self.property_changed('filename', value, draft=True))
            _ui_locale.add_row(form, _ui_tr('PDF-Dateiname'), filename)
            form.addRow(label(_ui_tr('Beispiel: Anschreiben{{Unternehmen}}.pdf. Excel-Spaltennamen und vorhandene Datenfelder verwenden; .pdf beibehalten. Gilt für die gespeicherte Datei und den Mailanhang. Ungültige Zeichen in eingesetzten Werten werden durch _ ersetzt.'), 'muted'))
            form.addRow(label(_ui_tr('PDF wird beim Erstellen konvertiert. Mit Seitenlayout (PDF) die Ausgabe vor Gruppenanlage prüfen.'), 'muted'))
            self.inline_preview = BuilderPreview(body)
            form.addRow(self.inline_preview)
        if kind in ('docx','replace','convert'):
            form.addRow(button(_ui_tr('Seitenlayout (PDF) vorschauen'), lambda: self.request_asset_preview(layout=True)))
        if self.preview and self.preview.get("rows"):
            preview = self.preview["rows"][max(0, self.recipient.currentIndex())].get("node_previews", {}).get(self.selected_id)
            if preview and "text" in preview:
                self.node_preview.display(preview)
        self.refresh_selected_preview()

    def property_changed(self, key, value, draft=False):
        if self.busy or self._painting:
            return
        graph = deepcopy(self.graph)
        item = next((n for n in graph["nodes"] if n["id"] == self.selected_id), None)
        if item:
            item["config"][key] = value
            # Property typing may temporarily be invalid; show errors at preview/save, preserve editor input.
            if graph != self.graph:
                self.history.append(deepcopy(self.graph))
                self.history = self.history[-100:]
                self.future = []
                self.graph = graph
                card = self.scene.cards[self.selected_id]
                card.value = item
                card.update()
                self.invalidate()
                self.update_text_preview()

    def filter_palette(self, text):
        for index in range(self.palette.count()):
            item = self.palette.item(index)
            item.setHidden(text.casefold() not in item.text().casefold())

    def update_text_preview(self):
        item = next((n for n in self.graph["nodes"] if n["id"] == self.selected_id), None)
        if self.inline_preview and item and item["kind"] in ("condition", "merge"):
            data = self.current_row().get("node_previews", {}).get(self.selected_id) if self.current_row() else None
            if data:
                self.inline_preview.display(data)
            else:
                self.inline_preview.clear(_ui_tr("Zeilen-Vorschau laden, um Textwahl und Zusammenführung mit persönlichen Daten zu sehen."))
            return
        item = next((n for n in self.graph["nodes"] if n["id"] == self.selected_id), None)
        if self.inline_preview and item and item["kind"] in (*TEXT_KINDS, "recipient"):
            text = item["config"].get("text", "")
            kind = item["kind"]
            if self.preview and self.preview.get("rows"):
                data = self.preview["rows"][max(0, self.recipient.currentIndex())].get("node_previews", {}).get(self.selected_id)
                if data:
                    self.inline_preview.display(data)
                    return
            preview_format = "html" if kind == "html" else "text"
            if kind in ("link", "button", "list", "heading", "separator"):
                fields = {key: "{{" + key + "}}" for key in TOKEN.findall(text + item["config"].get("url", ""))}
                try:
                    text = body_part(text, fields, kind, "html", item["config"])
                    preview_format = "html"
                except ValueError as error:
                    text = str(error) + "\n\n" + text
            self.inline_preview.display({"format": preview_format, "text": text, "filename": "Live-Vorschau · Platzhalter erst nach Zeilenprüfung ersetzt"})

    def request_asset_preview(self, *, layout=False):
        if self.busy or not self.selected_id:
            return
        self._asset_request_id = str(uuid4())
        self.inspector.setCurrentIndex(2)
        self.node_preview.clear(_ui_tr("Vorschau wird geladen …"))
        self.operation_requested.emit("builder_asset_preview", {"graph": deepcopy(self.graph), "node_id": self.selected_id, "layout":layout,
            "row_number": max(1, self.recipient.currentIndex() + 1), "request_id": self._asset_request_id,
            "libreoffice_path": self.preferences.libreoffice_path, "conversion_timeout": self.preferences.conversion_timeout,
            **({'evaluation_time': self.preview['evaluation_time']} if self.preview and 'evaluation_time' in self.preview else {})})

    def display_asset_preview(self, value):
        if value.get("request_id") == self._asset_request_id:
            self.node_preview.display(value)
            if self.inline_preview:
                self.inline_preview.display(value)
            self.inspector.setCurrentIndex(2)

    def plan_changed(self, *args):
        self.schedule.setEnabled(self.delivery_mode.currentData() == "scheduled" and not self.busy)
        self.confirm.setChecked(False)
        if self.delivery_mode.currentData() != "drafts" and not self.account.currentData():
            _ui_locale.set_text(self.status, _ui_tr('Für Versandplanung unten ein verbundenes Gmail-Konto auswählen und die Vorschau erneut bestätigen.'))
        self.update_buttons()
        self.schedule_checkpoint()

    def choose_file(self, control):
        path = QFileDialog.getOpenFileName(self, _ui_tr('Datei für Baustein wählen'))[0]
        if path:
            _ui_locale.set_text(control, path)

    def drop_files(self, paths, point):
        if not paths or self.busy:
            return
        try:
            files = [Path(path).resolve() for path in paths]
            if any(not p.is_file() or p.stat().st_size > 20 * 1024 * 1024 for p in files):
                raise ValueError(_ui_tr('Nur vorhandene lokale Dateien bis 20 MiB übernehmen.'))
            if QMessageBox.question(self, _ui_tr('Dateien übernehmen'), _ui_format('{0} Dateien als Eingangsbausteine übernehmen? Anhänge werden durch Verbinden gewählt.', f'{len(files)}'), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                return
            graph = deepcopy(self.graph)
            for offset, path in enumerate(files):
                kind = next((kind for kind, extensions in EXTENSIONS.items() if path.suffix.lower() in extensions), "file")
                item = node(kind, point.x() + offset * 40, point.y() + offset * 40)
                item["config"]["path"] = str(path)
                graph["nodes"].append(item)
            self.commit(graph)
        except (OSError, ValueError) as error:
            _ui_locale.set_text(self.status, str(error))

    def fields(self):
        fields = list(dict.fromkeys([*SOURCE_FIELDS, *getattr(self, '_source_fields', []), *(key for n in self.graph["nodes"] for key in TOKEN.findall(n["config"].get("text", "") + n["config"].get("path", "") + n["config"].get("url", "") + n["config"].get("yes", "") + n["config"].get("no", ""))), *(n["config"]["field"] for n in self.graph["nodes"] if n["kind"] == "condition" and n["config"]["field"]), *(r["field"] for n in self.graph["nodes"] if n["kind"] == "replace" for r in n["config"]["rules"] if r["field"])]))
        fields.extend(n['config']['field'] for n in self.graph['nodes'] if n['kind'] in ('date', 'time', 'variable'))
        return list(dict.fromkeys(field for field in fields if FIELD_NAME.fullmatch(field)))

    def use_builtin_graph(self):
        from ..builtin_templates import GRAPHS, builder_graph
        title, accepted = QInputDialog.getItem(self, str(_ui_tr('Mitgelieferte Builder-Vorlagen …')), str(_ui_tr('Vorlage auswählen')), list(GRAPHS.values()), 0, False)
        if not accepted:
            return
        if QMessageBox.question(self, _ui_tr('Builder-Vorlage laden'), _ui_tr('Aktuellen Graph ersetzen? Zuvor als Version speichern. Daten, Konto und Versandfreigabe werden anschließend neu gewählt.'), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        self.commit(builder_graph(next(key for key, value in GRAPHS.items() if value == title)))
        self.account.setCurrentIndex(0)
        self.signature.setCurrentIndex(0)
        self.delivery_mode.setCurrentIndex(0)
        self.last_batch = None
        self.fit()
        self.update_buttons()

    def add_sources(self, value):
        self._source_fields = list(dict.fromkeys(key for row in value['contacts'] for key in row.get('source_values', {})))
        item = next((n for n in self.graph["nodes"] if n["kind"] == "data"), None)
        if item:
            graph = deepcopy(self.graph)
            next(n for n in graph["nodes"] if n["id"] == item["id"])["config"]["sources"] = [c["source"] for c in value["contacts"]]
            self.commit(graph, item["id"])
            _ui_locale.set_text(self.status, _ui_format('{0} Datenzeilen übernommen.', f"{len(value['contacts'])}"))

    def invalidate(self, *args):
        if self.preview:
            _ui_locale.set_text(self.status, _ui_tr('Ablauf geändert. Alle Zeilen erneut vorschauen und bestätigen.'))
        self.preview = None
        self._preview_error = None
        self._preview_epoch += 1
        self._asset_cache.clear()
        self._asset_queue.clear()
        self._asset_errors.clear()
        self.autoload_timer.stop()
        for card in self.scene.cards.values():
            card.set_preview()
        self.confirm.setChecked(False)
        self.recipient.clear()
        self.result.clear()
        self.mail_preview.clear()
        self._asset_request_id = None
        self.node_preview.clear()
        if self.inline_preview:
            self.inline_preview.clear(_ui_tr("Vorschau nach Änderung erneut laden."))
        self.refresh_mail_views()
        self.update_buttons()
        self.schedule_checkpoint()

    def request_preview(self):
        if self.busy:
            return
        self.invalidate()
        try:
            validate_graph(self.graph, complete=True)
        except ValueError as error:
            self._preview_error = error.args[0]
            identifier = getattr(error, 'builder_node_id', None)
            if identifier in self.scene.cards:
                self.scene.clearSelection()
                self.scene.cards[identifier].setSelected(True)
                self.view.ensureVisible(self.scene.cards[identifier])
                self.inspector.setCurrentIndex(0)
                if getattr(error, 'rule_rows', ()):
                    self.rule_table.setCurrentCell(error.rule_rows[-1], 0)
                    self.rule_table.scrollToItem(self.rule_table.currentItem())
            _ui_locale.set_text(self.status, self._preview_error)
            self.update_buttons()
            return
        _ui_locale.set_text(self.status, _ui_tr('Alle Datenzeilen, Texte und Anhänge werden geprüft …'))
        self.operation_requested.emit("builder_preview", {"graph": deepcopy(self.graph), "provider_account_id": self.account.currentData(), "signature_id": self.signature.currentData(), "libreoffice_path": self.preferences.libreoffice_path, "conversion_timeout": self.preferences.conversion_timeout})

    def display_preview(self, value):
        self._source_fields = list(dict.fromkeys(key for row in value['rows'] for key in row.get('source_snapshot', {}).get('fields', {})))
        self.preview = value
        if not self.selected_id:
            self.inspector.setCurrentIndex(1)
        self.recipient.blockSignals(True)
        self.recipient.clear()
        for row in value["rows"]:
            _ui_locale.add_item(self.recipient, _ui_format("{0}. {1} · {2}", row["number"], row["name"], _ui_tr("Fehler" if row["error"] else "bereit")))
        self.recipient.blockSignals(False)
        _ui_locale.set_text(self.status, _ui_format("{0} Zeilen geprüft. {1}", len(value["rows"]), _ui_tr("Ergebnisse prüfen und bestätigen." if value["ready"] else "Fehler in Daten/Verbindungen korrigieren.")))
        self.show_row()
        self.update_text_preview()
        self.update_buttons()

    def show_row(self, *args):
        if not self.preview or not 0 <= self.recipient.currentIndex() < len(self.preview["rows"]):
            return
        row = self.preview["rows"][self.recipient.currentIndex()]
        from ..language import join_text
        text = _ui_format("An: {0}\nBetreff: {1}\nFormat: {2}\n\n{3}", row['email'], row.get('subject', ''),
                          row.get('body_format', ''), row.get('preview_body', ''))
        files = join_text('\n', (_ui_format('• {0} · {1}', f['filename'], f['size'] if f['size'] is not None
                                           else _ui_tr('Größe nach PDF-Konvertierung')) for f in row['attachments']))
        text = _ui_format('{0}\n\nAnhänge:\n{1}', text, files)
        for document in row["documents"]:
            text = _ui_format('{0}\n\nDOCX-Textvorschau:\n{1}', text, document['text'])
        if row["error"]:
            text = _ui_format('{0}\n\nFEHLER: {1}', text, row['error'])
        _ui_locale.set_plain_text(self.result, text)
        rendered = self.rendered.isChecked()
        self.result.setVisible(not rendered)
        self.mail_preview.setVisible(rendered)
        self.refresh_mail_views()
        for item in self.graph["nodes"]:
            value = self.node_value(item, row)
            card = self.scene.cards.get(item["id"])
            if card:
                cached = self._asset_cache.get((row["number"], item["id"]))
                card.set_preview(value, image_thumbnail(cached["content"]) if cached and cached.get("format") == "image" else None)
            if value and value.get("format") == "image":
                self.queue_asset(row, item)
        self.update_text_preview()
        self.refresh_selected_preview()
        self.autoload_timer.start(self.preferences.builder_preview_delay_ms)

    def current_row(self):
        index = self.recipient.currentIndex()
        return self.preview["rows"][index] if self.preview and 0 <= index < len(self.preview["rows"]) else None

    def node_value(self, item, row):
        if item["kind"] == "email":
            return {**row, "format": "mail"}
        return row.get("node_previews", {}).get(item["id"])

    def live_mail_row(self):
        """Unverified graph sketch, independent of the sendable row preview."""
        email = next((item for item in self.graph["nodes"] if item["kind"] == "email"), None)
        result = {"email": _ui_tr("Noch ungeprüft"), "subject": "", "preview_body": "", "body_format": email["config"]["body_format"] if email else "plain", "attachments": [], "live": True}
        if not email:
            return result
        nodes = {item["id"]: item for item in self.graph["nodes"]}
        parts = []
        for edge in self.graph["edges"]:
            if edge["to"] != email["id"]:
                continue
            item = nodes[edge["from"]]
            config = item["config"]
            text = config.get("text", "")
            if item["kind"] in ("condition", "merge"):
                text = _ui_format('[{0} · persönliche Zeilen-Vorschau laden]', _ui_tr(NODE_TYPES[item["kind"]]['title']))
            if edge["input"] == "subject":
                result["subject"] = text
            elif edge["input"] == "recipient" and item["kind"] == "recipient":
                result["email"] = text
            elif edge["input"] == "body":
                if item['kind']=='inline_image':
                    parts.append('[Inline-Bild · Zeilenvorschau laden]')
                    continue
                if item["kind"] in ("condition", "merge"):
                    parts.append(html.escape(text) if result["body_format"] == "html" else text)
                    continue
                fields = {key: "{{" + key + "}}" for key in TOKEN.findall(text + config.get("url", ""))}
                try:
                    parts.append(body_part(text, fields, item["kind"], result["body_format"], config))
                except ValueError:
                    parts.append(html.escape(text) if result["body_format"] == "html" else text)
            elif edge["input"] == "attachments":
                result["attachments"].append({"filename": config.get('filename') or Path(config.get("path", "")).name or NODE_TYPES[item["kind"]]["title"]})
        result["preview_body"] = ("<br><br>" if result["body_format"] == "html" else "\n\n").join(parts)
        return result

    def refresh_mail_views(self):
        row = self.current_row() or self.live_mail_row()
        media_errors = [message for (number, _), message in self._asset_errors.items() if number == row.get("number")]
        if media_errors:
            row = {**row, "error": row.get("error") or media_errors[0]}
        row = {**row, "sender": self.account.currentText() if self.account.currentData() else ""}
        inline_content={}
        for identifier,preview in row.get('node_previews',{}).items():
            if preview.get('cid'):
                data=self._asset_cache.get((row.get('number'),identifier))
                if data and data.get('format')=='image':inline_content[preview['cid']]=data['content']
        row={**row,'inline_content':inline_content}
        self.mail_preview.display(row)
        if self.inline_mail:
            self.inline_mail.display(row)

    def refresh_selected_preview(self):
        self.refresh_mail_views()
        row = self.current_row()
        item = next((item for item in self.graph["nodes"] if item["id"] == self.selected_id), None)
        if not row or not item or item["kind"] not in (*FILE_KINDS, "replace", "convert"):
            return
        value = self.node_value(item, row)
        if not value:
            return
        key = (row["number"], item["id"])
        data = self._asset_cache.get(key)
        if key in self._asset_errors:
            self.node_preview.clear(self._asset_errors[key])
            if self.inline_preview:
                self.inline_preview.clear(self._asset_errors[key])
        elif data or "text" in value or value.get("conversion"):
            data = data or ({"format": "text", "text": "PDF entsteht bei Gruppenanlage; DOCX-Text vorab prüfen.", "filename": value["filename"]} if value.get("conversion") else value)
            self.node_preview.display(data)
            if self.inline_preview:
                self.inline_preview.display(data)
        else:
            self.node_preview.clear(_ui_tr("Lokale Vorschau wird automatisch geladen …"))
            if self.inline_preview:
                self.inline_preview.clear(_ui_tr("Lokale Vorschau wird automatisch geladen …"))
            self.queue_asset(row, item, first=True)
            self.autoload_timer.start(0)

    def queue_asset(self, row, item, *, first=False):
        key = (row["number"], item["id"])
        if key in self._asset_cache or key in self._asset_errors or self._auto_asset_inflight and self._auto_asset_inflight["key"] == key and self._auto_asset_inflight["epoch"] == self._preview_epoch:
            return
        if key in self._asset_queue:
            self._asset_queue.remove(key)
        self._asset_queue.insert(0 if first else len(self._asset_queue), key)

    def autoload_next(self):
        if self._auto_asset_inflight or not self._asset_queue or not self.preview:
            return
        if self.busy:
            self.autoload_timer.start(200)
            return
        key = self._asset_queue.pop(0)
        if key in self._asset_cache or key in self._asset_errors:
            self.autoload_timer.start(0)
            return
        request_id = str(uuid4())
        self._auto_asset_inflight = {"key": key, "epoch": self._preview_epoch, "request_id": request_id}
        row = next(row for row in self.preview["rows"] if row["number"] == key[0])
        value = row["node_previews"][key[1]]
        self.asset_autoload_requested.emit("builder_asset_preview", {"graph": deepcopy(self.graph), "node_id": key[1], "row_number": key[0], "request_id": request_id,
            "expected_hash": value.get("hash"), "libreoffice_path": self.preferences.libreoffice_path, "conversion_timeout": self.preferences.conversion_timeout,
            **({'evaluation_time': self.preview['evaluation_time']} if 'evaluation_time' in self.preview else {})})

    def autoload_deferred(self, request_id):
        active = self._auto_asset_inflight
        if active and active["request_id"] == request_id:
            self._auto_asset_inflight = None
            if active["epoch"] == self._preview_epoch:
                self._asset_queue.insert(0, active["key"])
                self.autoload_timer.start(250)

    def display_auto_asset_preview(self, value=None, error=None):
        active = self._auto_asset_inflight
        if not active or value and value.get("request_id") != active["request_id"]:
            return
        self._auto_asset_inflight = None
        if active["epoch"] == self._preview_epoch and self.preview:
            key = active["key"]
            if error:
                self._asset_errors[key] = error
                self.confirm.setChecked(False)
                _ui_locale.set_text(self.status, _ui_tr('Bausteinvorschau fehlgeschlagen. Daten/Dateien prüfen und Zeilenvorschau erneuern.'))
                self.refresh_mail_views()
            else:
                self._asset_cache[key] = value
                self.refresh_mail_views()
                while len(self._asset_cache) > 6 or sum(len(data.get("content", b"")) for data in self._asset_cache.values()) > 40 * 1024 * 1024:
                    self._asset_cache.popitem(last=False)
                row = self.current_row()
                card = self.scene.cards.get(key[1])
                if card and row and row["number"] == key[0]:
                    card.set_preview(card.preview_value, image_thumbnail(value["content"]) if value.get("format") == "image" else None)
            row = self.current_row()
            if row and (row["number"], self.selected_id) == key:
                self.refresh_selected_preview()
            self.update_buttons()
        self.autoload_timer.start(0)

    def create(self):
        if self.preview and self.preview["ready"] and not self._asset_errors and self.confirm.isChecked() and not self.busy:
            mode = self.delivery_mode.currentData()
            plan = None if mode == "drafts" else {"interval_seconds": self.interval.value(), "timezone_id": self.timezone.currentText().strip(),
                "daily_budget": self.daily_budget.value(), "window_start": self.window_start.time().toString("HH:mm"), "window_end": self.window_end.time().toString("HH:mm"),
                "scheduled_local": self.schedule.dateTime().toString("yyyy-MM-ddTHH:mm:ss") if mode == "scheduled" else None}
            self.operation_requested.emit("builder_create", {"name": self.name.text(), "preview_id": self.preview["preview_id"], "delivery_plan": plan})

    def created(self, value):
        self.last_batch = value["batch"]["id"]
        self.invalidate()
        _ui_locale.set_text(self.status, _ui_format('{0} lokale Entwürfe gespeichert. Gruppe prüfen / senden öffnet die bestehende Freigabe.', f"{len(value['batch']['items'])}"))
        if value.get("dispatch"):
            ready = value["dispatch"]["status"] == "Ready"
            _ui_locale.set_text(self.status, _ui_format('Entwürfe und Versandplanung gespeichert. {0}', 'Versandkopien prüfen, freigeben und starten.' if ready else 'Vorbereitung im Gruppenfenster fortsetzen; bisherige Kopien bleiben gespeichert.'))
        self.update_buttons()

    def zoom(self, factor):
        current = self.view.transform().m11()
        target = min(2.5, max(.25, current * factor))
        self.view.scale(target / current, target / current)
        self.schedule_checkpoint()

    def fit(self):
        if self.scene.cards:
            rect = self.scene.itemsBoundingRect().adjusted(-35, -35, 35, 35)
            self.view.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
            self.zoom(1)

    def apply_settings(self, preferences):
        panel_changed = any(getattr(self.preferences, key) != getattr(preferences, key) for key in ("builder_palette_width", "builder_inspector_width", "builder_show_palette", "builder_show_inspector", "builder_compact_tools"))
        converter_changed = (self.preferences.libreoffice_path, self.preferences.conversion_timeout) != (preferences.libreoffice_path, preferences.conversion_timeout)
        zoom_changed = self.preferences.builder_zoom != preferences.builder_zoom
        self.preferences = preferences
        if panel_changed:
            self.apply_panel_layout()
        if zoom_changed:
            self.view.resetTransform()
            self.view.scale(preferences.builder_zoom / 100, preferences.builder_zoom / 100)
        self.scene.update()
        for card in self.scene.cards.values():
            card.set_preview(card.preview_value, card.preview_pixmap)
        if converter_changed:
            self.invalidate()
        self.schedule_checkpoint()

    def apply_panel_layout(self):
        self.palette.setMaximumWidth(self.preferences.builder_palette_width)
        self.palette_pane.setMaximumWidth(self.preferences.builder_palette_width + 12)
        self.palette_pane.setVisible(self.width() >= 900 and self.preferences.builder_show_palette)
        self.inspector_pane.setVisible(self.preferences.builder_show_inspector)
        self.tabs.setSizes([self.preferences.builder_palette_width, max(250, self.width() - self.preferences.builder_palette_width - self.preferences.builder_inspector_width), self.preferences.builder_inspector_width])
        captions = (("↶", "Rückgängig"), ("↷", "Wiederholen"), ("⧉", "Duplizieren"), ("×", "Löschen"))
        for control, (compact, full) in zip(self.tool_buttons[1:5], captions):
            _ui_locale.set_text(control, _ui_tr(compact if self.preferences.builder_compact_tools else full))
            _ui_locale.set_tooltip(control, _ui_tr(full))
            _ui_locale.set_accessible_name(control, _ui_tr(full))

    def toggle_panel(self, key):
        self.panel_preferences_requested.emit({**self.preferences.values(), key: not getattr(self.preferences, key)})

    def save_panel_sizes(self):
        sizes = self.tabs.sizes()
        values = self.preferences.values()
        if self.palette_pane.isVisible():
            values["builder_palette_width"] = max(150, min(320, sizes[0]))
        if self.inspector_pane.isVisible():
            values["builder_inspector_width"] = max(220, min(700, sizes[2]))
        self.panel_preferences_requested.emit(values)

    def work_state(self):
        point = self.view.mapToScene(self.view.viewport().rect().center())
        return {"history": self.persisted_history(self.history), "future": self.persisted_history(self.future), "graph": deepcopy(self.graph), "name": self.name.text(), "builder_id": self.builder_id, "version_id": self.version_id,
            "provider_account_id": self.account.currentData(), "signature_id": self.signature.currentData(), "last_batch": self.last_batch,
            "delivery_mode": self.delivery_mode.currentData(), "scheduled_local": self.schedule.dateTime().toString("yyyy-MM-ddTHH:mm:ss"),
            "timezone_id": self.timezone.currentText(), "interval_seconds": self.interval.value(),
            "daily_budget": self.daily_budget.value(), "window_start": self.window_start.time().toString("HH:mm"), "window_end": self.window_end.time().toString("HH:mm"),
            "view": {"zoom": self.view.transform().m11(), "x": min(100000, max(-100000, point.x())), "y": min(100000, max(-100000, point.y()))}}

    @staticmethod
    def persisted_history(graphs):
        # Keep the newest steps; never exceed the workspace storage limit.
        result, size = [], 0
        for graph in reversed(graphs[-100:]):
            length = len(json.dumps(graph, ensure_ascii=False).encode("utf-8"))
            if size + length > 4_000_000:
                break
            result.append(deepcopy(graph))
            size += length
        return list(reversed(result))

    def checkpoint_payload(self, *, force=False):
        if self._restoring or not self._workspace_loaded or not self.project_id or not (force or self.preferences.builder_autosave):
            return None
        if self._autosave_blocked:
            raise ValueError(_ui_tr('Autosicherung pausiert. Im Builder unter Plan den Arbeitsstand neu laden oder ausdrücklich ersetzen; aktuelle Eingaben vorher als Kopie speichern.'))
        state = self.work_state()
        if not force and digest(state) == self._autosave_hash:
            return None
        return {"project_id": self.project_id, "state": state, "expected_revision": self._workspace_revision}

    def schedule_checkpoint(self, *args):
        if hasattr(self, "autosave_timer") and self._workspace_loaded and not self._restoring and not self._autosave_blocked and self.preferences.builder_autosave:
            self.autosave_timer.start(self.preferences.builder_autosave_seconds * 1000)

    def request_checkpoint(self, *, force=False):
        force = force or self._checkpoint_force
        if self.busy:
            self._checkpoint_force = force
            self.autosave_timer.start(1000)
            return
        if self._autosave_blocked:
            if not force or QMessageBox.question(self, _ui_tr('Arbeitsstand ersetzen'), _ui_tr('Den zuletzt geladenen Arbeitsstand durch die aktuellen Eingaben ersetzen? Bei Änderungen aus einem anderen Fenster zuerst neu laden oder eine benannte Kopie speichern.'), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                return
            self._autosave_blocked = False
        payload = self.checkpoint_payload(force=force)
        if payload:
            self._checkpoint_force = force
            self.checkpoint_requested.emit("builder_workspace_save", payload)

    def checkpoint_saved(self, value):
        if value["project_id"] != self.project_id:
            return
        self._workspace_revision, self._autosave_hash = value["revision"], value["state_hash"]
        _ui_locale.set_text(self.checkpoint_label, _ui_format('Arbeitsstand gesichert · Revision {0}', str(value['revision'])))
        if digest(self.work_state()) == self._autosave_hash:
            self._checkpoint_force = False
        else:
            self.schedule_checkpoint()

    def checkpoint_failed(self, message):
        self._autosave_blocked = "anderen Fenster" in message
        _ui_locale.set_text(self.checkpoint_label, _ui_format('Autosicherung fehlgeschlagen: {0}', message))
        if not self._autosave_blocked:
            self.schedule_checkpoint()

    def reload_workspace(self):
        if not self.busy and self.discard_confirm():
            self._workspace_loaded = False
            self.autosave_timer.stop()
            self._load_workspace_explicitly = True
            self.request_load()

    def restore_workspace(self, value):
        self._restoring = True
        state = value["state"]
        if value["base_version"]:
            self.loaded(value["base_version"])
        else:
            self.builder_id, self.version_id, self.saved_graph = None, None, None
            self.versions.clear()
        self.graph, self.history, self.future = deepcopy(state["graph"]), deepcopy(state.get("history", [])), deepcopy(state.get("future", []))
        self.name.setText(state["name"])
        self.last_batch = state["last_batch"]
        self.account.setCurrentIndex(max(0, self.account.findData(state["provider_account_id"])))
        self.signature.setCurrentIndex(max(0, self.signature.findData(state["signature_id"])))
        self.delivery_mode.setCurrentIndex(self.delivery_mode.findData(state["delivery_mode"]))
        when = QDateTime.fromString(state["scheduled_local"], "yyyy-MM-ddTHH:mm:ss")
        if when.isValid():
            self.schedule.setDateTime(when)
        self.timezone.setCurrentText(state["timezone_id"])
        self.interval.setValue(state["interval_seconds"])
        from PySide6.QtCore import QTime
        self.daily_budget.setValue(state.get("daily_budget", 100))
        self.window_start.setTime(QTime.fromString(state.get("window_start", "00:00"), "HH:mm"))
        self.window_end.setTime(QTime.fromString(state.get("window_end", "00:00"), "HH:mm"))
        self.scene.rebuild(self.graph)
        self.view.resetTransform()
        self.view.scale(state["view"]["zoom"], state["view"]["zoom"])
        self.view.centerOn(state["view"]["x"], state["view"]["y"])
        self.invalidate()
        self._autosave_hash = digest(state)
        self._restoring = False
        _ui_locale.set_text(self.checkpoint_label, _ui_format('Arbeitsstand wiederhergestellt · Revision {0}', str(value['revision'])))
        _ui_locale.set_text(self.status, _ui_tr('Letzten Arbeitsstand wiederhergestellt. Daten/Vorschau und Versandfreigabe erneut prüfen.'))
        self.update_buttons()

    def set_busy(self, busy):
        self.busy = busy
        for control in (self.name, self.saved, self.versions, self.tabs, self.account, self.signature, self.confirm):
            control.setEnabled(not busy)
        for i in range(self.tools.count()):
            self.tools.itemAt(i).widget().setEnabled(not busy)
        self.update_buttons()
        if not busy and self._asset_queue:
            self.autoload_timer.start(0)

    def update_buttons(self):
        if not hasattr(self, "footer_buttons"):
            return
        _ui_locale.set_text(self.dirty, _ui_tr('Ungespeicherte Änderungen') if self.builder_id and (self.graph != self.saved_graph or self.name.text() != getattr(self, 'saved_name', '')) else _ui_tr('Version gespeichert') if self.builder_id else _ui_tr('Noch keine gespeicherte Version'))
        self.undo_button.setEnabled(not self.busy and bool(self.history))
        self.redo_button.setEnabled(not self.busy and bool(self.future))
        for control in (self.new_button, self.save_button, self.copy_button):
            control.setEnabled(not self.busy)
        self.load_button.setEnabled(not self.busy and bool(self.saved.count()))
        self.preview_button.setEnabled(not self.busy)
        planned = self.delivery_mode.currentData() != "drafts"
        _ui_locale.set_text(self.create_button, _ui_tr('Entwürfe & Planung erstellen') if planned else _ui_tr('Lokale Entwurfsgruppe erstellen'))
        self.create_button.setEnabled(not self.busy and bool(self.preview and self.preview["ready"]) and not self._asset_errors and self.confirm.isChecked() and bool(self.name.text().strip()) and (not planned or bool(self.account.currentData())))
        self.cancel_button.setEnabled(self.busy)
        self.delivery_button.setEnabled(not self.busy and bool(self.last_batch))
        ready = bool(self.preview and self.preview['ready']) and not self._asset_errors
        self.confirm.setEnabled(not self.busy and ready)
        if self.busy:
            hint = _ui_tr('Prüfung oder Erstellung läuft. Bitte warten; mit Vorgang abbrechen stoppen.')
        elif getattr(self, '_preview_error', None):
            hint = _ui_tr('Vorschau blockiert. Den angezeigten Fehler korrigieren und Alle Zeilen vorschauen erneut starten.')
        elif self._asset_errors:
            hint = _ui_tr('Eine Dateivorschau ist fehlgeschlagen. Dateien prüfen und Alle Zeilen vorschauen erneut starten.')
        elif self.preview and not self.preview['ready']:
            first_error = next((row['error'] for row in self.preview['rows'] if row['error']), '')
            hint = _ui_format('Vorschau enthält Fehler: {0}', first_error)
        elif not self.preview:
            hint = _ui_tr('Gruppe gespeichert. Gruppe prüfen / senden öffnet die zuletzt erstellte Gruppe zur Freigabe und zum Start.') if self.last_batch else _ui_tr('Schritt 1: Alle Zeilen vorschauen. Erst danach können die Ergebnisse bestätigt und Entwürfe erstellt werden.')
        elif not self.confirm.isChecked():
            hint = _ui_tr('Schritt 2: Jede Vorschau prüfen und Alle Zeilen, Texte und Anhänge geprüft bestätigen.')
        elif not self.name.text().strip():
            hint = _ui_tr('Für die Entwurfsgruppe oben einen Namen eingeben.')
        elif planned and not self.account.currentData():
            hint = _ui_tr('Für Versandplanung unten ein verbundenes Gmail-Konto auswählen und die Vorschau erneut bestätigen.')
        elif self.last_batch:
            hint = _ui_tr('Gruppe gespeichert. Gruppe prüfen / senden öffnet die zuletzt erstellte Gruppe zur Freigabe und zum Start.')
        else:
            hint = _ui_tr('Schritt 3: Entwürfe erstellen. Anschließend wird Gruppe prüfen / senden für Freigabe und Start aktiviert.')
        _ui_locale.set_text(self.workflow_hint, hint)
        _ui_locale.set_tooltip(self.create_button, hint)
        _ui_locale.set_tooltip(self.delivery_button, _ui_tr('Öffnet die zuletzt erstellte Gruppe zur Prüfung und Versandfreigabe.') if self.last_batch else _ui_tr('Zuerst eine fehlerfreie Zeilenvorschau prüfen, bestätigen und eine Entwurfsgruppe erstellen.'))
