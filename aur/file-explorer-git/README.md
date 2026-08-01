# file-explorer-git AUR Staging Folder

This folder mirrors the package files intended for the AUR repository.

Files to publish:

- `PKGBUILD`
- `.SRCINFO`

Typical workflow:

```bash
git clone ssh://aur@aur.archlinux.org/file-explorer-git.git
cd file-explorer-git
cp /path/to/your/source/repo/aur/file-explorer-git/PKGBUILD .
cp /path/to/your/source/repo/aur/file-explorer-git/.SRCINFO .
git add PKGBUILD .SRCINFO
git commit -m "Initial import"
git push
```
