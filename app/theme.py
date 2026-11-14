from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

from .paths import resource_path

# ---------------------------------------------------------------------------
# Color tokens
# ---------------------------------------------------------------------------
_DARK = {
    "ACCENT": "#5B8CFF",
    "ACCENT_HOVER": "#4d7dff",
    "ACCENT_DISABLED": "#2c3d66",
    "BG": "#0E1117",
    "PANEL": "#161B24",
    "PANEL_2": "#1C2230",
    "BORDER": "#252C3A",
    "TEXT": "#E8EDF7",
    "MUTED": "#8A94A6",
    "INPUT_BG": "#0f131b",
    "HOVER": "#222a3a",
    "PRESSED": "#1a2130",
    "SCROLL": "#2a3346",
    "DISABLED_TEXT": "#5a6478",
    "DISABLED_BG": "#12161f",
    "TOOLTIP_BG": "#1C2230",
}

_LIGHT = {
    "ACCENT": "#4B7DFF",
    "ACCENT_HOVER": "#3d6fe8",
    "ACCENT_DISABLED": "#a8c2f5",
    "BG": "#F5F7FA",
    "PANEL": "#FFFFFF",
    "PANEL_2": "#EEF2F7",
    "BORDER": "#D8DEE8",
    "TEXT": "#1A2233",
    "MUTED": "#44506a",
    "INPUT_BG": "#FFFFFF",
    "HOVER": "#E8EDF4",
    "PRESSED": "#DFE6EF",
    "SCROLL": "#b7c0ce",
    "DISABLED_TEXT": "#8a95a8",
    "DISABLED_BG": "#f0f3f7",
    "TOOLTIP_BG": "#FFFFFF",
}

# A white checkmark drawn over the blue indicator (shared image asset).
def _check_url() -> str:
    p = resource_path("check.png").resolve().as_posix()
    # Forward-slash absolute path loads reliably in both QPixmap and QSS.
    return p

