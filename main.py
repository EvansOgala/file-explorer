import argparse
import tkinter as tk
from pathlib import Path

from ui import FileExplorerApp


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--start-path", default="", help="Directory to open on startup")
    args, _unknown = parser.parse_known_args()

    start_path = None
    if args.start_path:
        candidate = Path(args.start_path).expanduser()
        if candidate.is_dir():
            start_path = candidate

    root = tk.Tk()
    FileExplorerApp(root, start_path=start_path)
    root.mainloop()


if __name__ == "__main__":
    main()
