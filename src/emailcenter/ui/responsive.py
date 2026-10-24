"""Wrapping action rows and small-window form sizing shared by desktop screens."""

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtWidgets import QLayout, QFormLayout, QComboBox, QSplitter, QSpacerItem


class ActionFlowLayout(QLayout):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = []
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(8)

    def addItem(self, item):
        self.items.append(item)

    def addWidget(self, widget, *args):
        super().addWidget(widget)

    def addStretch(self, *args):
        self.addItem(QSpacerItem(0, 0))

    def count(self):
        return len(self.items)

    def itemAt(self, index):
        return self.items[index] if 0 <= index < len(self.items) else None

    def takeAt(self, index):
        return self.items.pop(index) if 0 <= index < len(self.items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self.arrange(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self.arrange(rect, False)

    def arrange(self, rect, measure):
        left, top, right, bottom = self.getContentsMargins()
        x, y, height = rect.x() + left, rect.y() + top, 0
        limit = rect.right() - right + 1
        for item in self.items:
            widget = item.widget()
            if widget and widget.isHidden():
                continue
            size = item.sizeHint()
            if x > rect.x() + left and x + size.width() > limit:
                x, y, height = rect.x() + left, y + height + self.spacing(), 0
            if not measure:
                item.setGeometry(QRect(x, y, min(size.width(), max(0, rect.width() - left - right)), size.height()))
            x += size.width() + self.spacing()
            height = max(height, size.height())
        return y + height - rect.y() + bottom

    def minimumSize(self):
        size = QSize()
        for item in self.items:
            size = size.expandedTo(item.minimumSize())
        left, top, right, bottom = self.getContentsMargins()
        return size + QSize(left + right, top + bottom)

    def sizeHint(self):
        return self.minimumSize()


class ResponsiveSplitter(QSplitter):
    def resizeEvent(self, event):
        self.setOrientation(Qt.Orientation.Horizontal if self.width() >= 720 else Qt.Orientation.Vertical)
        super().resizeEvent(event)


def compact_forms(root):
    for form in root.findChildren(QFormLayout):
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    for combo in root.findChildren(QComboBox):
        combo.setMinimumContentsLength(12)
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
