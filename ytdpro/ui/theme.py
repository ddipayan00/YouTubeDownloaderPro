"""Palettes and the Qt stylesheet built from them."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    name: str
    window: str
    surface: str
    surface_alt: str
    border: str
    border_strong: str
    text: str
    text_muted: str
    accent: str
    accent_hover: str
    accent_text: str
    success: str
    warning: str
    danger: str
    track: str


DARK = Palette(
    name="dark",
    window="#15181d",
    surface="#1c2027",
    surface_alt="#232830",
    border="#2e343e",
    border_strong="#3c4453",
    text="#e7eaf0",
    text_muted="#98a2b3",
    accent="#ff3d3d",
    accent_hover="#ff5c5c",
    accent_text="#ffffff",
    success="#3ecf8e",
    warning="#f0b429",
    danger="#f76d6d",
    track="#2a2f38",
)

LIGHT = Palette(
    name="light",
    window="#f4f5f7",
    surface="#ffffff",
    surface_alt="#f0f2f5",
    border="#dde1e7",
    border_strong="#c4cad3",
    text="#1b1f26",
    text_muted="#697386",
    accent="#e02424",
    accent_hover="#c81e1e",
    accent_text="#ffffff",
    success="#1f9d55",
    warning="#b7791f",
    danger="#d64545",
    track="#e6e9ee",
)


def palette_for(name: str) -> Palette:
    return LIGHT if name == "light" else DARK


def stylesheet(p: Palette) -> str:
    """The whole app's QSS, generated from one palette."""
    return f"""
    QMainWindow, QDialog {{
        background-color: {p.window};
    }}
    QWidget {{
        color: {p.text};
        font-size: 13px;
    }}
    QLabel, QCheckBox {{
        background: transparent;
    }}
    QToolTip {{
        background-color: {p.surface_alt};
        color: {p.text};
        border: 1px solid {p.border};
        padding: 4px 6px;
    }}

    /* ---- Cards ---------------------------------------------------- */
    QFrame#Card {{
        background-color: {p.surface};
        border: 1px solid {p.border};
        border-radius: 12px;
    }}
    QFrame#HeaderBar {{
        background-color: {p.surface};
        border-bottom: 1px solid {p.border};
    }}
    QLabel#AppTitle {{
        font-size: 17px;
        font-weight: 600;
    }}
    QLabel#AppSubtitle, QLabel#Muted {{
        color: {p.text_muted};
    }}
    QLabel#SectionTitle {{
        font-size: 14px;
        font-weight: 600;
    }}
    QLabel#Brand {{
        color: {p.accent};
        font-size: 20px;
        font-weight: 700;
    }}
    QLabel#VideoTitle {{
        font-size: 15px;
        font-weight: 600;
    }}
    QLabel#StatValue {{
        font-size: 15px;
        font-weight: 600;
    }}
    QLabel#StatLabel {{
        color: {p.text_muted};
        font-size: 11px;
        letter-spacing: 1px;
    }}

    /* ---- Tabs ----------------------------------------------------- */
    QTabWidget::pane {{
        border: none;
        top: -1px;
    }}
    QTabBar::tab {{
        background: transparent;
        color: {p.text_muted};
        padding: 9px 18px;
        margin-right: 4px;
        border: 1px solid transparent;
        border-radius: 8px;
        font-weight: 500;
    }}
    QTabBar::tab:hover {{
        color: {p.text};
        background: {p.surface_alt};
    }}
    QTabBar::tab:selected {{
        color: {p.text};
        background: {p.surface};
        border: 1px solid {p.border};
    }}

    /* ---- Inputs --------------------------------------------------- */
    QLineEdit, QComboBox, QSpinBox {{
        background-color: {p.surface_alt};
        border: 1px solid {p.border};
        border-radius: 8px;
        padding: 8px 10px;
        selection-background-color: {p.accent};
        selection-color: {p.accent_text};
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
        border: 1px solid {p.accent};
    }}
    QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{
        color: {p.text_muted};
    }}
    QLineEdit#PathField {{
        color: {p.text_muted};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 22px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {p.surface};
        border: 1px solid {p.border};
        selection-background-color: {p.accent};
        selection-color: {p.accent_text};
        outline: none;
    }}

    /* ---- Buttons -------------------------------------------------- */
    QPushButton {{
        background-color: {p.surface_alt};
        border: 1px solid {p.border_strong};
        border-radius: 8px;
        padding: 8px 16px;
        font-weight: 500;
    }}
    QPushButton:hover {{
        border-color: {p.accent};
        color: {p.accent};
    }}
    QPushButton:pressed {{
        background-color: {p.border};
    }}
    QPushButton:disabled {{
        color: {p.text_muted};
        border-color: {p.border};
        background-color: transparent;
    }}
    QPushButton#Primary {{
        background-color: {p.accent};
        color: {p.accent_text};
        border: 1px solid {p.accent};
        font-weight: 600;
    }}
    QPushButton#Primary:hover {{
        background-color: {p.accent_hover};
        border-color: {p.accent_hover};
        color: {p.accent_text};
    }}
    QPushButton#Primary:disabled {{
        background-color: {p.border};
        border-color: {p.border};
        color: {p.text_muted};
    }}
    QPushButton#Ghost {{
        background: transparent;
        border: 1px solid transparent;
        color: {p.text_muted};
        padding: 6px 10px;
    }}
    QPushButton#Ghost:hover {{
        color: {p.text};
        background: {p.surface_alt};
    }}

    /* ---- Progress ------------------------------------------------- */
    QProgressBar {{
        background-color: {p.track};
        border: none;
        border-radius: 5px;
        height: 10px;
        text-align: center;
        color: transparent;
    }}
    QProgressBar::chunk {{
        background-color: {p.accent};
        border-radius: 5px;
    }}

    /* ---- Table ---------------------------------------------------- */
    QTableView {{
        background-color: {p.surface};
        alternate-background-color: {p.surface_alt};
        border: 1px solid {p.border};
        border-radius: 10px;
        gridline-color: transparent;
        selection-background-color: {p.surface_alt};
        selection-color: {p.text};
        outline: none;
    }}
    QTableView::item {{
        padding: 6px 8px;
        border: none;
    }}
    QTableView#Queue {{
        min-height: 220px;
    }}
    QHeaderView::section {{
        background-color: {p.surface_alt};
        color: {p.text_muted};
        padding: 8px;
        border: none;
        border-bottom: 1px solid {p.border};
        font-weight: 600;
    }}
    QTableCornerButton::section {{
        background-color: {p.surface_alt};
        border: none;
    }}

    /* ---- Log view ------------------------------------------------- */
    QPlainTextEdit {{
        background-color: {p.surface_alt};
        border: 1px solid {p.border};
        border-radius: 8px;
        color: {p.text_muted};
        font-family: "JetBrains Mono", "DejaVu Sans Mono", Consolas, monospace;
        font-size: 11px;
    }}

    /* ---- Scrollbars ----------------------------------------------- */
    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        background: {p.border_strong};
        border-radius: 5px;
        min-height: 28px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {p.text_muted}; }}
    QScrollBar:horizontal {{
        background: transparent;
        height: 10px;
        margin: 2px;
    }}
    QScrollBar::handle:horizontal {{
        background: {p.border_strong};
        border-radius: 5px;
        min-width: 28px;
    }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

    /* ---- Misc ----------------------------------------------------- */
    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
    }}
    QStatusBar {{
        background: {p.surface};
        border-top: 1px solid {p.border};
        color: {p.text_muted};
    }}
    QStatusBar::item {{ border: none; }}
    QSplitter::handle {{ background: transparent; }}
    """


