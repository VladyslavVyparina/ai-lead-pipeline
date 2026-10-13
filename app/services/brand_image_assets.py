"""Provenance-preserving image crops and colour extraction for preview assets.

This service only transforms supplied or already-crawled business media. It
does not fabricate an official logo. Any future generated SVG must be clearly
labelled as an unofficial concept mark and retain its source metadata.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from PIL import Image


@dataclass(frozen=True)
class DerivedImageAsset:
    path: Path
    width: int
    height: int
    dominant_colors: tuple[str, ...]


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def dominant_colors(path: Path, *, limit: int = 4) -> tuple[str, ...]:
    """Return non-neutral colours from a supplied image, ordered by frequency."""
    with Image.open(path) as source:
        image = source.convert("RGB")
        image.thumbnail((160, 160))
        colors = Counter(image.getdata())
    selected: list[str] = []
    for rgb, _count in colors.most_common():
        high, low = max(rgb), min(rgb)
        saturation = (high - low) / max(high, 1)
        brightness = sum(rgb) / (3 * 255)
        if saturation < 0.15 or brightness < 0.08 or brightness > 0.93:
            continue
        color = _hex(rgb)
        if color not in selected:
            selected.append(color)
        if len(selected) == limit:
            break
    return tuple(selected)


def crop_image_asset(
    source_path: str | Path,
    output_path: str | Path,
    *,
    box: tuple[int, int, int, int],
    max_size: tuple[int, int],
    output_format: str = "PNG",
) -> DerivedImageAsset:
    """Crop known user-supplied media without altering its semantic content."""
    source_path = Path(source_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source_path) as source:
        image = source.convert("RGB").crop(box)
        image.thumbnail(max_size, Image.Resampling.LANCZOS)
        image.save(output_path, format=output_format, optimize=True)
    return DerivedImageAsset(
        path=output_path.resolve(),
        width=image.width,
        height=image.height,
        dominant_colors=dominant_colors(output_path),
    )
