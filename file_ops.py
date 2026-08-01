from pathlib import Path
import shutil


class FileOpError(Exception):
    pass


def create_folder(parent: Path, name: str) -> Path:
    target = parent / name
    try:
        target.mkdir(parents=False, exist_ok=False)
    except OSError as exc:
        raise FileOpError(str(exc)) from exc
    return target


def create_file(parent: Path, name: str) -> Path:
    target = parent / name
    try:
        target.touch(exist_ok=False)
    except OSError as exc:
        raise FileOpError(str(exc)) from exc
    return target


def rename_path(source: Path, new_name: str) -> Path:
    target = source.with_name(new_name)
    try:
        source.rename(target)
    except OSError as exc:
        raise FileOpError(str(exc)) from exc
    return target


def delete_path(target: Path) -> None:
    try:
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
    except OSError as exc:
        raise FileOpError(str(exc)) from exc


def copy_path(source: Path, destination_dir: Path) -> Path:
    target = destination_dir / source.name
    try:
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)
    except OSError as exc:
        raise FileOpError(str(exc)) from exc
    return target


def move_path(source: Path, destination_dir: Path) -> Path:
    target = destination_dir / source.name
    try:
        moved = shutil.move(str(source), str(target))
    except OSError as exc:
        raise FileOpError(str(exc)) from exc
    return Path(moved)
