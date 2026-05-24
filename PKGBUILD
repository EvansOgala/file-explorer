pkgname=file-explorer-git
pkgver=0.r9.g187b355
pkgrel=1
pkgdesc="GTK4 file explorer with favorites, search, preview, and file operations"
arch=('x86_64')
url="https://github.com/EvansOgala/file-explorer"
license=('MIT')
depends=(
  'glibc'
  'xdg-utils'
)
makedepends=(
  'git'
  'python'
  'python-gobject'
  'gtk4'
)
optdepends=(
  'polkit: root-open support through pkexec'
)
provides=('file-explorer')
conflicts=('file-explorer')
options=('!strip' '!debug')
source=("$pkgname::git+https://github.com/EvansOgala/file-explorer.git")
sha256sums=('SKIP')

pkgver() {
  cd "$srcdir/$pkgname"
  printf "0.r%s.g%s" \
    "$(git rev-list --count HEAD)" \
    "$(git rev-parse --short HEAD)"
}

build() {
  cd "$srcdir/$pkgname"
  python -c 'import PyInstaller' || {
    echo "PyInstaller is required. Install it before building this package." >&2
    return 1
  }
  python -m PyInstaller FileExplorer.spec --noconfirm --clean
}

package() {
  cd "$srcdir/$pkgname"

  local bundle_dir="$srcdir/$pkgname/dist/FileExplorer"
  if [[ ! -x "$bundle_dir/FileExplorer" ]]; then
    echo "Missing PyInstaller bundle: build() did not create dist/FileExplorer." >&2
    return 1
  fi

  install -d "$pkgdir/opt/file-explorer" "$pkgdir/usr/bin"
  cp -a "$bundle_dir/." "$pkgdir/opt/file-explorer/"
  ln -s /opt/file-explorer/FileExplorer "$pkgdir/usr/bin/org.evans.FileExplorer"

  install -Dm644 org.evans.FileExplorer.desktop \
    "$pkgdir/usr/share/applications/org.evans.FileExplorer.desktop"
  install -Dm644 org.evans.FileExplorer.metainfo.xml \
    "$pkgdir/usr/share/metainfo/org.evans.FileExplorer.metainfo.xml"
  install -Dm644 org.evans.FileExplorer.svg \
    "$pkgdir/usr/share/icons/hicolor/scalable/apps/org.evans.FileExplorer.svg"
  install -Dm644 LICENSE "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
}
