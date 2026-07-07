"""Dark / light / system theming built on Qt's Fusion style + a QSS accent layer."""
from __future__ import annotations

import subprocess

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

ACCENT = "#3b82f6"          # blue accent used across both themes
ACCENT_HOVER = "#2f6fe0"

# Semantic colors for the monitor text, per theme.
COLORS = {
    "dark": {
        "rx": "#e2e8f0",
        "tx": "#60a5fa",
        "info": "#a3a3a3",
        "warn": "#fbbf24",
        "error": "#f87171",
        "timestamp": "#6b7280",
        "delay": "#a78bfa",
    },
    "light": {
        "rx": "#1f2937",
        "tx": "#1d4ed8",
        "info": "#6b7280",
        "warn": "#b45309",
        "error": "#dc2626",
        "timestamp": "#9ca3af",
        "delay": "#7c3aed",
    },
}


def detect_system_theme() -> str:
    """Best-effort detection of the desktop light/dark preference on Linux."""
    try:
        out = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
            capture_output=True, text=True, timeout=1.0,
        )
        if out.returncode == 0 and "dark" in out.stdout.lower():
            return "dark"
        if out.returncode == 0 and ("light" in out.stdout.lower() or "default" in out.stdout.lower()):
            return "light"
    except Exception:  # noqa: BLE001
        pass
    # Fallback: infer from the current palette's window color.
    app = QApplication.instance()
    if app is not None:
        win = app.palette().color(QPalette.ColorRole.Window)
        if win.lightnessF() < 0.5:
            return "dark"
    return "light"


def resolve(theme: str) -> str:
    return detect_system_theme() if theme == "system" else theme


def _dark_palette() -> QPalette:
    p = QPalette()
    bg = QColor("#1e1f24")
    base = QColor("#17181c")
    alt = QColor("#26272e")
    text = QColor("#e6e6e6")
    disabled = QColor("#6b7280")
    p.setColor(QPalette.ColorRole.Window, bg)
    p.setColor(QPalette.ColorRole.WindowText, text)
    p.setColor(QPalette.ColorRole.Base, base)
    p.setColor(QPalette.ColorRole.AlternateBase, alt)
    p.setColor(QPalette.ColorRole.ToolTipBase, alt)
    p.setColor(QPalette.ColorRole.ToolTipText, text)
    p.setColor(QPalette.ColorRole.Text, text)
    p.setColor(QPalette.ColorRole.Button, alt)
    p.setColor(QPalette.ColorRole.ButtonText, text)
    p.setColor(QPalette.ColorRole.BrightText, QColor("#ff5555"))
    p.setColor(QPalette.ColorRole.Link, QColor(ACCENT))
    p.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, disabled)
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, disabled)
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, disabled)
    return p


def _light_palette() -> QPalette:
    p = QPalette()
    bg = QColor("#f4f5f7")
    base = QColor("#ffffff")
    alt = QColor("#eceef1")
    text = QColor("#1f2328")
    disabled = QColor("#9ca3af")
    p.setColor(QPalette.ColorRole.Window, bg)
    p.setColor(QPalette.ColorRole.WindowText, text)
    p.setColor(QPalette.ColorRole.Base, base)
    p.setColor(QPalette.ColorRole.AlternateBase, alt)
    p.setColor(QPalette.ColorRole.ToolTipBase, base)
    p.setColor(QPalette.ColorRole.ToolTipText, text)
    p.setColor(QPalette.ColorRole.Text, text)
    p.setColor(QPalette.ColorRole.Button, alt)
    p.setColor(QPalette.ColorRole.ButtonText, text)
    p.setColor(QPalette.ColorRole.BrightText, QColor("#dc2626"))
    p.setColor(QPalette.ColorRole.Link, QColor(ACCENT))
    p.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, disabled)
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, disabled)
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, disabled)
    return p


def _qss(mode: str) -> str:
    if mode == "dark":
        border = "#3a3b42"
        hover = "#2f3038"
        base = "#17181c"
        panel = "#22232a"
    else:
        border = "#d0d3d8"
        hover = "#e4e7eb"
        base = "#ffffff"
        panel = "#ffffff"
    return f"""
    QWidget {{ font-size: 13px; }}
    QGroupBox {{
        border: 1px solid {border};
        border-radius: 10px;
        margin-top: 14px;
        padding-top: 8px;
        font-weight: 600;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 5px;
    }}
    QPushButton {{
        border: 1px solid {border};
        border-radius: 8px;
        padding: 6px 14px;
        background: {panel};
    }}
    QPushButton:hover {{ background: {hover}; }}
    QPushButton:disabled {{ color: palette(mid); }}
    QPushButton#accent {{
        background: {ACCENT};
        color: white;
        border: 1px solid {ACCENT};
        font-weight: 600;
    }}
    QPushButton#accent:hover {{ background: {ACCENT_HOVER}; border-color: {ACCENT_HOVER}; }}
    QPushButton#danger {{ color: #ef4444; }}
    QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit, QTableWidget {{
        border: 1px solid {border};
        border-radius: 8px;
        padding: 4px 6px;
        background: {base};
        selection-background-color: {ACCENT};
    }}
    QComboBox::drop-down {{ border: none; width: 20px; }}
    QTabWidget::pane {{ border: 1px solid {border}; border-radius: 10px; top: -1px; }}
    QTabBar::tab {{
        padding: 7px 16px;
        border: 1px solid transparent;
        border-top-left-radius: 8px;
        border-top-right-radius: 8px;
    }}
    QTabBar::tab:selected {{
        background: {panel};
        border: 1px solid {border};
        border-bottom-color: {panel};
        font-weight: 600;
    }}
    QHeaderView::section {{
        background: {panel};
        border: none;
        border-bottom: 1px solid {border};
        padding: 6px;
        font-weight: 600;
    }}
    QTableWidget {{ gridline-color: {border}; }}
    QToolButton {{ border-radius: 6px; padding: 4px; }}
    QToolButton:hover {{ background: {hover}; }}
    QStatusBar {{ border-top: 1px solid {border}; }}
    QScrollBar:vertical {{ background: transparent; width: 12px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {border}; border-radius: 5px; min-height: 30px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px; }}
    QScrollBar::handle:horizontal {{ background: {border}; border-radius: 5px; min-width: 30px; }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
    """


def apply_theme(app: QApplication, theme: str) -> str:
    """Apply the resolved theme to the app. Returns the resolved mode name."""
    mode = resolve(theme)
    app.setStyle("Fusion")
    app.setPalette(_dark_palette() if mode == "dark" else _light_palette())
    app.setStyleSheet(_qss(mode))
    return mode
