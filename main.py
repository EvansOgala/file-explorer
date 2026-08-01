import argparse
from pathlib import Path

from pyside_ui import FileExplorerQtApp


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--start-path", default="", help="Directory to open on startup")
    args, _unknown = parser.parse_known_args()

    start_path = None
    if args.start_path:
        candidate = Path(args.start_path).expanduser()
        if candidate.is_dir():
            start_path = candidate

    FileExplorerQtApp.run_app(start_path=start_path)


if __name__ == "__main__":
    main()
