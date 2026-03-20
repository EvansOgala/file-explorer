# File Explorer

Desktop file explorer with favorites, search, preview, and file operations.

## Features

- Directory tree + file list
- Double-click to open folders/files
- Search and sorting controls
- Create, rename, move, copy, and delete actions
- Right-click context menu
- Persisted last-opened path
- Linux: GTK4 UI
- Windows: PySide6 UI with drive list

## Dependencies

### Runtime

- Python 3.11+

Linux UI stack:

- GTK4 + PyGObject
- `xdg-utils` for opening files/URIs
- Optional: `pkexec` (`polkit`) for root-open action

Windows UI stack:

- PySide6 (Qt)

### Install dependencies by distro

#### Arch Linux / Nyarch

```bash
sudo pacman -S --needed python python-gobject gtk4 xdg-utils polkit
```

#### Debian / Ubuntu

```bash
sudo apt update
sudo apt install -y python3 python3-gi gir1.2-gtk-4.0 xdg-utils policykit-1
```

#### Fedora

```bash
sudo dnf install -y python3 python3-gobject gtk4 xdg-utils polkit
```

## Run from source

### Linux

```bash
cd /home/'your username'/Documents/file-explorer
python3 main.py
```

### Windows

```powershell
cd C:\Users\your-username\Documents\file-explorer
py -m pip install PySide6
py main.py
```

## Build AppImage

### Build requirements

```bash
python3 -m pip install --user pyinstaller
```

Install `appimagetool` in `PATH`, or place one of these files in `./tools/`:

- `appimagetool.AppImage`
- `appimagetool-x86_64.AppImage`

### Build command

```bash
cd /home/'your username'/Documents/file-explorer
chmod +x build-appimage.sh
./build-appimage.sh
```

The script outputs an `.AppImage` file in the project root.

## Build Windows (PyInstaller)

```powershell
cd C:\Users\your-username\Documents\file-explorer
build-windows.bat
```

The executable is emitted into `dist\FileExplorer\`.
