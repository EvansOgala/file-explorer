from __future__ import annotations

import os
import string
from datetime import datetime
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from file_ops import FileOpError, copy_path, create_file, create_folder, delete_path, move_path, rename_path
from models import Entry, filter_entries, human_size, scan_directory, sort_entries
from settings import load_settings, save_settings

_LIGHT_QSS = """
QWidget {
  font-family: "Segoe UI Variable", "Segoe UI", "Inter", sans-serif;
  font-size: 13px;
  color: #1c2433;
}
QMainWindow { background: #eef2f7; }
QGroupBox {
  background: #ffffff;
  border: 1px solid rgba(27, 39, 64, 0.12);
  border-radius: 12px;
  margin-top: 10px;
  padding: 12px;
}
QGroupBox::title {
  subcontrol-origin: margin;
  left: 10px;
  padding: 0 6px 0 6px;
  color: #1c2433;
  font-weight: 600;
}
QLineEdit, QComboBox, QTextEdit, QListWidget {
  border: 1px solid rgba(27, 39, 64, 0.14);
  border-radius: 10px;
  padding: 7px 10px;
  background: #ffffff;
}
QPushButton {
  border-radius: 18px;
  padding: 7px 14px;
  background: #2b7cff;
  color: white;
  font-weight: 600;
}
QPushButton:disabled { background: rgba(120, 140, 170, 0.5); }
"""

_DARK_QSS = """
QWidget {
  font-family: "Segoe UI Variable", "Segoe UI", "Inter", sans-serif;
  font-size: 13px;
  color: #e6e9f2;
}
QMainWindow { background: #1b1f2a; }
QGroupBox {
  background: #232a36;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
  margin-top: 10px;
  padding: 12px;
}
QGroupBox::title {
  subcontrol-origin: margin;
  left: 10px;
  padding: 0 6px 0 6px;
  color: #e6e9f2;
  font-weight: 600;
}
QLineEdit, QComboBox, QTextEdit, QListWidget {
  border: 1px solid rgba(255, 255, 255, 0.16);
  border-radius: 10px;
  padding: 7px 10px;
  background: #1f2430;
  color: #e6e9f2;
}
QPushButton {
  border-radius: 18px;
  padding: 7px 14px;
  background: #3f7bff;
  color: white;
  font-weight: 600;
}
QPushButton:disabled { background: rgba(120, 140, 170, 0.45); }
"""


