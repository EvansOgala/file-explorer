import errno
import os
import shutil
import stat
import subprocess
import sys
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import ttk

try:
    import grp
    import pwd
except ImportError:  # Windows
    grp = None
    pwd = None

from file_ops import (
    FileOpError,
    copy_path,
    create_file,
    create_folder,
    delete_path,
    move_path,
    rename_path,
)
from models import filter_entries, get_linux_partitions, human_size, scan_directory, sort_entries
from settings import load_settings, save_settings

THEMES = {
    "dark": {
        "root_bg": "#0f172a",
        "panel_bg": "#111827",
        "card_bg": "#0b1220",
        "line": "#1f2937",
        "title": "#e2e8f0",
        "text": "#cbd5e1",
        "muted": "#94a3b8",
        "entry_bg": "#020617",
        "entry_fg": "#dbeafe",
        "button_bg": "#2563eb",
        "button_hover": "#3b82f6",
        "button_press": "#1d4ed8",
        "button_text": "#eff6ff",
        "select_bg": "#2563eb",
        "placeholder": "#64748b",
    },
    "light": {
        "root_bg": "#f1f5f9",
        "panel_bg": "#ffffff",
        "card_bg": "#f8fafc",
        "line": "#dbe3ee",
        "title": "#0f172a",
        "text": "#1e293b",
        "muted": "#475569",
        "entry_bg": "#ffffff",
        "entry_fg": "#0f172a",
        "button_bg": "#2563eb",
        "button_hover": "#3b82f6",
        "button_press": "#1d4ed8",
        "button_text": "#eff6ff",
        "select_bg": "#93c5fd",
        "placeholder": "#94a3b8",
    },
}


class PlaceholderEntry(ttk.Entry):
    def __init__(self, master, placeholder: str, textvariable: tk.StringVar, style: str):
        super().__init__(master, textvariable=textvariable, style=style)
        self.placeholder = placeholder
        self.var = textvariable
        self._is_placeholder = False
        self.placeholder_color = "#64748b"
        self.normal_color = "#dbeafe"
        self.bind("<FocusIn>", self._clear_placeholder)
        self.bind("<FocusOut>", self._show_placeholder)
        self._show_placeholder()

    def set_colors(self, normal: str, placeholder: str):
        self.normal_color = normal
        self.placeholder_color = placeholder
        if self._is_placeholder:
            self.configure(foreground=self.placeholder_color)
        else:
            self.configure(foreground=self.normal_color)

    def _show_placeholder(self, _event=None):
        if not self.var.get().strip():
            self.var.set(self.placeholder)
            self.configure(foreground=self.placeholder_color)
            self._is_placeholder = True

    def _clear_placeholder(self, _event=None):
        if self._is_placeholder:
            self.var.set("")
            self.configure(foreground=self.normal_color)
            self._is_placeholder = False

    def value(self) -> str:
        return "" if self._is_placeholder else self.var.get().strip()


