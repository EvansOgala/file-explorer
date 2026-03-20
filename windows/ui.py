from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk

from file_ops import FileOpError, copy_path, create_file, create_folder, delete_path, move_path, rename_path
from models import Entry, filter_entries, get_linux_partitions, human_size, scan_directory, sort_entries
from settings import load_settings, save_settings
from gtk_style import install_material_smooth_css


class FileExplorerApp(Gtk.Application):
    def __init__(self, start_path: Path | None = None):
        super().__init__(application_id="org.evans.FileExplorer")
        self.window: Gtk.ApplicationWindow | None = None

        self.settings = load_settings()
        self.start_path_override = start_path
        self.theme_values = ["dark", "light"]
        self.css_provider = None

        configured = Path(self.settings.get("start_path", str(Path.home()))).expanduser()
        if self.start_path_override is not None:
            self.current_path = self.start_path_override.expanduser()
        else:
            self.current_path = configured if configured.is_dir() else Path.home()

        self.path_entry: Gtk.Entry | None = None
        self.search_entry: Gtk.Entry | None = None
        self.hidden_switch: Gtk.Switch | None = None
        self.theme_dropdown: Gtk.DropDown | None = None

        self.favorites_list: Gtk.ListBox | None = None
        self.partition_list: Gtk.ListBox | None = None
        self.entry_list: Gtk.ListBox | None = None
        self.preview_view: Gtk.TextView | None = None
        self.status_label: Gtk.Label | None = None

        self.entries: list[Entry] = []
        self.row_path_map: dict[str, Path] = {}
        self.context_popover: Gtk.Popover | None = None
        self.context_target_path: Path | None = None

    def do_activate(self):
        if self.window is None:
            self._build_ui()
            self._refresh_favorites()
            self._refresh_partitions()
            self._load_directory(self.current_path)
        self.window.present()

    def _build_ui(self):
        self.window = Gtk.ApplicationWindow(application=self)
        self.window.set_title("File Explorer")
        self.window.set_default_size(1280, 840)
        self.css_provider = install_material_smooth_css(self.window)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        root.set_margin_top(12)
        root.set_margin_bottom(12)
        root.set_margin_start(12)
        root.set_margin_end(12)
        self.window.set_child(root)

        title = Gtk.Label(label="File Explorer")
        title.set_xalign(0.0)
        title.add_css_class("title-2")
        root.append(title)

        subtitle = Gtk.Label(label="GTK4 explorer with favorites, search, preview, and file operations")
        subtitle.set_xalign(0.0)
        subtitle.add_css_class("dim-label")
        root.append(subtitle)

        nav = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        root.append(nav)

        self.path_entry = Gtk.Entry()
        self.path_entry.set_hexpand(True)
        self.path_entry.connect("activate", lambda _e: self._go_to_path())
        nav.append(self.path_entry)

        go_btn = Gtk.Button(label="Go")
        go_btn.connect("clicked", lambda _b: self._go_to_path())
        nav.append(go_btn)

        up_btn = Gtk.Button(label="Up")
        up_btn.connect("clicked", lambda _b: self._go_up())
        nav.append(up_btn)

        refresh_btn = Gtk.Button(label="Refresh")
        refresh_btn.connect("clicked", lambda _b: self._refresh_active_list())
        nav.append(refresh_btn)

        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        root.append(controls)

        controls.append(Gtk.Label(label="Search"))
        self.search_entry = Gtk.Entry()
        self.search_entry.set_hexpand(True)
        self.search_entry.set_placeholder_text("Filter by filename")
        self.search_entry.connect("changed", lambda _e: self._refresh_active_list())
        controls.append(self.search_entry)

        controls.append(Gtk.Label(label="Show hidden"))
        self.hidden_switch = Gtk.Switch()
        self.hidden_switch.set_active(bool(self.settings.get("show_hidden", False)))
        self.hidden_switch.connect("notify::active", self._on_toggle_hidden)
        controls.append(self.hidden_switch)

        controls.append(Gtk.Label(label="Theme"))
        self.theme_dropdown = Gtk.DropDown.new_from_strings(self.theme_values)
        self._set_dropdown_value(self.theme_dropdown, self.theme_values, self.settings.get("theme", "dark"))
        self.theme_dropdown.connect("notify::selected", self._on_theme_changed)
        controls.append(self.theme_dropdown)

        body = Gtk.Paned.new(Gtk.Orientation.HORIZONTAL)
        body.set_hexpand(True)
        body.set_vexpand(True)
        root.append(body)

        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        sidebar.set_size_request(290, -1)
        body.set_start_child(sidebar)

        fav_frame = Gtk.Frame(label="Favorites")
        sidebar.append(fav_frame)

        fav_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        fav_box.set_margin_top(8)
        fav_box.set_margin_bottom(8)
        fav_box.set_margin_start(8)
        fav_box.set_margin_end(8)
        fav_frame.set_child(fav_box)

        fav_scroller = Gtk.ScrolledWindow()
        fav_scroller.set_hexpand(True)
        fav_scroller.set_vexpand(True)
        fav_box.append(fav_scroller)

        self.favorites_list = Gtk.ListBox()
        self.favorites_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.favorites_list.connect("row-activated", self._open_favorite)
        fav_scroller.set_child(self.favorites_list)

        fav_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        fav_box.append(fav_actions)

        add_fav_btn = Gtk.Button(label="Add Current")
        add_fav_btn.connect("clicked", lambda _b: self._add_favorite())
        fav_actions.append(add_fav_btn)

        rm_fav_btn = Gtk.Button(label="Remove")
        rm_fav_btn.connect("clicked", lambda _b: self._remove_favorite())
        fav_actions.append(rm_fav_btn)

        part_frame = Gtk.Frame(label="Partitions")
        sidebar.append(part_frame)

        part_scroller = Gtk.ScrolledWindow()
        part_scroller.set_hexpand(True)
        part_scroller.set_vexpand(True)
        part_frame.set_child(part_scroller)

        self.partition_list = Gtk.ListBox()
        self.partition_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.partition_list.connect("row-activated", self._open_partition)
        part_scroller.set_child(self.partition_list)

        main_area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        body.set_end_child(main_area)

        ops = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        main_area.append(ops)

        for label, fn in (
            ("Open", self._open_selected),
            ("Open as Root", self._open_selected_as_root),
            ("New Folder", self._new_folder),
            ("New File", self._new_file),
            ("Rename", self._rename_selected),
            ("Delete", self._delete_selected),
            ("Copy", self._copy_selected),
            ("Move", self._move_selected),
        ):
            btn = Gtk.Button(label=label)
            btn.connect("clicked", lambda _b, cb=fn: cb())
            ops.append(btn)

        split = Gtk.Paned.new(Gtk.Orientation.HORIZONTAL)
        split.set_hexpand(True)
        split.set_vexpand(True)
        main_area.append(split)

        list_frame = Gtk.Frame(label="Entries")
        split.set_start_child(list_frame)

        list_scroller = Gtk.ScrolledWindow()
        list_scroller.set_hexpand(True)
        list_scroller.set_vexpand(True)
        list_frame.set_child(list_scroller)

        self.entry_list = Gtk.ListBox()
        self.entry_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.entry_list.set_activate_on_single_click(False)
        self.entry_list.connect("row-selected", self._on_entry_selected)
        self.entry_list.connect("row-activated", self._on_entry_activated)
        list_scroller.set_child(self.entry_list)

        preview_frame = Gtk.Frame(label="Preview")
        split.set_end_child(preview_frame)

        preview_scroller = Gtk.ScrolledWindow()
        preview_scroller.set_hexpand(True)
        preview_scroller.set_vexpand(True)
        preview_frame.set_child(preview_scroller)

        self.preview_view = Gtk.TextView()
        self.preview_view.set_editable(False)
        self.preview_view.set_monospace(True)
        preview_scroller.set_child(self.preview_view)

        self.status_label = Gtk.Label(label="Ready")
        self.status_label.set_xalign(0.0)
        self.status_label.add_css_class("dim-label")
        root.append(self.status_label)

        self._apply_theme(self.settings.get("theme", "dark"))

    def _set_status(self, text: str):
        if self.status_label is not None:
            self.status_label.set_text(text)

    def _set_preview(self, text: str):
        if self.preview_view is not None:
            self.preview_view.get_buffer().set_text(text)

    def _refresh_partitions(self):
        if self.partition_list is None:
            return
        self._clear_listbox(self.partition_list)
        for mountpoint, device, fstype in get_linux_partitions():
            row = Gtk.ListBoxRow()
            row.set_child(Gtk.Label(label=f"{mountpoint} ({device}, {fstype})", xalign=0.0))
            self.partition_list.append(row)

    def _refresh_favorites(self):
        if self.favorites_list is None:
            return
        self._clear_listbox(self.favorites_list)
        favorites = self.settings.get("favorites", [])
        if not isinstance(favorites, list):
            favorites = []
        self.settings["favorites"] = favorites

        for path in favorites:
            row = Gtk.ListBoxRow()
            row.set_child(Gtk.Label(label=str(path), xalign=0.0))
            self.favorites_list.append(row)

    def _open_favorite(self, _listbox: Gtk.ListBox, row: Gtk.ListBoxRow):
        child = row.get_child()
        if not isinstance(child, Gtk.Label):
            return
        path = Path(child.get_text()).expanduser()
        self._load_directory(path)

    def _open_partition(self, _listbox: Gtk.ListBox, row: Gtk.ListBoxRow):
        child = row.get_child()
        if not isinstance(child, Gtk.Label):
            return
        text = child.get_text()
        mountpoint = text.split(" ", 1)[0]
        self._load_directory(Path(mountpoint))

    def _on_theme_changed(self, dropdown: Gtk.DropDown, _param):
        self._apply_theme(self._get_dropdown_value(dropdown, self.theme_values))

    def _apply_theme(self, theme_name: str):
        if theme_name not in {"dark", "light"}:
            theme_name = "dark"
        self.settings["theme"] = theme_name
        save_settings(self.settings)

        gtk_settings = Gtk.Settings.get_default()
        if gtk_settings is not None:
            gtk_settings.set_property("gtk-application-prefer-dark-theme", theme_name == "dark")

    def _on_toggle_hidden(self, _switch: Gtk.Switch, _param):
        self.settings["show_hidden"] = bool(self.hidden_switch.get_active()) if self.hidden_switch else False
        save_settings(self.settings)
        self._refresh_active_list()

    def _go_to_path(self):
        if self.path_entry is None:
            return
        target = Path(self.path_entry.get_text().strip()).expanduser()
        self._load_directory(target)

    def _go_up(self):
        self._load_directory(self.current_path.parent)

    def _refresh_active_list(self):
        self._load_directory(self.current_path)

    def _load_directory(self, path: Path):
        try:
            path = path.expanduser().resolve()
        except Exception:  # noqa: BLE001
            path = Path.home()

        if not path.exists() or not path.is_dir():
            self._set_status(f"Invalid directory: {path}")
            return

        show_hidden = bool(self.settings.get("show_hidden", False))
        query = self.search_entry.get_text().strip() if self.search_entry else ""

        try:
            entries = scan_directory(path, include_hidden=show_hidden)
        except OSError as exc:
            if isinstance(exc, PermissionError):
                self._set_status(f"Permission denied: {path}. Use 'Open as Root'.")
            else:
                self._set_status(f"Failed to read {path}: {exc}")
            return

        entries = filter_entries(entries, query)
        entries = sort_entries(entries, "name")

        self.current_path = path
        self.entries = entries

        if self.path_entry is not None:
            self.path_entry.set_text(str(path))

        self.settings["start_path"] = str(path)
        save_settings(self.settings)

        self._render_entry_list(entries)
        self._set_preview("")
        self._set_status(f"Loaded {len(entries)} items from {path}")

    def _render_entry_list(self, entries: list[Entry]):
        if self.entry_list is None:
            return

        self._clear_listbox(self.entry_list)
        self.row_path_map.clear()

        for idx, entry in enumerate(entries):
            icon = "DIR" if entry.is_dir else "FILE"
            size = "-" if entry.is_dir else human_size(entry.size)
            mod = entry.modified.strftime("%Y-%m-%d %H:%M")
            line = f"{icon:<4}  {entry.name:<40.40}  {size:>10}  {mod}"

            row = Gtk.ListBoxRow()
            label = Gtk.Label(label=line, xalign=0.0)
            label.set_selectable(False)
            row.set_child(label)

            row_key = f"entry-{idx}"
            row.set_name(row_key)
            self.row_path_map[row_key] = entry.path

            right_click = Gtk.GestureClick()
            right_click.set_button(3)
            right_click.connect("pressed", self._on_entry_row_right_click, row)
            row.add_controller(right_click)
            self.entry_list.append(row)

    def _selected_path(self) -> Path | None:
        if self.entry_list is None:
            return None
        row = self.entry_list.get_selected_row()
        if row is None:
            return None
        return self.row_path_map.get(row.get_name() or "")

    def _on_entry_selected(self, _listbox: Gtk.ListBox, row: Gtk.ListBoxRow | None):
        if row is None:
            return
        path = self.row_path_map.get(row.get_name() or "")
        if path is not None:
            self._preview_path(path)

    def _on_entry_activated(self, _listbox: Gtk.ListBox, row: Gtk.ListBoxRow):
        path = self.row_path_map.get(row.get_name() or "")
        if path is not None:
            self._open_path(path)

    def _on_entry_row_right_click(self, _gesture: Gtk.GestureClick, _n_press: int, x: float, y: float, row: Gtk.ListBoxRow):
        if self.entry_list is None:
            return

        self.entry_list.select_row(row)
        path = self.row_path_map.get(row.get_name() or "")
        if path is None:
            return

        self.context_target_path = path
        self._show_context_menu(row, int(x), int(y))

    def _show_context_menu(self, row: Gtk.ListBoxRow, x: int, y: int):
        if self.entry_list is None:
            return

        if self.context_popover is not None:
            self.context_popover.popdown()
            self.context_popover = None

        popover = Gtk.Popover()
        popover.set_parent(row)
        rect = Gdk.Rectangle()
        rect.x = x
        rect.y = y
        rect.width = 1
        rect.height = 1
        popover.set_pointing_to(rect)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(8)
        box.set_margin_end(8)

        for label, callback in (
            ("Open", self._context_open),
            ("Open as Root", self._context_open_as_root),
            ("Rename", self._context_rename),
            ("Delete", self._context_delete),
            ("Copy", self._context_copy),
            ("Move", self._context_move),
            ("Properties", self._context_properties),
        ):
            btn = Gtk.Button(label=label)
            btn.set_halign(Gtk.Align.FILL)
            btn.connect("clicked", lambda _b, cb=callback: self._run_context_action(cb))
            box.append(btn)

        popover.set_child(box)
        popover.popup()
        self.context_popover = popover

    def _run_context_action(self, callback):
        if self.context_popover is not None:
            self.context_popover.popdown()
            self.context_popover = None
        callback()

    def _context_open(self):
        if self.context_target_path is not None:
            self._open_path(self.context_target_path)

    def _context_open_as_root(self):
        if self.context_target_path is not None:
            self._open_as_root(self.context_target_path)

    def _context_rename(self):
        self._rename_selected()

    def _context_delete(self):
        self._delete_selected()

    def _context_copy(self):
        self._copy_selected()

    def _context_move(self):
        self._move_selected()

    def _context_properties(self):
        path = self._selected_path()
        if path is not None:
            self._show_properties(path)

    def _open_selected(self):
        path = self._selected_path()
        if path is None:
            self._set_status("Select an entry first")
            return
        self._open_path(path)

    def _open_selected_as_root(self):
        path = self._selected_path() or self.current_path
        self._open_as_root(path)

    def _open_path(self, path: Path):
        if path.is_dir():
            self._load_directory(path)
            return
        try:
            subprocess.Popen(["xdg-open", str(path)])
            self._set_status(f"Opened file: {path}")
        except Exception as exc:  # noqa: BLE001
            self._set_status(f"Failed to open file: {exc}")

    def _open_as_root(self, path: Path):
        target = path.expanduser()

        if os.geteuid() == 0:
            if target.is_dir():
                self._load_directory(target)
            else:
                self._open_path(target)
            return

        if shutil.which("pkexec") is None:
            self._alert("Open as Root", "pkexec is not installed. Install polkit/pkexec to use this action.")
            return

        script_dir = Path(__file__).resolve().parent
        main_py = script_dir / "main.py"

        env_pairs = []
        for key in (
            "DISPLAY",
            "WAYLAND_DISPLAY",
            "XAUTHORITY",
            "XDG_RUNTIME_DIR",
            "DBUS_SESSION_BUS_ADDRESS",
            "XDG_CURRENT_DESKTOP",
            "DESKTOP_SESSION",
        ):
            value = os.environ.get(key)
            if value:
                env_pairs.append(f"{key}={value}")

        root_app_cmd = [
            "pkexec",
            "env",
            *env_pairs,
            f"PYTHONPATH={script_dir}",
            sys.executable,
            str(main_py),
            "--start-path",
            str(target),
        ]

        try:
            subprocess.Popen(root_app_cmd)
            self._set_status(f"Opened root session for: {target}")
            return
        except Exception:
            pass

        for fm in ("nautilus", "nemo", "thunar", "dolphin", "pcmanfm", "xdg-open"):
            if shutil.which(fm) is None:
                continue
            try:
                subprocess.Popen(["pkexec", fm, str(target)])
                self._set_status(f"Requested root open for: {target}")
                return
            except Exception:
                continue

        self._alert(
            "Open as Root",
            f"Failed to open as root: {target}\n"
            "Ensure your polkit agent is running and a file manager is installed.",
        )

    def _preview_path(self, path: Path):
        try:
            st = path.stat()
        except OSError as exc:
            self._set_preview(f"Preview error: {exc}")
            return

        mode = stat.filemode(st.st_mode)
        modified = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        created = datetime.fromtimestamp(st.st_ctime).strftime("%Y-%m-%d %H:%M:%S")
        kind = "Folder" if path.is_dir() else "File"
        size = "-" if path.is_dir() else human_size(st.st_size)

        header = (
            f"Name: {path.name}\n"
            f"Path: {path}\n"
            f"Type: {kind}\n"
            f"Size: {size}\n"
            f"Permissions: {mode}\n"
            f"Modified: {modified}\n"
            f"Created: {created}\n"
        )

        if path.is_dir():
            try:
                count = len(list(path.iterdir()))
            except OSError:
                count = -1
            extra = f"Items: {count if count >= 0 else 'N/A'}"
            self._set_preview(f"{header}\n{extra}")
            return

        text_preview = ""
        if st.st_size <= 2 * 1024 * 1024:
            try:
                text_preview = path.read_text(encoding="utf-8", errors="replace")[:12000]
            except OSError:
                text_preview = ""

        if text_preview:
            self._set_preview(f"{header}\n--- Content Preview ---\n{text_preview}")
        else:
            self._set_preview(header)

    def _show_properties(self, path: Path):
        try:
            st = path.stat()
        except OSError as exc:
            self._alert("Properties", str(exc))
            return

        mode = stat.filemode(st.st_mode)
        modified = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        created = datetime.fromtimestamp(st.st_ctime).strftime("%Y-%m-%d %H:%M:%S")
        info = (
            f"Name: {path.name}\n"
            f"Path: {path}\n"
            f"Type: {'Folder' if path.is_dir() else 'File'}\n"
            f"Size: {'-' if path.is_dir() else human_size(st.st_size)}\n"
            f"Permissions: {mode}\n"
            f"Modified: {modified}\n"
            f"Created: {created}"
        )
        self._alert("Properties", info)

    def _new_folder(self):
        name = self._prompt_text("New Folder", "Folder name")
        if not name:
            return
        try:
            create_folder(self.current_path, name)
            self._refresh_active_list()
            self._set_status(f"Folder created: {name}")
        except FileOpError as exc:
            self._alert("Create Folder", str(exc))

    def _new_file(self):
        name = self._prompt_text("New File", "File name")
        if not name:
            return
        try:
            create_file(self.current_path, name)
            self._refresh_active_list()
            self._set_status(f"File created: {name}")
        except FileOpError as exc:
            self._alert("Create File", str(exc))

    def _rename_selected(self):
        path = self._selected_path()
        if path is None:
            self._set_status("Select an entry first")
            return

        new_name = self._prompt_text("Rename", "New name", initial=path.name)
        if not new_name:
            return

        try:
            rename_path(path, new_name)
            self._refresh_active_list()
            self._set_status(f"Renamed to {new_name}")
        except FileOpError as exc:
            self._alert("Rename", str(exc))

    def _delete_selected(self):
        path = self._selected_path()
        if path is None:
            self._set_status("Select an entry first")
            return

        if not self._confirm("Delete", f"Delete '{path.name}'? This cannot be undone."):
            return

        try:
            delete_path(path)
            self._refresh_active_list()
            self._set_status(f"Deleted: {path.name}")
        except FileOpError as exc:
            self._alert("Delete", str(exc))

    def _copy_selected(self):
        path = self._selected_path()
        if path is None:
            self._set_status("Select an entry first")
            return

        dest_text = self._prompt_text("Copy To", "Destination directory", initial=str(self.current_path))
        if not dest_text:
            return

        destination = Path(dest_text).expanduser()
        if not destination.is_dir():
            self._alert("Copy", "Destination must be an existing directory")
            return

        try:
            copied = copy_path(path, destination)
            self._set_status(f"Copied to {copied}")
            self._refresh_active_list()
        except FileOpError as exc:
            self._alert("Copy", str(exc))

    def _move_selected(self):
        path = self._selected_path()
        if path is None:
            self._set_status("Select an entry first")
            return

        dest_text = self._prompt_text("Move To", "Destination directory", initial=str(self.current_path))
        if not dest_text:
            return

        destination = Path(dest_text).expanduser()
        if not destination.is_dir():
            self._alert("Move", "Destination must be an existing directory")
            return

        try:
            moved = move_path(path, destination)
            self._set_status(f"Moved to {moved}")
            self._refresh_active_list()
        except FileOpError as exc:
            self._alert("Move", str(exc))

    def _add_favorite(self):
        favorites = self.settings.get("favorites", [])
        if not isinstance(favorites, list):
            favorites = []

        current_str = str(self.current_path)
        if current_str not in favorites:
            favorites.append(current_str)
            self.settings["favorites"] = favorites
            save_settings(self.settings)
            self._refresh_favorites()
            self._set_status(f"Added favorite: {current_str}")

    def _remove_favorite(self):
        if self.favorites_list is None:
            return
        row = self.favorites_list.get_selected_row()
        if row is None:
            self._set_status("Select a favorite first")
            return

        child = row.get_child()
        if not isinstance(child, Gtk.Label):
            return
        path = child.get_text()

        favorites = self.settings.get("favorites", [])
        if isinstance(favorites, list) and path in favorites:
            favorites.remove(path)
            self.settings["favorites"] = favorites
            save_settings(self.settings)
            self._refresh_favorites()
            self._set_status(f"Removed favorite: {path}")

    def _alert(self, title: str, message: str):
        if self.window is None:
            return
        dialog = Gtk.Dialog(title=title, transient_for=self.window, modal=True)
        dialog.add_button("OK", Gtk.ResponseType.OK)
        content = dialog.get_content_area()
        label = Gtk.Label(label=message)
        label.set_wrap(True)
        label.set_xalign(0.0)
        label.set_margin_top(12)
        label.set_margin_bottom(12)
        label.set_margin_start(12)
        label.set_margin_end(12)
        content.append(label)
        self._run_dialog(dialog)

    def _confirm(self, title: str, message: str) -> bool:
        if self.window is None:
            return False
        dialog = Gtk.Dialog(title=title, transient_for=self.window, modal=True)
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Yes", Gtk.ResponseType.OK)
        content = dialog.get_content_area()
        label = Gtk.Label(label=message)
        label.set_wrap(True)
        label.set_xalign(0.0)
        label.set_margin_top(12)
        label.set_margin_bottom(12)
        label.set_margin_start(12)
        label.set_margin_end(12)
        content.append(label)
        response = self._run_dialog(dialog)
        return response == Gtk.ResponseType.OK

    def _prompt_text(self, title: str, label: str, initial: str = "") -> str | None:
        if self.window is None:
            return None

        dialog = Gtk.Dialog(title=title, transient_for=self.window, modal=True)
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("OK", Gtk.ResponseType.OK)

        content = dialog.get_content_area()
        wrap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        wrap.set_margin_top(12)
        wrap.set_margin_bottom(12)
        wrap.set_margin_start(12)
        wrap.set_margin_end(12)
        content.append(wrap)

        prompt = Gtk.Label(label=label)
        prompt.set_xalign(0.0)
        wrap.append(prompt)

        entry = Gtk.Entry()
        entry.set_text(initial)
        wrap.append(entry)

        response = self._run_dialog(dialog, focus_entry=entry)
        if response != Gtk.ResponseType.OK:
            return None

        value = entry.get_text().strip()
        return value or None

    def _run_dialog(self, dialog: Gtk.Dialog, focus_entry: Gtk.Entry | None = None):
        loop = GLib.MainLoop()
        result = {"response": Gtk.ResponseType.CANCEL}

        def on_response(_dialog, response_id):
            result["response"] = response_id
            dialog.destroy()
            loop.quit()

        dialog.connect("response", on_response)
        dialog.present()
        if focus_entry is not None:
            focus_entry.grab_focus()
        loop.run()
        return result["response"]

    @staticmethod
    def _set_dropdown_value(dropdown: Gtk.DropDown, values: list[str], value: str):
        try:
            idx = values.index(value)
        except ValueError:
            idx = 0
        dropdown.set_selected(idx)

    @staticmethod
    def _get_dropdown_value(dropdown: Gtk.DropDown, values: list[str]) -> str:
        idx = int(dropdown.get_selected())
        if 0 <= idx < len(values):
            return values[idx]
        return values[0]

    @staticmethod
    def _clear_listbox(box: Gtk.ListBox):
        child = box.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            box.remove(child)
            child = nxt
