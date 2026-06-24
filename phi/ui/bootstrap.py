"""Bootstrap CustomTkinter fonts into a writable project directory."""

from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
FONT_DIR = PROJECT_ROOT / "data" / "fonts"


def _find_customtkinter_dir() -> Path | None:
    for entry in sys.path:
        candidate = Path(entry) / "customtkinter"
        if (candidate / "assets" / "fonts").is_dir():
            return candidate
    return None


def bootstrap_customtkinter_fonts() -> None:
    """
    CustomTkinter copies fonts to ~/.fonts on Linux. If that fails, widgets
    render blank or broken. Copy fonts into data/fonts/ and patch FontManager
    before the rest of customtkinter finishes loading.
    """
    FONT_DIR.mkdir(parents=True, exist_ok=True)
    ctk_dir = _find_customtkinter_dir()
    if ctk_dir is None:
        return

    assets = ctk_dir / "assets" / "fonts"
    font_sources = [
        assets / "Roboto" / "Roboto-Regular.ttf",
        assets / "Roboto" / "Roboto-Medium.ttf",
        assets / "CustomTkinter_shapes_font.otf",
    ]
    for src in font_sources:
        if src.is_file():
            dest = FONT_DIR / src.name
            if not dest.exists() or dest.stat().st_mtime < src.stat().st_mtime:
                shutil.copy2(src, dest)

    fm_path = ctk_dir / "windows" / "widgets" / "font" / "font_manager.py"
    spec = importlib.util.spec_from_file_location(
        "customtkinter.windows.widgets.font.font_manager", fm_path
    )
    if spec is None or spec.loader is None:
        return

    fm = importlib.util.module_from_spec(spec)
    sys.modules["customtkinter.windows.widgets.font.font_manager"] = fm
    spec.loader.exec_module(fm)

    fm.FontManager.linux_font_path = str(FONT_DIR) + "/"
    fm.FontManager.init_font_manager()
    for src in font_sources:
        if src.is_file():
            fm.FontManager.load_font(str(src))