class RoundedButton(tk.Canvas):
    def __init__(self, parent, text, command, width=120, height=34, radius=14):
        super().__init__(parent, width=width, height=height, bd=0, highlightthickness=0, relief="flat", cursor="hand2")
        self.command = command
        self.text = text
        self.width = width
        self.height = height
        self.radius = radius
        self.enabled = True
        self.pressed = False
        self.colors = {
            "bg": "#2563eb",
            "hover": "#3b82f6",
            "press": "#1d4ed8",
            "fg": "#eff6ff",
            "container": "#0f172a",
            "disabled": "#475569",
        }
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self._draw()

    def configure_theme(self, palette, container_bg):
        self.colors.update(
            {
                "bg": palette["button_bg"],
                "hover": palette["button_hover"],
                "press": palette["button_press"],
                "fg": palette["button_text"],
                "container": container_bg,
            }
        )
        self._draw()

    def set_enabled(self, enabled: bool):
        self.enabled = enabled
        self.config(cursor="hand2" if enabled else "arrow")
        self._draw()

    def _rounded(self, color):
        w, h, r = self.width, self.height, self.radius
        self.create_arc(0, 0, 2 * r, 2 * r, start=90, extent=90, fill=color, outline=color)
        self.create_arc(w - 2 * r, 0, w, 2 * r, start=0, extent=90, fill=color, outline=color)
        self.create_arc(0, h - 2 * r, 2 * r, h, start=180, extent=90, fill=color, outline=color)
        self.create_arc(w - 2 * r, h - 2 * r, w, h, start=270, extent=90, fill=color, outline=color)
        self.create_rectangle(r, 0, w - r, h, fill=color, outline=color)
        self.create_rectangle(0, r, w, h - r, fill=color, outline=color)

    def _draw(self):
        self.delete("all")
        self.configure(bg=self.colors["container"])
        if not self.enabled:
            color = self.colors["disabled"]
        elif self.pressed:
            color = self.colors["press"]
        else:
            color = self.colors["bg"]
        self._rounded(color)
        self.create_text(self.width // 2, self.height // 2, text=self.text, fill=self.colors["fg"], font=("Adwaita Sans", 10, "bold"))

    def _on_enter(self, _event):
        if self.enabled and not self.pressed:
            self.delete("all")
            self.configure(bg=self.colors["container"])
            self._rounded(self.colors["hover"])
            self.create_text(self.width // 2, self.height // 2, text=self.text, fill=self.colors["fg"], font=("Adwaita Sans", 10, "bold"))

    def _on_leave(self, _event):
        self.pressed = False
        self._draw()

    def _on_press(self, _event):
        if self.enabled:
            self.pressed = True
            self._draw()

    def _on_release(self, _event):
        if not self.enabled:
            return
        run = self.pressed
        self.pressed = False
        self._draw()
        if run:
            self.command()


class FileExplorerApp:
    def __init__(self, root: tk.Tk, start_path: Path | None = None):
        self.root = root
        self.root.title("Python File Explorer")
        self.root.geometry("1180x700")
        self.root.minsize(980, 620)

        self.settings = load_settings()
        self.theme_var = tk.StringVar(value=self.settings.get("theme", "dark"))
        self.show_hidden_var = tk.BooleanVar(value=self.settings.get("show_hidden", False))
        self.start_path_override = start_path
        self.is_flatpak = Path("/.flatpak-info").exists() or bool(os.environ.get("FLATPAK_ID"))
        self.flatpak_app_id = os.environ.get("FLATPAK_ID", "org.evans.FileExplorer")
        self.can_root_open = self._can_attempt_root_open()

        self.path_var = tk.StringVar()
        self.search_var = tk.StringVar()

        self.tab_state: dict[str, dict] = {}
        self.entries: list = []
        self.partition_rows: list[tuple[str, str, str]] = []

        self._build_ui()
        self._populate_tree_roots()
        self._refresh_partitions()
        self._schedule_partition_refresh()
        self._refresh_favorites()
        self._restore_tabs()
        self.apply_theme(self.theme_var.get())

    def _build_ui(self):
        self.style = ttk.Style()
        self.style.theme_use("clam")

        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)

        self.header = tk.Frame(self.root, padx=14, pady=12)
        self.header.grid(row=0, column=0, sticky="ew")
        self.header.columnconfigure(1, weight=1)

        self.title = tk.Label(self.header, text="File Explorer", font=("Adwaita Sans", 21, "bold"))
        self.title.grid(row=0, column=0, sticky="w")
        self.subtitle = tk.Label(self.header, text="Tabs, favorites, preview, and file operations", font=("Adwaita Sans", 10))
        self.subtitle.grid(row=1, column=0, sticky="w", pady=(2, 0))

        self.path_entry = PlaceholderEntry(
            self.header,
            "Enter folder path...",
            self.path_var,
            "App.TEntry",
        )
        self.path_entry.grid(row=0, column=1, rowspan=2, sticky="ew", padx=12)
        self.path_entry.bind("<Return>", lambda _e: self._go_to_path())

        self.theme_box = ttk.Combobox(
            self.header,
            textvariable=self.theme_var,
            values=("dark", "light"),
            width=8,
            state="readonly",
            style="App.TCombobox",
        )
        self.theme_box.grid(row=0, column=2, rowspan=2)
        self.theme_box.bind("<<ComboboxSelected>>", self._on_theme_change)

        self.toolbar = tk.Frame(self.root, padx=14, pady=6)
        self.toolbar.grid(row=1, column=0, sticky="ew")

        self.btn_new_tab = RoundedButton(self.toolbar, "New Tab", self._new_tab_from_dialog, width=100)
        self.btn_new_tab.pack(side="left")
        self.btn_close_tab = RoundedButton(self.toolbar, "Close Tab", self._close_active_tab, width=100)
        self.btn_close_tab.pack(side="left", padx=6)
        self.btn_up = RoundedButton(self.toolbar, "Up", self._go_up, width=72)
        self.btn_up.pack(side="left", padx=6)
        self.btn_go = RoundedButton(self.toolbar, "Go", self._go_to_path, width=72)
        self.btn_go.pack(side="left", padx=6)
        self.show_hidden_check = ttk.Checkbutton(
            self.toolbar,
            text="Show Hidden",
            variable=self.show_hidden_var,
            command=self._toggle_hidden,
            style="App.TCheckbutton",
        )
        self.show_hidden_check.pack(side="left", padx=(8, 2))

        self.search_entry = PlaceholderEntry(
            self.toolbar,
            "Search in tab...",
            self.search_var,
            "App.TEntry",
        )
        self.search_entry.pack(side="left", padx=(12, 0), fill="x", expand=True)
        self.search_entry.bind("<KeyRelease>", lambda _e: self._refresh_active_list())

        self.btn_sort_name = RoundedButton(self.toolbar, "Sort Name", lambda: self._set_sort("name"), width=94)
        self.btn_sort_name.pack(side="left", padx=(8, 4))
        self.btn_sort_size = RoundedButton(self.toolbar, "Sort Size", lambda: self._set_sort("size"), width=94)
        self.btn_sort_size.pack(side="left", padx=4)
        self.btn_sort_date = RoundedButton(self.toolbar, "Sort Date", lambda: self._set_sort("modified"), width=94)
        self.btn_sort_date.pack(side="left", padx=4)

        self.body = tk.Frame(self.root, padx=14, pady=6)
        self.body.grid(row=2, column=0, sticky="nsew", pady=(0, 10))
        self.body.columnconfigure(1, weight=1)
        self.body.rowconfigure(0, weight=1)

        self.sidebar = tk.Frame(self.body, width=300)
        self.sidebar.grid(row=0, column=0, sticky="nsw", padx=(0, 10))
        self.sidebar.grid_propagate(False)
        self.sidebar.rowconfigure(3, weight=0)
        self.sidebar.rowconfigure(6, weight=0)
        self.sidebar.rowconfigure(9, weight=1)

        self.side_title = tk.Label(self.sidebar, text="Sidebar", font=("Adwaita Sans", 13, "bold"))
        self.side_title.grid(row=0, column=0, sticky="w", padx=10, pady=(10, 4))

        ttk.Separator(self.sidebar, orient="horizontal").grid(row=1, column=0, sticky="ew", padx=10)

        self.fav_head = tk.Frame(self.sidebar)
        self.fav_head.grid(row=2, column=0, sticky="ew", padx=10, pady=(8, 4))
        self.fav_head.columnconfigure(0, weight=1)
        self.fav_label = tk.Label(self.fav_head, text="Favorites", font=("Adwaita Sans", 10, "bold"))
        self.fav_label.grid(row=0, column=0, sticky="w")
        self.btn_add_fav = RoundedButton(self.fav_head, "+", self._add_favorite, width=30, height=28, radius=12)
        self.btn_add_fav.grid(row=0, column=1, padx=2)
        self.btn_rm_fav = RoundedButton(self.fav_head, "-", self._remove_favorite, width=30, height=28, radius=12)
        self.btn_rm_fav.grid(row=0, column=2, padx=2)

        self.fav_list = tk.Listbox(self.sidebar, height=6, activestyle="none", borderwidth=0, highlightthickness=0)
        self.fav_list.grid(row=3, column=0, sticky="new", padx=10)
        self.fav_list.bind("<Double-1>", self._open_favorite)

        ttk.Separator(self.sidebar, orient="horizontal").grid(row=4, column=0, sticky="ew", padx=10, pady=(8, 6))

        self.part_head = tk.Frame(self.sidebar)
        self.part_head.grid(row=5, column=0, sticky="ew", padx=10, pady=(0, 4))
        self.part_head.columnconfigure(0, weight=1)
        self.part_label = tk.Label(self.part_head, text="Partitions", font=("Adwaita Sans", 10, "bold"))
        self.part_label.grid(row=0, column=0, sticky="w")
        self.btn_refresh_parts = RoundedButton(self.part_head, "↻", self._refresh_partitions, width=30, height=28, radius=12)
        self.btn_refresh_parts.grid(row=0, column=1, padx=2)

        self.partition_list = tk.Listbox(self.sidebar, height=5, activestyle="none", borderwidth=0, highlightthickness=0)
        self.partition_list.grid(row=6, column=0, sticky="ew", padx=10)
        self.partition_list.bind("<Double-1>", self._open_partition)

        ttk.Separator(self.sidebar, orient="horizontal").grid(row=7, column=0, sticky="ew", padx=10, pady=(8, 6))

        self.tree_label = tk.Label(self.sidebar, text="Folder Tree", font=("Adwaita Sans", 10, "bold"))
        self.tree_label.grid(row=8, column=0, sticky="w", padx=10)

        tree_frame = tk.Frame(self.sidebar)
        tree_frame.grid(row=9, column=0, sticky="nsew", padx=10, pady=(4, 10))
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(tree_frame, columns=("fullpath",), show="tree", style="App.Treeview")
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<<TreeviewOpen>>", self._on_tree_expand)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        tree_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        tree_scroll.grid(row=0, column=1, sticky="ns")

        right = tk.Frame(self.body)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(0, weight=1)
        right.rowconfigure(1, weight=0)
        right.columnconfigure(0, weight=1)

        self.notebook = ttk.Notebook(right)
        self.notebook.grid(row=0, column=0, sticky="nsew")
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        self.actions = tk.Frame(right, pady=8)
        self.actions.grid(row=1, column=0, sticky="ew")

        self.btn_new_folder = RoundedButton(self.actions, "New Folder", self._new_folder, width=110)
        self.btn_new_folder.pack(side="left")
        self.btn_new_file = RoundedButton(self.actions, "New File", self._new_file, width=100)
        self.btn_new_file.pack(side="left", padx=6)
        self.btn_rename = RoundedButton(self.actions, "Rename", self._rename_selected, width=94)
        self.btn_rename.pack(side="left", padx=6)
        self.btn_delete = RoundedButton(self.actions, "Delete", self._delete_selected, width=94)
        self.btn_delete.pack(side="left", padx=6)
        self.btn_copy = RoundedButton(self.actions, "Copy To", self._copy_selected, width=94)
        self.btn_copy.pack(side="left", padx=6)
        self.btn_move = RoundedButton(self.actions, "Move To", self._move_selected, width=94)
        self.btn_move.pack(side="left", padx=6)

        self.status_var = tk.StringVar(value="Ready")
        self.status = tk.Label(self.root, textvariable=self.status_var, anchor="w", padx=14, pady=6, font=("Adwaita Sans", 10))
        self.status.grid(row=3, column=0, sticky="ew")
        self._build_context_menu()

    def _build_context_menu(self):
        self.context_menu = tk.Menu(self.root, tearoff=False)
        self.context_menu.add_command(label="Open", command=self._context_open)
        self.context_menu.add_command(label="Open In New Tab", command=self._context_open_in_new_tab)
        root_label = "Open As Root (Host pkexec)" if self.is_flatpak else "Open As Root (pkexec)"
        self.context_menu.add_command(label=root_label, command=self._context_open_as_root)
        self.root_menu_index = self.context_menu.index("end")
        self.context_menu.add_separator()
        self.context_menu.add_command(label="New Folder Here", command=self._new_folder)
        self.context_menu.add_command(label="New File Here", command=self._new_file)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Rename", command=self._rename_selected)
        self.context_menu.add_command(label="Delete", command=self._delete_selected)
        self.context_menu.add_command(label="Copy To...", command=self._copy_selected)
        self.context_menu.add_command(label="Move To...", command=self._move_selected)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Duplicate", command=self._context_duplicate)
        self.context_menu.add_command(label="Copy Path", command=self._context_copy_path)
        self.context_menu.add_command(label="Add Folder To Favorites", command=self._context_add_folder_to_favorites)
        self.context_menu.add_command(label="Open Terminal Here", command=self._context_open_terminal_here)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Permissions...", command=self._context_permissions)
        self.context_menu.add_command(label="Properties...", command=self._context_properties)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Refresh", command=self._refresh_active_list)
        if not self.can_root_open:
            self.context_menu.entryconfig(self.root_menu_index, state="disabled")

    def _style_widgets(self, palette):
        self.style.configure(
            "App.TEntry",
            fieldbackground=palette["entry_bg"],
            foreground=palette["entry_fg"],
            bordercolor=palette["line"],
            insertcolor=palette["entry_fg"],
            padding=6,
            font=("Adwaita Sans", 10),
        )
        self.style.configure(
            "App.TCombobox",
            fieldbackground=palette["entry_bg"],
            foreground=palette["entry_fg"],
            bordercolor=palette["line"],
            padding=4,
            font=("Adwaita Sans", 10),
        )
        self.style.map("App.TCombobox", fieldbackground=[("readonly", palette["entry_bg"])], foreground=[("readonly", palette["entry_fg"])])
        self.style.configure(
            "App.TCheckbutton",
            background=palette["root_bg"],
            foreground=palette["title"],
            font=("Adwaita Sans", 10, "bold"),
            indicatorcolor=palette["entry_bg"],
            indicatormargin=4,
        )
        self.style.map(
            "App.TCheckbutton",
            background=[("active", palette["root_bg"])],
            foreground=[("disabled", palette["muted"])],
        )
        self.style.configure(
            "App.Treeview",
            background=palette["card_bg"],
            fieldbackground=palette["card_bg"],
            foreground=palette["text"],
            rowheight=28,
            borderwidth=0,
            font=("Adwaita Sans", 10),
        )
        self.style.map("App.Treeview", background=[("selected", palette["select_bg"])], foreground=[("selected", palette["title"])])
        self.style.configure(
            "App.Treeview.Heading",
            background=palette["panel_bg"],
            foreground=palette["title"],
            relief="flat",
            font=("Adwaita Sans", 10, "bold"),
        )

    def apply_theme(self, theme_name: str):
        theme_name = theme_name if theme_name in THEMES else "dark"
        self.theme_var.set(theme_name)
        self.settings["theme"] = theme_name
        save_settings(self.settings)

        p = THEMES[theme_name]
        self.palette = p
        self._style_widgets(p)

        self.root.configure(bg=p["root_bg"])
        self.header.configure(bg=p["root_bg"])
        self.title.configure(bg=p["root_bg"], fg=p["title"])
        self.subtitle.configure(bg=p["root_bg"], fg=p["muted"])

        self.toolbar.configure(bg=p["root_bg"])
        self.path_entry.set_colors(p["entry_fg"], p["placeholder"])
        self.search_entry.set_colors(p["entry_fg"], p["placeholder"])

        self.body.configure(bg=p["root_bg"])
        self.sidebar.configure(bg=p["panel_bg"], highlightbackground=p["line"], highlightthickness=1)
        self.fav_head.configure(bg=p["panel_bg"])
        self.part_head.configure(bg=p["panel_bg"])
        self.side_title.configure(bg=p["panel_bg"], fg=p["title"])
        self.fav_label.configure(bg=p["panel_bg"], fg=p["title"])
        self.part_label.configure(bg=p["panel_bg"], fg=p["title"])
        self.tree_label.configure(bg=p["panel_bg"], fg=p["title"])

        self.fav_list.configure(
            bg=p["card_bg"],
            fg=p["text"],
            selectbackground=p["select_bg"],
            selectforeground=p["title"],
        )
        self.partition_list.configure(
            bg=p["card_bg"],
            fg=p["text"],
            selectbackground=p["select_bg"],
            selectforeground=p["title"],
        )

        for panel in (self.actions,):
            panel.configure(bg=p["root_bg"])

        for btn in (
            self.btn_new_tab,
            self.btn_close_tab,
            self.btn_up,
            self.btn_go,
            self.btn_sort_name,
            self.btn_sort_size,
            self.btn_sort_date,
            self.btn_add_fav,
            self.btn_rm_fav,
            self.btn_refresh_parts,
            self.btn_new_folder,
            self.btn_new_file,
            self.btn_rename,
            self.btn_delete,
            self.btn_copy,
            self.btn_move,
        ):
            btn.configure_theme(p, btn.master.cget("bg"))

        self.status.configure(bg=p["root_bg"], fg=p["muted"])
        self.context_menu.configure(
            bg=p["panel_bg"],
            fg=p["text"],
            activebackground=p["select_bg"],
            activeforeground=p["title"],
            relief="flat",
            borderwidth=1,
        )

        # Apply theme to all tab widgets.
        for state in self.tab_state.values():
            state["frame"].configure(bg=p["panel_bg"])
            state["list_frame"].configure(bg=p["panel_bg"])
            state["preview_frame"].configure(bg=p["panel_bg"])
            state["preview_label"].configure(bg=p["panel_bg"], fg=p["title"])
            state["preview"].configure(bg=p["card_bg"], fg=p["text"], insertbackground=p["text"])

    def _show_modal(self, title: str, width: int = 460, height: int = 180) -> tuple[tk.Toplevel, tk.Frame]:
        p = getattr(self, "palette", THEMES["dark"])
        win = tk.Toplevel(self.root)
        win.title(title)
        win.geometry(f"{width}x{height}")
        win.minsize(width, height)
        win.configure(bg=p["root_bg"])
        win.transient(self.root)
        win.grab_set()

        body = tk.Frame(win, bg=p["panel_bg"], highlightbackground=p["line"], highlightthickness=1, padx=12, pady=12)
        body.pack(fill="both", expand=True, padx=10, pady=10)
        return win, body

    def _alert(self, title: str, message: str):
        win, body = self._show_modal(title, width=520, height=210)
        p = self.palette
        label = tk.Label(body, text=message, justify="left", anchor="nw", wraplength=470, bg=p["panel_bg"], fg=p["text"], font=("Adwaita Sans", 10))
        label.pack(fill="both", expand=True)
        btn = RoundedButton(body, "OK", win.destroy, width=90)
        btn.pack(anchor="e", pady=(10, 0))
        btn.configure_theme(p, body.cget("bg"))
        self.root.wait_window(win)

    def _confirm(self, title: str, message: str) -> bool:
        win, body = self._show_modal(title, width=520, height=220)
        p = self.palette
        result = {"ok": False}
        tk.Label(body, text=message, justify="left", anchor="nw", wraplength=470, bg=p["panel_bg"], fg=p["text"], font=("Adwaita Sans", 10)).pack(fill="both", expand=True)
        actions = tk.Frame(body, bg=p["panel_bg"])
        actions.pack(fill="x", pady=(8, 0))
        yes_btn = RoundedButton(actions, "Yes", lambda: (result.update(ok=True), win.destroy()), width=90)
        no_btn = RoundedButton(actions, "No", win.destroy, width=90)
        no_btn.pack(side="right")
        yes_btn.pack(side="right", padx=(0, 8))
        yes_btn.configure_theme(p, actions.cget("bg"))
        no_btn.configure_theme(p, actions.cget("bg"))
        self.root.wait_window(win)
        return result["ok"]

    def _prompt_text(self, title: str, label: str, initial: str = "") -> str | None:
        win, body = self._show_modal(title, width=520, height=220)
        p = self.palette
        result = {"value": None}
        var = tk.StringVar(value=initial)
        tk.Label(body, text=label, anchor="w", bg=p["panel_bg"], fg=p["title"], font=("Adwaita Sans", 10, "bold")).pack(fill="x")
        entry = ttk.Entry(body, textvariable=var, style="App.TEntry")
        entry.pack(fill="x", pady=(8, 0))
        entry.focus_set()

        def accept():
            text = var.get().strip()
            if text:
                result["value"] = text
            win.destroy()

        actions = tk.Frame(body, bg=p["panel_bg"])
        actions.pack(fill="x", pady=(12, 0))
        ok_btn = RoundedButton(actions, "OK", accept, width=90)
        cancel_btn = RoundedButton(actions, "Cancel", win.destroy, width=90)
        cancel_btn.pack(side="right")
        ok_btn.pack(side="right", padx=(0, 8))
        ok_btn.configure_theme(p, actions.cget("bg"))
        cancel_btn.configure_theme(p, actions.cget("bg"))
        self.root.wait_window(win)
        return result["value"]

    def _pick_directory(self, title: str, initial: Path | None = None) -> Path | None:
        current = (initial or Path.home()).expanduser()
        if not current.exists() or not current.is_dir():
            current = Path.home()

        win, body = self._show_modal(title, width=700, height=500)
        p = self.palette
        selected = {"path": None}
        path_var = tk.StringVar(value=str(current))

        top = tk.Frame(body, bg=p["panel_bg"])
        top.pack(fill="x")
        tk.Label(top, text="Folder", bg=p["panel_bg"], fg=p["title"], font=("Adwaita Sans", 10, "bold")).pack(side="left")
        entry = ttk.Entry(top, textvariable=path_var, style="App.TEntry")
        entry.pack(side="left", fill="x", expand=True, padx=8)

        content = tk.Frame(body, bg=p["panel_bg"])
        content.pack(fill="both", expand=True, pady=(10, 0))
        content.columnconfigure(0, weight=1)
        content.rowconfigure(0, weight=1)
        listbox = tk.Listbox(content, activestyle="none", borderwidth=0, highlightthickness=1, highlightbackground=p["line"], bg=p["card_bg"], fg=p["text"], selectbackground=p["select_bg"], selectforeground=p["title"])
        listbox.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(content, orient="vertical", command=listbox.yview)
        listbox.configure(yscrollcommand=scroll.set)
        scroll.grid(row=0, column=1, sticky="ns")

        def refresh_dirs():
            listbox.delete(0, tk.END)
            path = Path(path_var.get()).expanduser()
            if not path.exists() or not path.is_dir():
                return
            for child in sorted(path.iterdir(), key=lambda x: x.name.lower()):
                if child.is_dir():
                    listbox.insert(tk.END, child.name)

        def go_to():
            path = Path(path_var.get()).expanduser()
            if path.exists() and path.is_dir():
                path_var.set(str(path))
                refresh_dirs()
            else:
                self._alert("Invalid Folder", "Please enter a valid directory path.")

        def up():
            path = Path(path_var.get()).expanduser()
            parent = path.parent
            path_var.set(str(parent))
            refresh_dirs()

        def open_selected(_event=None):
            sel = listbox.curselection()
            if not sel:
                return
            path = Path(path_var.get()).expanduser() / listbox.get(sel[0])
            if path.is_dir():
                path_var.set(str(path))
                refresh_dirs()

        def choose_current():
            path = Path(path_var.get()).expanduser()
            if path.is_dir():
                selected["path"] = path
                win.destroy()

        listbox.bind("<Double-1>", open_selected)

        actions = tk.Frame(body, bg=p["panel_bg"])
        actions.pack(fill="x", pady=(10, 0))
        btn_go = RoundedButton(actions, "Go", go_to, width=74)
        btn_up = RoundedButton(actions, "Up", up, width=74)
        btn_select = RoundedButton(actions, "Select", choose_current, width=90)
        btn_cancel = RoundedButton(actions, "Cancel", win.destroy, width=90)
        btn_go.pack(side="left")
        btn_up.pack(side="left", padx=6)
        btn_cancel.pack(side="right")
        btn_select.pack(side="right", padx=(0, 8))
        for b in (btn_go, btn_up, btn_select, btn_cancel):
            b.configure_theme(p, actions.cget("bg"))

        refresh_dirs()
        self.root.wait_window(win)
        return selected["path"]

    def _show_properties(self, path: Path):
        try:
            st = path.stat()
        except OSError as exc:
            self._alert("Properties Error", str(exc))
            return

        mode_text = stat.filemode(st.st_mode)
        octal = oct(st.st_mode & 0o777)
        owner = str(st.st_uid)
        group = str(st.st_gid)
        if pwd:
            try:
                owner = pwd.getpwuid(st.st_uid).pw_name
            except KeyError:
                pass
        if grp:
            try:
                group = grp.getgrgid(st.st_gid).gr_name
            except KeyError:
                pass

        size = human_size(st.st_size) if path.is_file() else "-"
        modified = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        created = datetime.fromtimestamp(st.st_ctime).strftime("%Y-%m-%d %H:%M:%S")
        info = (
            f"Name: {path.name}\\n"
            f"Path: {path}\\n"
            f"Type: {'Folder' if path.is_dir() else 'File'}\\n"
            f"Size: {size}\\n"
            f"Owner: {owner}\\n"
            f"Group: {group}\\n"
            f"Permissions: {mode_text} ({octal})\\n"
            f"Modified: {modified}\\n"
            f"Created: {created}"
        )
        self._alert("Properties", info)

    def _show_permissions_dialog(self, path: Path):
        try:
            st = path.stat()
        except OSError as exc:
            self._alert("Permissions Error", str(exc))
            return

        win, body = self._show_modal("Permissions", width=520, height=250)
        p = self.palette
        mode_text = stat.filemode(st.st_mode)
        current_octal = f"{st.st_mode & 0o777:03o}"
        tk.Label(body, text=f"{path.name}", bg=p["panel_bg"], fg=p["title"], font=("Adwaita Sans", 11, "bold")).pack(anchor="w")
        tk.Label(body, text=f"Current: {mode_text} ({current_octal})", bg=p["panel_bg"], fg=p["text"], font=("Adwaita Sans", 10)).pack(anchor="w", pady=(4, 12))
        tk.Label(body, text="Set octal permissions (e.g. 755):", bg=p["panel_bg"], fg=p["title"], font=("Adwaita Sans", 10, "bold")).pack(anchor="w")
        octal_var = tk.StringVar(value=current_octal)
        entry = ttk.Entry(body, textvariable=octal_var, style="App.TEntry")
        entry.pack(fill="x", pady=(6, 0))

        def apply_mode():
            text = octal_var.get().strip()
            if len(text) != 3 or any(c not in "01234567" for c in text):
                self._alert("Invalid Mode", "Permission must be a 3-digit octal value, e.g. 644 or 755.")
                return
            try:
                path.chmod(int(text, 8))
            except OSError as exc:
                self._alert("chmod Failed", str(exc))
                return
            win.destroy()
            self.status_var.set(f"Permissions updated for {path.name}")

        actions = tk.Frame(body, bg=p["panel_bg"])
        actions.pack(fill="x", pady=(12, 0))
        apply_btn = RoundedButton(actions, "Apply", apply_mode, width=92)
        cancel_btn = RoundedButton(actions, "Cancel", win.destroy, width=92)
        cancel_btn.pack(side="right")
        apply_btn.pack(side="right", padx=(0, 8))
        apply_btn.configure_theme(p, actions.cget("bg"))
        cancel_btn.configure_theme(p, actions.cget("bg"))
        self.root.wait_window(win)

    def _can_attempt_root_open(self) -> bool:
        if os.name != "posix":
            return False
        if self.is_flatpak:
            return (
                shutil.which("flatpak-spawn") is not None
                and shutil.which("pkexec") is not None
                and shutil.which("flatpak") is not None
            )
        return shutil.which("pkexec") is not None

    def _is_permission_denied(self, exc: OSError) -> bool:
        if exc.errno == errno.EACCES:
            return True
        lowered = str(exc).lower()
        return "permission denied" in lowered

    def _request_root_open(self, path: Path):
        if os.name != "posix":
            self._alert("Permission Denied", "Administrator elevation is only supported on Linux/Unix.")
            return

        if not self.can_root_open:
            if self.is_flatpak:
                self._alert(
                    "Root Open Unavailable",
                    "Root elevation is unavailable in this Flatpak environment.\n"
                    "Run the host version of the app for full pkexec support.",
                )
            else:
                self._alert("pkexec Not Found", "Install pkexec (polkit) to open restricted paths as root.")
            return

        display = os.environ.get("DISPLAY", "")
        wayland_display = os.environ.get("WAYLAND_DISPLAY", "")
        xauthority = os.environ.get("XAUTHORITY", "")
        xdg_runtime = os.environ.get("XDG_RUNTIME_DIR", "")
        dbus_addr = os.environ.get("DBUS_SESSION_BUS_ADDRESS", "")
        env_args = []
        for key, value in (
            ("DISPLAY", display),
            ("WAYLAND_DISPLAY", wayland_display),
            ("XAUTHORITY", xauthority),
            ("XDG_RUNTIME_DIR", xdg_runtime),
            ("DBUS_SESSION_BUS_ADDRESS", dbus_addr),
        ):
            if value:
                env_args.append(f"{key}={value}")

        if self.is_flatpak:
            cmd = [
                "flatpak-spawn",
                "--host",
                "pkexec",
                "env",
                *env_args,
                "flatpak",
                "run",
                self.flatpak_app_id,
                "--start-path",
                str(path),
            ]
        else:
            app_main = Path(__file__).with_name("main.py")
            cmd = [
                "pkexec",
                "env",
                *env_args,
                f"PYTHONPATH={Path(__file__).parent}",
                sys.executable,
                str(app_main),
                "--start-path",
                str(path),
            ]

        try:
            subprocess.Popen(cmd)
            self.status_var.set(f"Opened elevated window for {path}")
        except OSError as err:
            self._alert("pkexec Failed", str(err))

    def _on_theme_change(self, _event=None):
        self.apply_theme(self.theme_var.get())

    def _toggle_hidden(self):
        self.settings["show_hidden"] = bool(self.show_hidden_var.get())
        save_settings(self.settings)
        for node in self.tree.get_children():
            self.tree.delete(node)
        self._populate_tree_roots()
        self._refresh_active_list()

    def _refresh_partitions(self):
        current = get_linux_partitions() if os.name == "posix" else []
        if current == self.partition_rows:
            return
        self.partition_rows = current
        self.partition_list.delete(0, tk.END)
        for mountpoint, device, fstype in current:
            label = f"{mountpoint}  [{fstype}]"
            if mountpoint == "/":
                label = f"/  (root)  [{fstype}]"
            self.partition_list.insert(tk.END, label)
        if not current and os.name != "posix":
            self.partition_list.insert(tk.END, "Partitions are Linux-only in this view")

    def _schedule_partition_refresh(self):
        self._refresh_partitions()
        self.root.after(4000, self._schedule_partition_refresh)

    def _open_partition(self, _event=None):
        sel = self.partition_list.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx < len(self.partition_rows):
            mountpoint = Path(self.partition_rows[idx][0])
            if mountpoint.is_dir():
                self._load_directory(mountpoint)

    def _populate_tree_roots(self):
        home = Path.home()
        root_node = self.tree.insert("", "end", text=str(home), values=(str(home),))
        self.tree.insert(root_node, "end", text="...")
        if os.name != "nt":
            root = Path("/")
            if root != home:
                node = self.tree.insert("", "end", text="/", values=("/",))
                self.tree.insert(node, "end", text="...")

    def _refresh_favorites(self):
        self.fav_list.delete(0, tk.END)
        for path in self.settings.get("favorites", []):
            self.fav_list.insert(tk.END, path)

    def _restore_tabs(self):
        if self.start_path_override and self.start_path_override.is_dir():
            self._create_tab(self.start_path_override)
            return

        recent = self.settings.get("recent_tabs", [])
        valid = [Path(p) for p in recent if Path(p).is_dir()]
        if not valid:
            valid = [Path(self.settings.get("start_path", str(Path.home())))]

        for path in valid[:5]:
            self._create_tab(path)

        if not self.notebook.tabs():
            self._create_tab(Path.home())

    def _create_tab(self, path: Path):
        frame = tk.Frame(self.notebook)
        frame.columnconfigure(0, weight=3)
        frame.columnconfigure(1, weight=2)
        frame.rowconfigure(0, weight=1)

        list_frame = tk.Frame(frame)
        list_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        list_view = ttk.Treeview(
            list_frame,
            columns=("name", "type", "size", "modified"),
            show="headings",
            style="App.Treeview",
        )
        list_view.heading("name", text="Name")
        list_view.heading("type", text="Type")
        list_view.heading("size", text="Size")
        list_view.heading("modified", text="Modified")
        list_view.column("name", width=340, anchor="w")
        list_view.column("type", width=90, anchor="center")
        list_view.column("size", width=110, anchor="e")
        list_view.column("modified", width=170, anchor="center")
        list_view.grid(row=0, column=0, sticky="nsew")
        list_view.bind("<Double-1>", self._on_list_double_click)
        list_view.bind("<<TreeviewSelect>>", self._on_list_select)
        list_view.bind("<Button-3>", self._on_list_right_click)

        list_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=list_view.yview)
        list_view.configure(yscrollcommand=list_scroll.set)
        list_scroll.grid(row=0, column=1, sticky="ns")

        preview_frame = tk.Frame(frame)
        preview_frame.grid(row=0, column=1, sticky="nsew")
        preview_frame.columnconfigure(0, weight=1)
        preview_frame.rowconfigure(1, weight=1)

        preview_label = tk.Label(preview_frame, text="Preview", font=("Adwaita Sans", 11, "bold"), anchor="w")
        preview_label.grid(row=0, column=0, sticky="ew")

        preview = tk.Text(preview_frame, wrap="word", font=("Adwaita Mono", 10), state="disabled")
        preview.grid(row=1, column=0, sticky="nsew", pady=(4, 0))

        tab_id = self.notebook.add(frame, text=path.name or str(path))
        tab_key = self.notebook.tabs()[-1]
        self.tab_state[tab_key] = {
            "frame": frame,
            "list_frame": list_frame,
            "preview_frame": preview_frame,
            "preview_label": preview_label,
            "preview": preview,
            "list": list_view,
            "path": path,
            "entries": [],
            "sort_key": "name",
            "sort_desc": False,
        }
        self.notebook.select(tab_key)
        self._load_directory(path, tab_key)

    def _active_tab_key(self):
        current = self.notebook.select()
        return current if current else None

    def _active_state(self):
        key = self._active_tab_key()
        return self.tab_state.get(key) if key else None

    def _on_tab_changed(self, _event=None):
        state = self._active_state()
        if not state:
            return
        self.path_var.set(str(state["path"]))
        self.search_var.set("")
        self._render_preview("Select a file to preview")

    def _load_directory(self, path: Path, tab_key: str | None = None):
        if tab_key is None:
            tab_key = self._active_tab_key()
        if not tab_key:
            return

        try:
            entries = scan_directory(
                path,
                include_hidden=bool(self.show_hidden_var.get()),
                hidden_skip_names={".local", ".cache"},
            )
        except OSError as exc:
            if self._is_permission_denied(exc):
                if self.can_root_open:
                    ask = self._confirm(
                        "Permission Required",
                        f"Permission denied for:\n{path}\n\nOpen this location in a root window with pkexec?",
                    )
                    if ask:
                        self._request_root_open(path)
                else:
                    if self.is_flatpak:
                        self._alert(
                            "Permission Denied",
                            f"Permission denied for:\n{path}\n\n"
                            "Root open is not available in this Flatpak sandbox.\n"
                            "Run the host app for full root support.",
                        )
                    else:
                        self._alert("Permission Denied", str(exc))
            else:
                self._alert("Open Folder Failed", str(exc))
            return

        state = self.tab_state[tab_key]
        state["path"] = path
        state["entries"] = entries

        self.path_var.set(str(path))
        self.settings["start_path"] = str(path)
        self._persist_tabs()
        save_settings(self.settings)

        self.notebook.tab(tab_key, text=path.name or str(path))
        self._refresh_tab_list(tab_key)
        self._render_preview("Select a file to preview")

    def _refresh_tab_list(self, tab_key: str):
        state = self.tab_state[tab_key]
        query = self.search_entry.value()
        filtered = filter_entries(state["entries"], query)
        sorted_entries = sort_entries(filtered, state["sort_key"], state["sort_desc"])

        list_view = state["list"]
        for item in list_view.get_children():
            list_view.delete(item)

        for e in sorted_entries:
            ftype = "Folder" if e.is_dir else (e.path.suffix[1:].upper() or "File")
            size = "-" if e.is_dir else human_size(e.size)
            mod = e.modified.strftime("%Y-%m-%d %H:%M")
            list_view.insert("", "end", iid=str(e.path), values=(e.name, ftype, size, mod))

        self.status_var.set(f"{len(sorted_entries)} items in {state['path']}")

    def _refresh_active_list(self):
        state = self._active_state()
        if state:
            self._load_directory(state["path"])

    def _on_tree_expand(self, _event):
        node = self.tree.focus()
        fullpath = Path(self.tree.item(node, "values")[0])
        children = self.tree.get_children(node)

        if len(children) == 1 and self.tree.item(children[0], "text") == "...":
            self.tree.delete(children[0])
            try:
                for child in sorted(fullpath.iterdir(), key=lambda p: p.name.lower()):
                    if child.name in {".local", ".cache"}:
                        continue
                    if not self.show_hidden_var.get() and child.name.startswith("."):
                        continue
                    if child.is_dir():
                        child_id = self.tree.insert(node, "end", text=child.name, values=(str(child),))
                        self.tree.insert(child_id, "end", text="...")
            except OSError:
                pass

    def _on_tree_select(self, _event):
        selected = self.tree.selection()
        if not selected:
            return
        node = selected[0]
        path = Path(self.tree.item(node, "values")[0])
        if path.is_dir():
            self._load_directory(path)

    def _selected_path(self) -> Path | None:
        state = self._active_state()
        if not state:
            return None
        selected = state["list"].selection()
        if not selected:
            return None
        return Path(selected[0])

    def _on_list_double_click(self, _event):
        target = self._selected_path()
        if target is None:
            return
        if target.is_dir():
            self._load_directory(target)
            return
        self._open_file(target)

    def _on_list_select(self, _event):
        target = self._selected_path()
        if target is None:
            self._render_preview("Select a file to preview")
            return
        self._preview_path(target)

    def _on_list_right_click(self, event):
        state = self._active_state()
        if not state:
            return
        row_id = state["list"].identify_row(event.y)
        if row_id:
            state["list"].selection_set(row_id)
            state["list"].focus(row_id)
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    def _context_open(self):
        target = self._selected_path()
        if not target:
            return
        if target.is_dir():
            self._load_directory(target)
        else:
            self._open_file(target)

    def _context_open_in_new_tab(self):
        target = self._selected_path()
        if target and target.is_dir():
            self._create_tab(target)
            self.apply_theme(self.theme_var.get())

    def _context_open_as_root(self):
        target = self._selected_path()
        if target and target.is_file():
            target = target.parent
        if not target:
            state = self._active_state()
            target = state["path"] if state else None
        if target:
            self._request_root_open(target)

    def _context_duplicate(self):
        target = self._selected_path()
        state = self._active_state()
        if not target or not state:
            return
        parent = state["path"]
        new_name = self._prompt_text("Duplicate", "Duplicate name:", initial=f"{target.stem}_copy{target.suffix}")
        if not new_name:
            return
        destination = parent / new_name
        if destination.exists():
            self._alert("Duplicate Failed", f"'{new_name}' already exists.")
            return
        try:
            if target.is_dir():
                shutil.copytree(target, destination)
            else:
                shutil.copy2(target, destination)
        except OSError as exc:
            self._alert("Duplicate Failed", str(exc))
            return
        self._load_directory(parent)

    def _context_copy_path(self):
        target = self._selected_path()
        if not target:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(str(target))
        self.status_var.set(f"Copied path: {target}")

    def _context_add_folder_to_favorites(self):
        target = self._selected_path()
        if not target or not target.is_dir():
            return
        favs = self.settings.setdefault("favorites", [])
        target_str = str(target)
        if target_str not in favs:
            favs.append(target_str)
            save_settings(self.settings)
            self._refresh_favorites()
            self.status_var.set(f"Added favorite: {target.name}")

    def _context_open_terminal_here(self):
        state = self._active_state()
        if not state:
            return
        cwd = state["path"]
        try:
            if os.name == "nt":
                subprocess.Popen(["cmd.exe"], cwd=str(cwd))
            else:
                subprocess.Popen(["x-terminal-emulator"], cwd=str(cwd))
        except Exception:
            try:
                subprocess.Popen(["gnome-terminal", "--working-directory", str(cwd)])
            except Exception as exc:  # noqa: BLE001
                self._alert("Terminal Error", str(exc))

    def _context_permissions(self):
        target = self._selected_path()
        if target:
            self._show_permissions_dialog(target)

    def _context_properties(self):
        target = self._selected_path()
        if target:
            self._show_properties(target)

    def _preview_path(self, path: Path):
        if path.is_dir():
            self._render_preview(f"Folder: {path.name}\n\nDouble-click to open.")
            return

        suffix = path.suffix.lower()
        if suffix in {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}:
            self._render_preview("Image preview is not implemented yet.\nDouble-click to open with system viewer.")
            return

        try:
            with path.open("r", encoding="utf-8", errors="replace") as f:
                content = f.read(8000)
        except OSError as exc:
            self._render_preview(f"Preview unavailable:\n{exc}")
            return

        if len(content) >= 8000:
            content += "\n\n... (truncated)"
        self._render_preview(content)

    def _render_preview(self, text: str):
        state = self._active_state()
        if not state:
            return
        preview = state["preview"]
        preview.configure(state="normal")
        preview.delete("1.0", tk.END)
        preview.insert("1.0", text)
        preview.configure(state="disabled")

    def _open_file(self, target: Path):
        try:
            if os.name == "nt":
                os.startfile(target)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(target)])
        except Exception as exc:  # noqa: BLE001
            self._alert("Open File Failed", str(exc))

    def _go_to_path(self):
        raw = self.path_entry.value()
        if not raw:
            return
        path = Path(raw).expanduser()
        if not path.exists() or not path.is_dir():
            self._alert("Invalid Path", "Please enter a valid directory path.")
            return
        self._load_directory(path)

    def _go_up(self):
        state = self._active_state()
        if not state:
            return
        parent = state["path"].parent
        if parent == state["path"]:
            return
        self._load_directory(parent)

    def _set_sort(self, key: str):
        state = self._active_state()
        if not state:
            return
        if state["sort_key"] == key:
            state["sort_desc"] = not state["sort_desc"]
        else:
            state["sort_key"] = key
            state["sort_desc"] = False
        self._refresh_active_list()

    def _new_tab_from_dialog(self):
        selected = self._pick_directory("Open Folder in New Tab", initial=Path(self.path_var.get() or Path.home()))
        if selected:
            self._create_tab(selected)
            self.apply_theme(self.theme_var.get())

    def _close_active_tab(self):
        key = self._active_tab_key()
        if not key:
            return
        if len(self.notebook.tabs()) == 1:
            self._alert("Tab", "At least one tab must remain open.")
            return
        self.notebook.forget(key)
        self.tab_state.pop(key, None)
        self._persist_tabs()
        save_settings(self.settings)

    def _persist_tabs(self):
        self.settings["recent_tabs"] = [str(self.tab_state[t]["path"]) for t in self.notebook.tabs() if t in self.tab_state]

    def _add_favorite(self):
        state = self._active_state()
        if not state:
            return
        path = str(state["path"])
        favs = self.settings.setdefault("favorites", [])
        if path not in favs:
            favs.append(path)
            self._refresh_favorites()
            save_settings(self.settings)

    def _remove_favorite(self):
        sel = self.fav_list.curselection()
        if not sel:
            return
        path = self.fav_list.get(sel[0])
        favs = self.settings.setdefault("favorites", [])
        if path in favs:
            favs.remove(path)
            self._refresh_favorites()
            save_settings(self.settings)

    def _open_favorite(self, _event=None):
        sel = self.fav_list.curselection()
        if not sel:
            return
        path = Path(self.fav_list.get(sel[0]))
        if path.is_dir():
            self._load_directory(path)

    def _new_folder(self):
        state = self._active_state()
        if not state:
            return
        name = self._prompt_text("New Folder", "Folder name:")
        if not name:
            return
        try:
            create_folder(state["path"], name)
        except FileOpError as exc:
            self._alert("Create Folder Failed", str(exc))
            return
        self._load_directory(state["path"])

    def _new_file(self):
        state = self._active_state()
        if not state:
            return
        name = self._prompt_text("New File", "File name:")
        if not name:
            return
        try:
            create_file(state["path"], name)
        except FileOpError as exc:
            self._alert("Create File Failed", str(exc))
            return
        self._load_directory(state["path"])

    def _rename_selected(self):
        target = self._selected_path()
        if target is None:
            self._alert("Rename", "Select a file or folder first.")
            return
        new_name = self._prompt_text("Rename", "New name:", initial=target.name)
        if not new_name:
            return
        try:
            rename_path(target, new_name)
        except FileOpError as exc:
            self._alert("Rename Failed", str(exc))
            return
        state = self._active_state()
        if state:
            self._load_directory(state["path"])

    def _delete_selected(self):
        target = self._selected_path()
        if target is None:
            self._alert("Delete", "Select a file or folder first.")
            return
        if not self._confirm("Confirm Delete", f"Delete '{target.name}'?"):
            return
        try:
            delete_path(target)
        except FileOpError as exc:
            self._alert("Delete Failed", str(exc))
            return
        state = self._active_state()
        if state:
            self._load_directory(state["path"])

    def _copy_selected(self):
        target = self._selected_path()
        if target is None:
            self._alert("Copy", "Select a file or folder first.")
            return
        state = self._active_state()
        initial = state["path"] if state else Path.home()
        picked = self._pick_directory("Copy To", initial=initial)
        destination = str(picked) if picked else ""
        if not destination:
            return
        try:
            copy_path(target, Path(destination))
        except FileOpError as exc:
            self._alert("Copy Failed", str(exc))
            return
        self.status_var.set(f"Copied {target.name} to {destination}")

    def _move_selected(self):
        target = self._selected_path()
        if target is None:
            self._alert("Move", "Select a file or folder first.")
            return
        state = self._active_state()
        initial = state["path"] if state else Path.home()
        picked = self._pick_directory("Move To", initial=initial)
        destination = str(picked) if picked else ""
        if not destination:
            return
        try:
            move_path(target, Path(destination))
        except FileOpError as exc:
            self._alert("Move Failed", str(exc))
            return
        state = self._active_state()
        if state:
            self._load_directory(state["path"])
        self.status_var.set(f"Moved {target.name} to {destination}")
