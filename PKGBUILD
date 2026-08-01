pkgname=file-explorer-git
pkgver=0.r9.g187b355
pkgrel=1
pkgdesc="Qt file explorer with favorites, search, preview, and file operations"
arch=('any')
url="https://github.com/EvansOgala/file-explorer"
license=('MIT')
depends=(
  'python'
  'pyside6'
  'xdg-utils'
)
makedepends=('git')
optdepends=(
  'polkit: root-open support through pkexec'
)
provides=('file-explorer')
conflicts=('file-explorer')
source=("$pkgname::git+https://github.com/EvansOgala/file-explorer.git")
sha256sums=('SKIP')

pkgver() {
  cd "$srcdir/$pkgname"
  printf "0.r%s.g%s" \
    "$(git rev-list --count HEAD)" \
    "$(git rev-parse --short HEAD)"
}

package() {
  cd "$srcdir/$pkgname"

  install -d "$pkgdir/usr/lib/file-explorer"
  install -Dm644 main.py "$pkgdir/usr/lib/file-explorer/main.py"
  install -Dm644 pyside_ui.py "$pkgdir/usr/lib/file-explorer/pyside_ui.py"
  install -Dm644 settings.py "$pkgdir/usr/lib/file-explorer/settings.py"
  install -Dm644 models.py "$pkgdir/usr/lib/file-explorer/models.py"
  install -Dm644 file_ops.py "$pkgdir/usr/lib/file-explorer/file_ops.py"
  install -Dm644 org.evans.FileExplorer.svg "$pkgdir/usr/lib/file-explorer/org.evans.FileExplorer.svg"

  install -Dm755 /dev/stdin "$pkgdir/usr/bin/org.evans.FileExplorer" <<'LAUNCHER'
#!/bin/sh
exec /usr/bin/python3 /usr/lib/file-explorer/main.py "$@"
LAUNCHER

  install -Dm644 org.evans.FileExplorer.desktop \
    "$pkgdir/usr/share/applications/org.evans.FileExplorer.desktop"
  install -Dm644 org.evans.FileExplorer.metainfo.xml \
    "$pkgdir/usr/share/metainfo/org.evans.FileExplorer.metainfo.xml"
  install -Dm644 org.evans.FileExplorer.svg \
    "$pkgdir/usr/share/icons/hicolor/scalable/apps/org.evans.FileExplorer.svg"
  install -Dm644 LICENSE "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
}
