"""Cross-platform window helpers."""

from __future__ import annotations

import sys
import tkinter as tk


def _redraw_ctk_widgets(widget: tk.Misc) -> None:
    """Walk the widget tree and force a full CustomTkinter canvas redraw."""
    draw = getattr(widget, "_draw", None)
    if callable(draw):
        try:
            draw()
        except tk.TclError:
            pass

    try:
        children = widget.winfo_children()
    except tk.TclError:
        return

    for child in children:
        _redraw_ctk_widgets(child)


def refresh_layout(window: tk.Misc) -> None:
    """Force layout and full CustomTkinter redraw after a size change."""
    try:
        window.update_idletasks()
        _redraw_ctk_widgets(window)
        window.update_idletasks()
    except tk.TclError:
        pass


def maximize_window(window: tk.Misc) -> None:
    """Maximize a window on Windows, Linux, and macOS."""
    try:
        if sys.platform.startswith("win"):
            window.state("zoomed")
        elif sys.platform == "darwin":
            window.attributes("-zoomed", True)
        else:
            window.attributes("-zoomed", True)
    except tk.TclError:
        try:
            window.state("zoomed")
        except tk.TclError:
            pass
    refresh_layout(window)


def schedule_maximize(window: tk.Misc, *, delay_ms: int = 150) -> None:
    """Maximize after the first paint to avoid CustomTkinter canvas artifacts."""
    window.after(delay_ms, lambda: maximize_window(window))


def bind_resize_refresh(window: tk.Misc, *, debounce_ms: int = 50) -> None:
    """Refresh layout when the window is resized (debounced)."""
    pending: list[str | None] = [None]

    def on_configure(event) -> None:
        if event.widget is not window:
            return
        if pending[0] is not None:
            try:
                window.after_cancel(pending[0])
            except tk.TclError:
                pass

        def _refresh() -> None:
            pending[0] = None
            refresh_layout(window)

        pending[0] = window.after(debounce_ms, _refresh)

    window.bind("<Configure>", on_configure)
