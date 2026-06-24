"""Uniform thumbnail rendering for item photos."""

from __future__ import annotations

from typing import Tuple

import customtkinter as ctk
from PIL import Image, ImageOps

# Fixed display sizes — every thumbnail uses the full box.
THUMB_CARD: Tuple[int, int] = (168, 168)
THUMB_EDITOR: Tuple[int, int] = (256, 256)

_PLACEHOLDER_BG = (42, 42, 42)


def fit_image(
    image: Image.Image,
    size: Tuple[int, int],
    *,
    bg: Tuple[int, int, int] = _PLACEHOLDER_BG,
) -> Image.Image:
    """Fit an image inside a fixed-size box, centered with letterboxing."""
    image = ImageOps.exif_transpose(image)
    image = image.convert("RGB")
    fitted = Image.new("RGB", size, bg)
    scaled = image.copy()
    scaled.thumbnail(size, Image.Resampling.LANCZOS)
    x = (size[0] - scaled.width) // 2
    y = (size[1] - scaled.height) // 2
    fitted.paste(scaled, (x, y))
    return fitted


def load_ctk_image(path: str, size: Tuple[int, int]) -> ctk.CTkImage:
    """Load a file into a fixed-size CTkImage."""
    with Image.open(path) as img:
        fitted = fit_image(img, size)
    return ctk.CTkImage(light_image=fitted, dark_image=fitted, size=size)
