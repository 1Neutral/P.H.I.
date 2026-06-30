"""Scroll helpers — reliable mouse wheel without CTk bind_all conflicts."""

from __future__ import annotations

import sys
import tkinter as tk
from typing import Any

import customtkinter as ctk

SCROLL_PIXELS = 48


def wheel_direction(event: tk.Event) -> int:
    """Return -1 (scroll up) or +1 (scroll down) for one wheel notch."""
    if getattr(event, "num", None) == 4:
        return -1
    if getattr(event, "num", None) == 5:
        return 1
    if event.delta > 0:
        return -1
    if event.delta < 0:
        return 1
    return 0


def bind_mousewheel(widget: tk.Misc, callback) -> None:
    widget.bind("<MouseWheel>", callback, add="+")
    widget.bind("<Button-4>", callback, add="+")
    widget.bind("<Button-5>", callback, add="+")


def _canvas_bg(parent: ctk.CTkFrame) -> str:
    color = parent.cget("fg_color")
    if color == "transparent":
        return parent.cget("bg_color")
    return color


class LocalScrollFrame(ctk.CTkFrame):
    """Scrollable frame with local wheel binding (no CTk bind_all)."""

    def __init__(self, master, *, label_text: str = "", **kwargs) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)
        super().grid_columnconfigure(0, weight=1)
        row = 0

        if label_text:
            ctk.CTkLabel(
                self,
                text=label_text,
                anchor="w",
                font=ctk.CTkFont(size=13, weight="bold"),
            ).grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
            row = 1

        super().grid_rowconfigure(row, weight=1)

        self._shell = ctk.CTkFrame(self, fg_color="transparent")
        self._shell.grid(row=row, column=0, columnspan=2, sticky="nsew")
        self._shell.grid_columnconfigure(0, weight=1)
        self._shell.grid_rowconfigure(0, weight=1)

        bg = _canvas_bg(self._shell)
        self._canvas = tk.Canvas(
            self._shell,
            highlightthickness=0,
            borderwidth=0,
            bg=self._shell._apply_appearance_mode(bg),
        )
        self._canvas.configure(yscrollincrement=SCROLL_PIXELS)
        self._scrollbar = ctk.CTkScrollbar(self._shell, command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._scrollbar.set)

        self.content = ctk.CTkFrame(self._canvas, fg_color="transparent")
        self._window_id = self._canvas.create_window((0, 0), window=self.content, anchor="nw")

        self._canvas.grid(row=0, column=0, sticky="nsew")
        self._scrollbar.grid(row=0, column=1, sticky="ns")

        self.content.bind("<Configure>", self._on_content_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)

        for widget in (self, self._shell, self._canvas, self.content):
            bind_mousewheel(widget, self._on_wheel)

    @property
    def _parent_canvas(self) -> tk.Canvas:
        """Alias for compatibility with CTkScrollableFrame scroll helpers."""
        return self._canvas

    def _on_content_configure(self, _event) -> None:
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event) -> None:
        self._canvas.itemconfigure(self._window_id, width=event.width)

    def _scrollable(self) -> bool:
        bbox = self._canvas.bbox("all")
        if not bbox:
            return False
        return bbox[3] > self._canvas.winfo_height()

    def _scroll_canvas(self, direction: int) -> None:
        if direction == 0 or not self._scrollable():
            return
        amount = direction * SCROLL_PIXELS
        if sys.platform == "darwin":
            self._canvas.yview("scroll", direction, "units")
            return
        try:
            self._canvas.yview("scroll", amount, "pixels")
        except tk.TclError:
            self._canvas.yview("scroll", direction, "units")

    def scroll_wheel(self, event) -> str:
        direction = wheel_direction(event)
        self._scroll_canvas(direction)
        return "break"

    def _on_wheel(self, event) -> str:
        return self.scroll_wheel(event)

    def attach_widget(self, widget: tk.Misc) -> None:
        """Bind mouse wheel on a widget and all current descendants."""
        bind_mousewheel(widget, self._on_wheel)
        for child in widget.winfo_children():
            self.attach_widget(child)

    def refresh_scroll_region(self) -> None:
        self.update_idletasks()
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def grid_columnconfigure(self, index: int, **kwargs: Any) -> None:
        self.content.grid_columnconfigure(index, **kwargs)

    def grid_rowconfigure(self, index: int, **kwargs: Any) -> None:
        self.content.grid_rowconfigure(index, **kwargs)
