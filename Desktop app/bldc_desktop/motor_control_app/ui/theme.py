"""Application-wide dark theme."""

DARK_STYLESHEET = r"""
QWidget {
    background-color: #11151c;
    color: #e6edf3;
    font-family: "SF Pro Text", "Inter", "Helvetica Neue", sans-serif;
    font-size: 13px;
}

QMainWindow, QSplitter, QScrollArea, QScrollArea > QWidget > QWidget {
    background-color: #0d1117;
}

QGroupBox {
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 9px;
    margin-top: 13px;
    padding: 14px 10px 10px 10px;
    font-weight: 600;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 5px;
    color: #9da7b3;
}

QLabel#sectionLabel {
    color: #8b949e;
    font-size: 12px;
    font-weight: 600;
}

QLabel#currentStepLabel {
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 12px;
    color: #f0f6fc;
    font-size: 25px;
    font-weight: 700;
    padding: 17px;
}

QComboBox, QSpinBox {
    background-color: #0d1117;
    border: 1px solid #3d444d;
    border-radius: 6px;
    padding: 6px 8px;
    min-height: 22px;
    selection-background-color: #1f6feb;
}

QComboBox:hover, QSpinBox:hover {
    border-color: #58a6ff;
}

QComboBox:disabled, QSpinBox:disabled {
    color: #6e7681;
    background-color: #161b22;
}

QComboBox::drop-down {
    border: 0;
    width: 24px;
}

QPushButton {
    background-color: #21262d;
    border: 1px solid #3d444d;
    border-radius: 6px;
    color: #f0f6fc;
    font-weight: 600;
    min-height: 24px;
    padding: 6px 11px;
}

QPushButton:hover {
    background-color: #30363d;
    border-color: #58a6ff;
}

QPushButton:pressed {
    background-color: #161b22;
}

QPushButton:disabled {
    background-color: #161b22;
    border-color: #30363d;
    color: #6e7681;
}

QPushButton#primaryButton {
    background-color: #238636;
    border-color: #2ea043;
}

QPushButton#primaryButton:hover {
    background-color: #2ea043;
}

QPushButton#dangerButton {
    background-color: #8e2731;
    border-color: #da3633;
}

QPushButton#dangerButton:hover {
    background-color: #a8323c;
}

QSlider::groove:horizontal {
    background: #30363d;
    border-radius: 3px;
    height: 6px;
}

QSlider::sub-page:horizontal {
    background: #2f81f7;
    border-radius: 3px;
}

QSlider::handle:horizontal {
    background: #f0f6fc;
    border: 1px solid #58a6ff;
    border-radius: 8px;
    margin: -5px 0;
    width: 16px;
}

QPlainTextEdit {
    background-color: #070b10;
    border: 1px solid #30363d;
    border-radius: 6px;
    color: #b7c3d0;
    selection-background-color: #264f78;
    padding: 6px;
}

QScrollBar:vertical {
    background: #161b22;
    width: 12px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background: #3d444d;
    border-radius: 5px;
    min-height: 25px;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

QSplitter::handle {
    background-color: #0d1117;
    width: 5px;
    height: 5px;
}

QStatusBar {
    background-color: #161b22;
    border-top: 1px solid #30363d;
    color: #8b949e;
}

QToolTip {
    background-color: #21262d;
    border: 1px solid #58a6ff;
    color: #f0f6fc;
    padding: 4px;
}
"""
