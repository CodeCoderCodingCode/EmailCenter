"""Queued workspace operations with SQLite confined to one worker thread."""

from PySide6.QtCore import QObject, QThread, Signal, Slot
from threading import Event

from ..application.workspace import WorkspaceService
from ..documents import MissingRequiredValues
from ..language import format_text


class WorkspaceWorker(QObject):
    progressed = Signal(str, object)
    completed = Signal(str, object)
    failed = Signal(str, str)
    stopped = Signal()

    def __init__(self):
        super().__init__()
        self.cancel_event = Event()
        self.action = ""
        self.service = WorkspaceService(cancel_requested=self.cancel_event.is_set, progress_callback=lambda value: self.progressed.emit(self.action, value))

    @Slot(str, object)
    def execute(self, action, payload):
        self.action = action
        try:
            value = self.service.execute(action, payload)
        except MissingRequiredValues as error:
            self.failed.emit(action, str(format_text('Bitte Pflichtwerte ergänzen: {0}', ', '.join(error.placeholders))))
        except Exception as error:
            self.failed.emit(action, str(error))
        else:
            self.completed.emit(action, value)

    @Slot()
    def stop(self):
        try:
            self.service.close()
        finally:
            self.stopped.emit()


class WorkspaceController(QObject):
    progress_changed = Signal(str, object)
    completed = Signal(str, object)
    failed = Signal(str, str)
    busy_changed = Signal(bool)
    shutdown_finished = Signal()
    background_completed = Signal(str, object)
    background_failed = Signal(str, str)
    shutdown_blocked = Signal(str)
    _requested = Signal(str, object)
    _stop_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.busy = False
        self.stopping = False
        self.current_action = None
        self.checkpoint_provider = None
        self._background = None
        self._pending = None
        self._needs_checkpoint = False
        self.thread = QThread(self)
        self.thread.setObjectName("EmailCenterWorkspace")
        self.worker = WorkspaceWorker()
        self.worker.moveToThread(self.thread)
        self._requested.connect(self.worker.execute)
        self._stop_requested.connect(self.worker.stop)
        self.worker.completed.connect(self._completed)
        self.worker.failed.connect(self._failed)
        self.worker.progressed.connect(self.progress_changed.emit)
        self.worker.stopped.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.shutdown_finished)
        self.thread.start()

    def submit(self, action: str, payload: dict | None = None) -> bool:
        if self.busy or self.stopping:
            return False
        self.busy = True
        self.current_action = action
        self._pending = (action, payload or {})
        self._needs_checkpoint = bool(self.checkpoint_provider)
        self.worker.cancel_event.clear()
        self.busy_changed.emit(True)
        if self._background is None:
            self._dispatch_pending()
        return True

    def submit_background(self, action, payload):
        """Use the same DB worker while keeping editor controls available."""
        if self.busy or self.stopping or self._background is not None:
            return False
        self._background = (action, False)
        self._requested.emit(action, payload)
        return True

    def _dispatch_pending(self):
        if self._needs_checkpoint and self.checkpoint_provider:
            try:
                checkpoint = self.checkpoint_provider(self._pending[0] if self._pending else "shutdown")
            except Exception as error:
                self._checkpoint_failed(str(error))
                return
            self._needs_checkpoint = False
            if checkpoint:
                action, payload = checkpoint
                self._background = (action, True)
                self._requested.emit(action, payload)
                return
        if self._pending:
            action, payload = self._pending
            self._pending = None
            self._requested.emit(action, payload)
        elif self.stopping:
            self._stop_requested.emit()

    def _background_finished(self, action, value=None, error=None):
        barrier = self._background[1]
        self._background = None
        if error is None:
            self.background_completed.emit(action, value)
        else:
            self.background_failed.emit(action, error)
        if error is not None and barrier:
            self._checkpoint_failed(error)
            return
        if self._pending or self.stopping:
            self._dispatch_pending()

    def _checkpoint_failed(self, error):
        self._needs_checkpoint = False
        if self.stopping:
            self.stopping = False
            self.shutdown_blocked.emit(error)
        elif self._pending:
            pending_action = self._pending[0]
            self._pending = None
            self.busy, self.current_action = False, None
            self.busy_changed.emit(False)
            self.failed.emit(pending_action, "Arbeitsstand konnte nicht gesichert werden. " + error)

    @Slot(str, object)
    def _completed(self, action, value):
        if self._background is not None:
            self._background_finished(action, value=value)
            return
        self.busy = False
        self.current_action = None
        self.busy_changed.emit(False)
        self.completed.emit(action, value)

    @Slot(str, str)
    def _failed(self, action, message):
        if self._background is not None:
            self._background_finished(action, error=message)
            return
        self.busy = False
        self.current_action = None
        self.busy_changed.emit(False)
        self.failed.emit(action, message)

    def shutdown(self) -> bool:
        if self.busy:
            return False
        if not self.stopping:
            self.stopping = True
            self._needs_checkpoint = bool(self.checkpoint_provider)
            if self._background is None:
                self._dispatch_pending()
        return True

    def cancel_current(self):
        """Thread-safe cancellation checked between committed import rows."""
        self.worker.cancel_event.set()
