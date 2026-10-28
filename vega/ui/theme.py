BG, PANEL, PANEL2, BORDER = "#0a0a0c", "#111114", "#17171b", "#26262c"
TEXT, MUTED = "#e8e8ec", "#8a8a95"
STATE_COLORS = {"idle": "#6c6c78", "listening": "#6fd0ff", "thinking": "#c3b2ff", "speaking": "#f2f2f7"}
STATE_LABELS = {"idle": "IDLE", "listening": "LISTENING", "thinking": "THINKING", "speaking": "SPEAKING"}

QSS = f"""
* {{ font-family: "Segoe UI", "Inter", sans-serif; font-size: 13px; color: {TEXT}; }}
QMainWindow, QDialog, QWidget#root {{ background: {BG}; }}
QLabel#title {{ font-size: 15px; font-weight: 600; letter-spacing: 6px; color: {TEXT}; }}
QLabel#hint {{ color: {MUTED}; font-size: 12px; }}
QTextBrowser {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 12px; padding: 10px;
               selection-background-color: #34343f; }}
QLineEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{ background: {PANEL2}; border: 1px solid {BORDER};
               border-radius: 10px; padding: 8px 12px; selection-background-color: #34343f; }}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{ border: 1px solid #5a5a68; }}
QComboBox QAbstractItemView {{ background: {PANEL2}; border: 1px solid {BORDER}; selection-background-color: #2a2a33; }}
QPushButton {{ background: {PANEL2}; border: 1px solid {BORDER}; border-radius: 10px; padding: 8px 16px; }}
QPushButton:hover {{ background: #202027; border-color: #3a3a45; }}
QPushButton:pressed {{ background: #2a2a33; }}
QPushButton#icon {{ padding: 6px 10px; font-size: 15px; }}
QPushButton#mic {{ border-radius: 22px; min-width: 44px; max-width: 44px; min-height: 44px; max-height: 44px;
               font-size: 18px; padding: 0; }}
QPushButton#mic:checked {{ background: #123344; border: 1px solid #6fd0ff; }}
QPushButton#primary {{ background: #e8e8ec; color: #0a0a0c; border: none; font-weight: 600; }}
QPushButton#primary:hover {{ background: #ffffff; }}
QPushButton#danger {{ background: #3a1517; border: 1px solid #6b2a2e; }}
QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 10px; top: -1px; }}
QTabBar::tab {{ background: transparent; padding: 8px 16px; color: {MUTED}; }}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {TEXT}; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px; border: 1px solid #4a4a56; background: {PANEL2}; }}
QCheckBox::indicator:checked {{ background: #e8e8ec; }}
QSlider::groove:horizontal {{ height: 4px; background: {BORDER}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {TEXT}; width: 14px; margin: -6px 0; border-radius: 7px; }}
QSlider::sub-page:horizontal {{ background: #8a8a95; border-radius: 2px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; }}
QScrollBar::handle:vertical {{ background: #2c2c34; border-radius: 5px; min-height: 30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QToolTip {{ background: {PANEL2}; color: {TEXT}; border: 1px solid {BORDER}; }}
QMenu {{ background: {PANEL2}; border: 1px solid {BORDER}; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 6px; }} QMenu::item:selected {{ background: #2a2a33; }}
"""
