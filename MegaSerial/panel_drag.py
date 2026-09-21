"""Header-only dragging and highlighted, same-view panel drop targets."""
from PyQt6.QtCore import Qt, QMimeData, QTimer
from PyQt6.QtGui import QDrag, QPainter, QPen, QCursor
from PyQt6.QtWidgets import QApplication, QLabel, QWidget

MIME = 'application/x-megaserial-panel'


class PanelHeader(QLabel):
    def __init__(self, view, ident):
        super().__init__()
        self.view, self.ident = view, ident
        self._press = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._press = None
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        if (self._press is None or not event.buttons() & Qt.MouseButton.LeftButton
                or (event.position().toPoint() - self._press).manhattanLength()
                < QApplication.startDragDistance()):
            return super().mouseMoveEvent(event)
        self._press = None
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(MIME, self.ident.encode('utf-8'))
        drag.setMimeData(mime)
        drag.setPixmap(self.grab())
        self.view.set_dragging(True)
        timer = QTimer(self)
        timer.timeout.connect(self._scroll_edges)
        timer.start(50)
        try:
            drag.exec(Qt.DropAction.MoveAction)
        finally:
            timer.stop()
            timer.deleteLater()
            self.view.set_dragging(False)

    def _scroll_edges(self):
        viewport = self.view.viewport()
        point = viewport.mapFromGlobal(QCursor.pos())
        if not viewport.rect().contains(point):
            return
        for coordinate, extent, bar in ((point.y(), viewport.height(), self.view.verticalScrollBar()),
                                        (point.x(), viewport.width(), self.view.horizontalScrollBar())):
            if coordinate < 35:
                bar.setValue(bar.value() - 20)
            elif coordinate > extent - 35:
                bar.setValue(bar.value() + 20)


class PanelDropTarget(QWidget):
    def __init__(self, view):
        super().__init__()
        self.view = view
        self.cell = None
        self._highlight = False
        self.setAcceptDrops(True)

    def accepts(self, event):
        source = event.source()
        return (isinstance(source, PanelHeader) and source.view is self.view
                and self.cell is not None and event.mimeData().hasFormat(MIME)
                and bytes(event.mimeData().data(MIME)) == source.ident.encode('utf-8')
                and self.view.widgets.get(source.ident, None) is not None)

    def dragEnterEvent(self, event):
        if self.accepts(event):
            self._highlight = True
            event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()
            self.update()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        self.dragEnterEvent(event)

    def dragLeaveEvent(self, event):
        self._highlight = False
        self.update()
        event.accept()

    def dropEvent(self, event):
        self._highlight = False
        self.update()
        if self.accepts(event):
            self.view.move_panel(event.source().ident, *self.cell)
            event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()
        else:
            event.ignore()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._highlight:
            painter = QPainter(self)
            painter.setPen(QPen(self.palette().highlight().color(), 3))
            painter.drawRect(self.rect().adjusted(2, 2, -2, -2))