_TEMPLATE = """
* { font-family: "Microsoft YaHei UI", "Segoe UI", "PingFang SC", sans-serif; }
QWidget { color: @TEXT@; font-size: 13px; }
QMainWindow, QDialog { background: @BG@; }
QWidget#root { background: @BG@; }

QTabWidget::pane { border: none; background: transparent; }
QTabBar::tab {
    background: transparent; color: @MUTED@;
    padding: 9px 18px; border: none; border-bottom: 2px solid transparent;
    font-size: 13px;
}
QTabBar::tab:selected { color: @TEXT@; border-bottom: 2px solid @ACCENT@; }
QTabBar::tab:hover { color: @TEXT@; }

QGroupBox {
    border: 1px solid @BORDER@; border-radius: 12px; margin-top: 12px;
    background: @PANEL@; font-weight: 600; padding-top: 6px;
}
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; color: @TEXT@; }

QFrame#card {
    background: @PANEL@; border: 1px solid @BORDER@; border-radius: 14px;
}
QLabel#cardTitle { font-size: 14px; font-weight: 600; color: @TEXT@; }
QLabel#cardSubtitle { color: @MUTED@; font-size: 12px; }
QLabel#hint { color: @MUTED@; font-size: 12px; }
QLabel#sectionTitle { font-size: 15px; font-weight: 700; }

QPushButton {
    background: @PANEL_2@; border: 1px solid @BORDER@; border-radius: 8px;
    padding: 7px 16px; color: @TEXT@;
}
QPushButton:hover { border-color: @ACCENT@; background: @HOVER@; }
QPushButton:pressed { background: @PRESSED@; }
QPushButton:disabled { color: @DISABLED_TEXT@; background: @DISABLED_BG@; }
QPushButton#primary {
    background: @ACCENT@; border: none; color: #FFFFFF; font-weight: 600;
    padding: 9px 22px;
}
QPushButton#primary:hover { background: @ACCENT_HOVER@; }
QPushButton#primary:disabled { background: @ACCENT_DISABLED@; color: #ffffff; }
QPushButton#danger { background: transparent; border: 1px solid #FF6B6B; color: #FF6B6B; }

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background: @INPUT_BG@; border: 1px solid @BORDER@; border-radius: 8px;
    padding: 6px 10px; selection-background-color: @ACCENT@;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus { border-color: @ACCENT@; }
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {
    color: @DISABLED_TEXT@; background: @DISABLED_BG@; border-color: @BORDER@;
}
QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView {
    background: @PANEL_2@; border: 1px solid @BORDER@; selection-background-color: @ACCENT@;
}

QSlider::groove:horizontal { height: 5px; background: @BORDER@; border-radius: 2px; }
QSlider::handle:horizontal {
    width: 16px; height: 16px; margin: -6px 0; border-radius: 8px; background: @ACCENT@;
}
QSlider::sub-page:horizontal { background: @ACCENT@; border-radius: 2px; }

QCheckBox { spacing: 8px; }
QCheckBox::indicator {
    width: 20px; height: 20px; border: 1px solid @BORDER@; border-radius: 6px; background: @INPUT_BG@;
}
QCheckBox::indicator:checked {
    background: @ACCENT@; border-color: @ACCENT@; image: url(@CHECK@);
}
QCheckBox::indicator:hover { border-color: @ACCENT@; }
QCheckBox:disabled { color: @DISABLED_TEXT@; }

QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: @SCROLL@; border-radius: 5px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: transparent; height: 10px; }
QScrollBar::handle:horizontal { background: @SCROLL@; border-radius: 5px; min-width: 30px; }

QStatusBar { background: @PANEL@; color: @MUTED@; border-top: 1px solid @BORDER@; }
QToolTip { background: @TOOLTIP_BG@; color: @TEXT@; border: 1px solid @BORDER@; padding: 4px 8px; }

QMenu { background: @PANEL_2@; border: 1px solid @BORDER@; border-radius: 8px; padding: 4px; }
QMenu::item { padding: 7px 26px 7px 12px; border-radius: 6px; }
QMenu::item:selected { background: @ACCENT@; color: #FFFFFF; }
QMenu::separator { height: 1px; background: @BORDER@; margin: 4px 8px; }
"""


def _build_qss(tokens: dict[str, str]) -> str:
    qss = _TEMPLATE.replace("@CHECK@", _check_url())
    for key, value in tokens.items():
        qss = qss.replace(f"@{key}@", value)
    return qss


def _palette(tokens: dict[str, str]) -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(tokens["BG"]))
    palette.setColor(QPalette.WindowText, QColor(tokens["TEXT"]))
    palette.setColor(QPalette.Base, QColor(tokens["INPUT_BG"]))
    palette.setColor(QPalette.AlternateBase, QColor(tokens["PANEL"]))
    palette.setColor(QPalette.Text, QColor(tokens["TEXT"]))
    palette.setColor(QPalette.Button, QColor(tokens["PANEL_2"]))
    palette.setColor(QPalette.ButtonText, QColor(tokens["TEXT"]))
    palette.setColor(QPalette.Highlight, QColor(tokens["ACCENT"]))
    palette.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ToolTipBase, QColor(tokens["TOOLTIP_BG"]))
    palette.setColor(QPalette.ToolTipText, QColor(tokens["TEXT"]))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor(tokens["DISABLED_TEXT"]))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(tokens["DISABLED_TEXT"]))
    return palette


_CURRENT_THEME = "dark"


def current_theme() -> str:
    return _CURRENT_THEME


def apply_theme(app: QApplication, theme: str = "dark") -> None:
    global _CURRENT_THEME
    _CURRENT_THEME = "light" if theme == "light" else "dark"
    tokens = _LIGHT if _CURRENT_THEME == "light" else _DARK
    app.setPalette(_palette(tokens))
    app.setStyleSheet(_build_qss(tokens))
    app.setFont(QFont("Microsoft YaHei UI", 10))


def theme_tokens(theme: str) -> dict[str, str]:
    return _LIGHT if theme == "light" else _DARK