class FileExplorerQtWindow(QtWidgets.QMainWindow):
    def __init__(self, start_path: Path | None = None):
        super().__init__()
        self.setWindowTitle("File Explorer")
        self.resize(1260, 840)

        self.settings = load_settings()
        self.current_path = start_path or Path(self.settings.get("start_path", str(Path.home())))
        if not self.current_path.exists() or not self.current_path.is_dir():
            self.current_path = Path.home()

        self.row_path_map: dict[int, Path] = {}

        self._build_ui()
        self._apply_settings()
        self._refresh_favorites()
        self._refresh_drives()
        self._load_directory(self.current_path)

    def _build_ui(self):
        root = QtWidgets.QWidget()
        self.setCentralWidget(root)
        outer = QtWidgets.QVBoxLayout(root)
        outer.setContentsMargins(18, 18, 18, 18)
        outer.setSpacing(10)

        self.title_label = QtWidgets.QLabel("File Explorer")
        self.title_label.setStyleSheet("font-size: 26px; font-weight: 700;")
        self.subtitle_label = QtWidgets.QLabel("Windows-ready explorer with favorites, drives, and file operations")
        outer.addWidget(self.title_label)
        outer.addWidget(self.subtitle_label)

        nav = QtWidgets.QHBoxLayout()
        outer.addLayout(nav)
        self.path_entry = QtWidgets.QLineEdit()
        self.path_entry.returnPressed.connect(self._go_to_path)
        nav.addWidget(self.path_entry, 1)
        for text, fn in [("Go", self._go_to_path), ("Up", self._go_up), ("Refresh", self._refresh_active_list)]:
            btn = QtWidgets.QPushButton(text)
            btn.clicked.connect(fn)
            nav.addWidget(btn)

        controls = QtWidgets.QHBoxLayout()
        outer.addLayout(controls)
        controls.addWidget(QtWidgets.QLabel("Search"))
        self.search_entry = QtWidgets.QLineEdit()
        self.search_entry.setPlaceholderText("Filter by filename")
        self.search_entry.textChanged.connect(self._refresh_active_list)
        controls.addWidget(self.search_entry, 1)
        self.hidden_check = QtWidgets.QCheckBox("Show hidden")
        self.hidden_check.stateChanged.connect(self._on_toggle_hidden)
        controls.addWidget(self.hidden_check)
        controls.addWidget(QtWidgets.QLabel("Theme"))
        self.theme_box = QtWidgets.QComboBox()
        self.theme_box.addItems(["light", "dark"])
        self.theme_box.currentIndexChanged.connect(self._on_theme_changed)
        controls.addWidget(self.theme_box)

        body = QtWidgets.QHBoxLayout()
        outer.addLayout(body, 1)

        sidebar = QtWidgets.QVBoxLayout()
        body.addLayout(sidebar, 1)

        fav_box = QtWidgets.QGroupBox("Favorites")
        fav_layout = QtWidgets.QVBoxLayout(fav_box)
        self.favorites_list = QtWidgets.QListWidget()
        self.favorites_list.itemActivated.connect(self._open_favorite)
        fav_layout.addWidget(self.favorites_list, 1)
        fav_btns = QtWidgets.QHBoxLayout()
        add_f = QtWidgets.QPushButton("Add Current")
        add_f.clicked.connect(self._add_favorite)
        rm_f = QtWidgets.QPushButton("Remove")
        rm_f.clicked.connect(self._remove_favorite)
        fav_btns.addWidget(add_f)
        fav_btns.addWidget(rm_f)
        fav_layout.addLayout(fav_btns)
        sidebar.addWidget(fav_box, 1)

        drv_box = QtWidgets.QGroupBox("Drives")
        drv_layout = QtWidgets.QVBoxLayout(drv_box)
        self.drive_list = QtWidgets.QListWidget()
        self.drive_list.itemActivated.connect(self._open_drive)
        drv_layout.addWidget(self.drive_list)
        sidebar.addWidget(drv_box, 1)

        main = QtWidgets.QVBoxLayout()
        body.addLayout(main, 3)

        ops = QtWidgets.QHBoxLayout()
        main.addLayout(ops)
        for text, fn in [
            ("Open", self._open_selected),
            ("New Folder", self._new_folder),
            ("New File", self._new_file),
            ("Rename", self._rename_selected),
            ("Delete", self._delete_selected),
            ("Copy", self._copy_selected),
            ("Move", self._move_selected),
        ]:
            btn = QtWidgets.QPushButton(text)
            btn.clicked.connect(fn)
            ops.addWidget(btn)

        split = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        main.addWidget(split, 1)

        left_box = QtWidgets.QGroupBox("Entries")
        left_layout = QtWidgets.QVBoxLayout(left_box)
        self.entry_list = QtWidgets.QListWidget()
        self.entry_list.itemSelectionChanged.connect(self._on_entry_selected)
        self.entry_list.itemActivated.connect(self._on_entry_activated)
        self.entry_list.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.entry_list.customContextMenuRequested.connect(self._show_entry_context_menu)
        left_layout.addWidget(self.entry_list)
        split.addWidget(left_box)

        right_box = QtWidgets.QGroupBox("Preview")
        right_layout = QtWidgets.QVBoxLayout(right_box)
        self.preview_view = QtWidgets.QTextEdit()
        self.preview_view.setReadOnly(True)
        right_layout.addWidget(self.preview_view)
        split.addWidget(right_box)
        split.setSizes([800, 400])

        self.status_label = QtWidgets.QLabel("Ready")
        outer.addWidget(self.status_label)

    def _apply_settings(self):
        self.hidden_check.setChecked(bool(self.settings.get("show_hidden", False)))
        theme = self.settings.get("theme", "light")
        self.theme_box.setCurrentIndex(0 if theme == "light" else 1)
        self._apply_theme(theme)

    def _apply_theme(self, theme: str):
        app = QtWidgets.QApplication.instance()
        if app is None:
            return
        if theme == "dark":
            app.setStyle("Fusion")
            app.setStyleSheet(_DARK_QSS)
            self.title_label.setStyleSheet("font-size: 26px; font-weight: 700; color: #e6e9f2;")
            self.subtitle_label.setStyleSheet("color: rgba(230,233,242,0.72);")
            self.status_label.setStyleSheet("color: rgba(230,233,242,0.68);")
        else:
            app.setStyle("Fusion")
            app.setStyleSheet(_LIGHT_QSS)
            self.title_label.setStyleSheet("font-size: 26px; font-weight: 700; color: #1f2a44;")
            self.subtitle_label.setStyleSheet("color: rgba(30,40,60,0.72);")
            self.status_label.setStyleSheet("color: rgba(30,40,60,0.68);")

    def _set_status(self, text: str):
        self.status_label.setText(text)

    def _refresh_favorites(self):
        self.favorites_list.clear()
        favorites = self.settings.get("favorites", [])
        if not isinstance(favorites, list):
            favorites = []
        for path in favorites:
            self.favorites_list.addItem(str(path))

    def _refresh_drives(self):
        self.drive_list.clear()
        if os.name == "nt":
            for letter in string.ascii_uppercase:
                drive = Path(f"{letter}:\\")
                if drive.exists():
                    self.drive_list.addItem(str(drive))
        else:
            self.drive_list.addItem(str(Path("/")))
            self.drive_list.addItem(str(Path.home()))

    def _open_favorite(self, item: QtWidgets.QListWidgetItem):
        self._load_directory(Path(item.text()))

    def _open_drive(self, item: QtWidgets.QListWidgetItem):
        self._load_directory(Path(item.text()))

    def _on_theme_changed(self):
        theme = self.theme_box.currentText()
        self.settings["theme"] = theme
        save_settings(self.settings)
        self._apply_theme(theme)

    def _on_toggle_hidden(self):
        self.settings["show_hidden"] = bool(self.hidden_check.isChecked())
        save_settings(self.settings)
        self._refresh_active_list()

    def _go_to_path(self):
        self._load_directory(Path(self.path_entry.text().strip()))

    def _go_up(self):
        self._load_directory(self.current_path.parent)

    def _refresh_active_list(self):
        self._load_directory(self.current_path)

    def _load_directory(self, path: Path):
        try:
            path = path.expanduser().resolve()
        except Exception:
            path = Path.home()

        if not path.exists() or not path.is_dir():
            self._set_status(f"Invalid directory: {path}")
            return

        show_hidden = bool(self.settings.get("show_hidden", False))
        query = self.search_entry.text().strip()

        try:
            entries = scan_directory(path, include_hidden=show_hidden)
        except OSError as exc:
            self._set_status(f"Failed to read {path}: {exc}")
            return

        entries = filter_entries(entries, query)
        entries = sort_entries(entries, "name")

        self.current_path = path
        self.path_entry.setText(str(path))
        self.settings["start_path"] = str(path)
        save_settings(self.settings)

        self._render_entry_list(entries)
        self.preview_view.clear()
        self._set_status(f"Loaded {len(entries)} items from {path}")

    def _render_entry_list(self, entries: list[Entry]):
        self.entry_list.clear()
        self.row_path_map.clear()
        for idx, entry in enumerate(entries):
            icon = "DIR" if entry.is_dir else "FILE"
            size = "-" if entry.is_dir else human_size(entry.size)
            mod = entry.modified.strftime("%Y-%m-%d %H:%M")
            line = f"{icon:<4}  {entry.name:<40.40}  {size:>10}  {mod}"
            self.entry_list.addItem(line)
            self.row_path_map[idx] = entry.path

    def _selected_path(self) -> Path | None:
        row = self.entry_list.currentRow()
        if row < 0:
            return None
        return self.row_path_map.get(row)

    def _on_entry_selected(self):
        path = self._selected_path()
        if path is not None:
            self._preview_path(path)

    def _on_entry_activated(self):
        path = self._selected_path()
        if path is not None:
            self._open_path(path)

    def _show_entry_context_menu(self, pos: QtCore.QPoint):
        path = self._selected_path()
        if path is None:
            return
        menu = QtWidgets.QMenu(self)
        for label, callback in [
            ("Open", lambda: self._open_path(path)),
            ("Rename", self._rename_selected),
            ("Delete", self._delete_selected),
            ("Copy", self._copy_selected),
            ("Move", self._move_selected),
            ("Properties", lambda: self._show_properties(path)),
        ]:
            action = menu.addAction(label)
            action.triggered.connect(callback)
        menu.exec(self.entry_list.mapToGlobal(pos))

    def _open_selected(self):
        path = self._selected_path()
        if path is None:
            self._set_status("Select an entry first")
            return
        self._open_path(path)

    def _open_path(self, path: Path):
        if path.is_dir():
            self._load_directory(path)
            return
        try:
            if os.name == "nt":
                os.startfile(path)  # type: ignore[attr-defined]
            else:
                QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(path)))
            self._set_status(f"Opened file: {path}")
        except Exception as exc:
            self._set_status(f"Failed to open file: {exc}")

    def _preview_path(self, path: Path):
        try:
            st = path.stat()
        except OSError as exc:
            self.preview_view.setPlainText(f"Preview error: {exc}")
            return

        modified = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        created = datetime.fromtimestamp(st.st_ctime).strftime("%Y-%m-%d %H:%M:%S")
        kind = "Folder" if path.is_dir() else "File"
        size = "-" if path.is_dir() else human_size(st.st_size)

        header = (
            f"Name: {path.name}\n"
            f"Path: {path}\n"
            f"Type: {kind}\n"
            f"Size: {size}\n"
            f"Modified: {modified}\n"
            f"Created: {created}\n"
        )
        if path.is_dir():
            try:
                count = len(list(path.iterdir()))
            except OSError:
                count = -1
            self.preview_view.setPlainText(f"{header}\nItems: {count if count >= 0 else 'N/A'}")
            return

        text_preview = ""
        if st.st_size <= 2 * 1024 * 1024:
            try:
                text_preview = path.read_text(encoding="utf-8", errors="replace")[:12000]
            except OSError:
                text_preview = ""
        self.preview_view.setPlainText(f"{header}\n--- Content Preview ---\n{text_preview}" if text_preview else header)

    def _show_properties(self, path: Path):
        try:
            st = path.stat()
            modified = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            created = datetime.fromtimestamp(st.st_ctime).strftime("%Y-%m-%d %H:%M:%S")
            info = (
                f"Name: {path.name}\n"
                f"Path: {path}\n"
                f"Type: {'Folder' if path.is_dir() else 'File'}\n"
                f"Size: {'-' if path.is_dir() else human_size(st.st_size)}\n"
                f"Modified: {modified}\n"
                f"Created: {created}"
            )
            QtWidgets.QMessageBox.information(self, "Properties", info)
        except OSError as exc:
            QtWidgets.QMessageBox.warning(self, "Properties", str(exc))

    def _new_folder(self):
        name, ok = QtWidgets.QInputDialog.getText(self, "New Folder", "Folder name")
        if not ok or not name.strip():
            return
        try:
            create_folder(self.current_path, name.strip())
            self._refresh_active_list()
        except FileOpError as exc:
            QtWidgets.QMessageBox.warning(self, "Create Folder", str(exc))

    def _new_file(self):
        name, ok = QtWidgets.QInputDialog.getText(self, "New File", "File name")
        if not ok or not name.strip():
            return
        try:
            create_file(self.current_path, name.strip())
            self._refresh_active_list()
        except FileOpError as exc:
            QtWidgets.QMessageBox.warning(self, "Create File", str(exc))

    def _rename_selected(self):
        path = self._selected_path()
        if path is None:
            self._set_status("Select an entry first")
            return
        new_name, ok = QtWidgets.QInputDialog.getText(self, "Rename", "New name", text=path.name)
        if not ok or not new_name.strip():
            return
        try:
            rename_path(path, new_name.strip())
            self._refresh_active_list()
        except FileOpError as exc:
            QtWidgets.QMessageBox.warning(self, "Rename", str(exc))

    def _delete_selected(self):
        path = self._selected_path()
        if path is None:
            self._set_status("Select an entry first")
            return
        confirm = QtWidgets.QMessageBox.question(
            self,
            "Delete",
            f"Delete '{path.name}'? This cannot be undone.",
        )
        if confirm != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        try:
            delete_path(path)
            self._refresh_active_list()
        except FileOpError as exc:
            QtWidgets.QMessageBox.warning(self, "Delete", str(exc))

    def _copy_selected(self):
        path = self._selected_path()
        if path is None:
            self._set_status("Select an entry first")
            return
        destination = QtWidgets.QFileDialog.getExistingDirectory(self, "Copy To", str(self.current_path))
        if not destination:
            return
        try:
            copy_path(path, Path(destination))
            self._refresh_active_list()
        except FileOpError as exc:
            QtWidgets.QMessageBox.warning(self, "Copy", str(exc))

    def _move_selected(self):
        path = self._selected_path()
        if path is None:
            self._set_status("Select an entry first")
            return
        destination = QtWidgets.QFileDialog.getExistingDirectory(self, "Move To", str(self.current_path))
        if not destination:
            return
        try:
            move_path(path, Path(destination))
            self._refresh_active_list()
        except FileOpError as exc:
            QtWidgets.QMessageBox.warning(self, "Move", str(exc))

    def _add_favorite(self):
        favorites = self.settings.get("favorites", [])
        if not isinstance(favorites, list):
            favorites = []
        path = str(self.current_path)
        if path not in favorites:
            favorites.append(path)
            self.settings["favorites"] = favorites
            save_settings(self.settings)
            self._refresh_favorites()

    def _remove_favorite(self):
        item = self.favorites_list.currentItem()
        if item is None:
            self._set_status("Select a favorite first")
            return
        path = item.text()
        favorites = self.settings.get("favorites", [])
        if isinstance(favorites, list) and path in favorites:
            favorites.remove(path)
            self.settings["favorites"] = favorites
            save_settings(self.settings)
            self._refresh_favorites()


class FileExplorerQtApp:
    @staticmethod
    def run_app(start_path: Path | None = None):
        app = QtWidgets.QApplication([])
        app.setStyle("Fusion")
        window = FileExplorerQtWindow(start_path=start_path)
        icon_path = os.path.join(os.path.dirname(__file__), "org.evans.FileExplorer.svg")
        if os.path.exists(icon_path):
            window.setWindowIcon(QtGui.QIcon(icon_path))
        window.show()
        app.exec()
