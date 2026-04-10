from __future__ import annotations

import shutil
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
SOURCE_DIR = ROOT_DIR / "frontend"
PUBLIC_DIR = ROOT_DIR / "public"


def main() -> None:
    if not SOURCE_DIR.exists():
        raise FileNotFoundError("Frontend source directory was not found.")

    if PUBLIC_DIR.exists():
        shutil.rmtree(PUBLIC_DIR)
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)

    for source_path in SOURCE_DIR.iterdir():
        target_path = PUBLIC_DIR / source_path.name
        if source_path.is_dir():
            shutil.copytree(source_path, target_path)
        else:
            shutil.copy2(source_path, target_path)

    print(f"Copied frontend assets from '{SOURCE_DIR.name}/' to '{PUBLIC_DIR.name}/'.")


if __name__ == "__main__":
    main()
