from pathlib import Path

from PIL import Image, UnidentifiedImageError


def _open_files(files):
    for file in files:
        file = Path(file)
        if not file.is_file():
            continue

        valid = False

        try:
            with Image.open(file):
                valid = True
        except (OSError, UnidentifiedImageError, NotImplementedError, ValueError):
            pass

        if valid:
            yield file


def open_files(files):
    for file in _open_files(files):
        folder_processed = file.parent / "rembg"
        outfile = folder_processed / file.relative_to(file.parent).with_suffix(".png")
        yield file, outfile


def open_folder(folder):
    folder = Path(folder)
    if not folder.is_dir():
        return

    folder_processed = folder.with_name(folder.name + "_rembg")

    for file in _open_files(folder.rglob("*")):
        outfile = folder_processed / file.relative_to(folder).with_suffix(".png")
        yield file, outfile


def open_mixed(files):
    for file in files:
        file = Path(file)
        if file.is_file():
            yield from open_files([file])
        elif file.is_dir():
            yield from open_folder(file)
