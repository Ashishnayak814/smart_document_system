"""Read-only inspection report for the document image dataset."""

from __future__ import annotations

import argparse
import hashlib
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image, UnidentifiedImageError


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inspect(root: Path) -> str:
    categories = sorted(path for path in root.iterdir() if path.is_dir())
    lines: list[str] = [f"Dataset: {root.resolve()}", "", "Categories and image counts:"]
    all_hashes: dict[str, list[str]] = defaultdict(list)
    total_images = 0
    total_files = 0
    total_non_images = 0
    total_corrupt = 0
    overall_formats: Counter[str] = Counter()

    for category in categories:
        image_count = 0
        category_formats: Counter[str] = Counter()
        corrupt: list[str] = []
        non_images: list[str] = []
        files = sorted(path for path in category.rglob("*") if path.is_file())
        total_files += len(files)

        for path in files:
            relative = str(path.relative_to(root))
            try:
                with Image.open(path) as image:
                    detected_format = (image.format or "UNKNOWN").upper()
                    image.verify()
                with Image.open(path) as image:
                    image.load()
                image_count += 1
                category_formats[detected_format] += 1
                overall_formats[detected_format] += 1
                all_hashes[sha256(path)].append(relative)
            except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
                # A known image suffix is reported as corrupt; other files as non-image.
                if path.suffix.lower() in {
                    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff",
                    ".webp", ".heic", ".heif", ".avif", ".jfif",
                }:
                    corrupt.append(relative)
                    total_corrupt += 1
                else:
                    non_images.append(relative)
                    total_non_images += 1

        total_images += image_count
        lines.append(
            f"- {category.name}: {image_count} image(s)"
            + (f"; formats: {dict(sorted(category_formats.items()))}" if category_formats else "")
        )
        if corrupt:
            lines.append(f"  Corrupted/unreadable ({len(corrupt)}): {', '.join(corrupt)}")
        if non_images:
            lines.append(f"  Non-image files ({len(non_images)}): {', '.join(non_images)}")

    duplicates = [paths for paths in all_hashes.values() if len(paths) > 1]
    lines.extend(
        [
            "",
            "Overall summary:",
            f"- Total files: {total_files}",
            f"- Total readable images: {total_images}",
            f"- Formats: {dict(sorted(overall_formats.items())) or 'none'}",
            f"- Corrupted/unreadable image files: {total_corrupt}",
            f"- Non-image files: {total_non_images}",
            f"- Exact duplicate groups (SHA-256): {len(duplicates)}",
        ]
    )
    if duplicates:
        lines.append("Duplicate groups:")
        for group in duplicates:
            lines.append(f"- {', '.join(group)}")

    counts = {
        category.name: sum(
            1
            for path in category.rglob("*")
            if path.is_file() and str(path.relative_to(root)) in all_hashes.get(sha256(path), [])
        )
        for category in categories
    }
    if counts:
        maximum = max(counts.values())
        minimum = min(counts.values())
        lines.extend(
            [
                "",
                "Balance:",
                f"- Readable-image range: {minimum} to {maximum}",
                f"- Max/min ratio: {(maximum / minimum):.2f}"
                if minimum
                else "- Max/min ratio: undefined because at least one category is empty",
            ]
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", type=Path, default=Path("raw_dataset"))
    args = parser.parse_args()
    print(inspect(args.root))


if __name__ == "__main__":
    main()