def apply_qt_palette(app, p: Palette) -> None:
    """Tint the widgets Qt draws itself (checkmarks, arrows) to match the theme.

    A stylesheet cannot reach these; without it a dark theme keeps light-grey
    check indicators and dropdown arrows.
    """
    from PySide6.QtGui import QColor, QPalette

    role = QPalette.ColorRole
    group = QPalette.ColorGroup
    qp = QPalette()
    qp.setColor(role.Window, QColor(p.window))
    qp.setColor(role.WindowText, QColor(p.text))
    qp.setColor(role.Base, QColor(p.surface_alt))
    qp.setColor(role.AlternateBase, QColor(p.surface))
    qp.setColor(role.Text, QColor(p.text))
    qp.setColor(role.Button, QColor(p.surface_alt))
    qp.setColor(role.ButtonText, QColor(p.text))
    qp.setColor(role.Highlight, QColor(p.accent))
    qp.setColor(role.HighlightedText, QColor(p.accent_text))
    qp.setColor(role.ToolTipBase, QColor(p.surface_alt))
    qp.setColor(role.ToolTipText, QColor(p.text))
    qp.setColor(role.PlaceholderText, QColor(p.text_muted))
    qp.setColor(group.Disabled, role.Text, QColor(p.text_muted))
    qp.setColor(group.Disabled, role.ButtonText, QColor(p.text_muted))
    qp.setColor(group.Disabled, role.WindowText, QColor(p.text_muted))
    app.setPalette(qp)
