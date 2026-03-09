# File Explorer

GTK4 file explorer with partitions view, context actions, and root-open helper.

## Features

- Directory tree + file list
- Double-click to open folders/files
- Search and sorting controls
- Create, rename, move, copy, and delete actions
- Right-click context menu
- "Open as Root" action for protected paths
- Persisted last-opened path

## Dependencies

### Runtime

- Python 3.11+
- GTK4 + PyGObject
- `xdg-utils` for opening files/URIs
- Optional: `pkexec` (`polkit`) for root-open action

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

```bash
cd /home/'your username'/Documents/file-explorer
python3 main.py
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
