from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


@dataclass
class Entry:
    path: Path
    name: str
    is_dir: bool
    size: int
    modified: datetime


def scan_directory(
    directory: Path,
    include_hidden: bool = False,
    hidden_skip_names: Iterable[str] | None = None,
) -> list[Entry]:
    skip_names = set(hidden_skip_names or [])
    entries: list[Entry] = []
    for child in directory.iterdir():
        if child.name in skip_names:
            continue
        if not include_hidden and child.name.startswith("."):
            continue
        try:
            stat = child.stat()
        except OSError:
            continue

        entries.append(
            Entry(
                path=child,
                name=child.name,
                is_dir=child.is_dir(),
                size=stat.st_size,
                modified=datetime.fromtimestamp(stat.st_mtime),
            )
        )

    return entries


def filter_entries(entries: list[Entry], query: str) -> list[Entry]:
    q = query.strip().lower()
    if not q:
        return entries
    return [e for e in entries if q in e.name.lower()]


def sort_entries(entries: list[Entry], key: str, reverse: bool = False) -> list[Entry]:
    key_map = {
        "name": lambda e: (not e.is_dir, e.name.lower()),
        "size": lambda e: (not e.is_dir, e.size),
        "modified": lambda e: (not e.is_dir, e.modified),
        "type": lambda e: (not e.is_dir, e.path.suffix.lower()),
    }
    sorter = key_map.get(key, key_map["name"])
    return sorted(entries, key=sorter, reverse=reverse)


def human_size(num: int) -> str:
    if num < 1024:
        return f"{num} B"
    for unit in ["KB", "MB", "GB", "TB"]:
        num /= 1024.0
        if num < 1024:
            return f"{num:.1f} {unit}"
    return f"{num:.1f} PB"


def get_linux_partitions() -> list[tuple[str, str, str]]:
    mounts_file = Path("/proc/self/mounts")
    if not mounts_file.exists():
        return []

    ignored_types = {
        "proc",
        "sysfs",
        "tmpfs",
        "devtmpfs",
        "devpts",
        "cgroup",
        "cgroup2",
        "securityfs",
        "pstore",
        "debugfs",
        "tracefs",
        "mqueue",
        "hugetlbfs",
        "configfs",
        "fusectl",
        "ramfs",
        "autofs",
        "overlay",
        "squashfs",
        "nsfs",
        "rpc_pipefs",
        "binfmt_misc",
        "efivarfs",
        "bpf",
    }

    partitions: list[tuple[str, str, str]] = []
    seen_mounts: set[str] = set()

    try:
        with mounts_file.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) < 3:
                    continue
                device, mountpoint, fstype = parts[0], parts[1], parts[2]
                mountpoint = mountpoint.replace("\\040", " ")
                if fstype in ignored_types:
                    continue
                if not mountpoint.startswith("/"):
                    continue
                if mountpoint in seen_mounts:
                    continue
                if mountpoint.startswith("/proc") or mountpoint.startswith("/sys") or mountpoint.startswith("/dev"):
                    continue
                seen_mounts.add(mountpoint)
                partitions.append((mountpoint, device, fstype))
    except OSError:
        return []

    partitions.sort(key=lambda item: (item[0] != "/", item[0]))
    return partitions
