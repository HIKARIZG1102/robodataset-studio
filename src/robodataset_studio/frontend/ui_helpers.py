from __future__ import annotations

from PySide6.QtWidgets import QLabel, QLineEdit, QSizePolicy


def make_path_label(label: QLabel) -> QLabel:
    label.setWordWrap(True)
    label.setMinimumWidth(0)
    label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    return label


def make_path_field(field: QLineEdit) -> QLineEdit:
    field.setMinimumWidth(0)
    field.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
    field.textChanged.connect(field.setToolTip)
    field.setToolTip(field.text())
    return field
