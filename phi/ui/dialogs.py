"""CustomTkinter modal dialogs matching the P.H.I. dark theme."""

from __future__ import annotations

import tkinter as tk
from typing import Literal

import customtkinter as ctk

from phi.ui.window_utils import refresh_layout

DialogKind = Literal["info", "warning", "error", "question"]

_KIND_STYLES: dict[DialogKind, dict[str, str]] = {
    "info": {"accent": "#2fa572", "icon": "i", "icon_fg": "#ffffff"},
    "warning": {"accent": "#c9a227", "icon": "!", "icon_fg": "#1a1a1a"},
    "error": {"accent": "#c0392b", "icon": "×", "icon_fg": "#ffffff"},
    "question": {"accent": "#3b82c4", "icon": "?", "icon_fg": "#ffffff"},
}


def _center_on_parent(dialog: ctk.CTkToplevel, parent: tk.Misc) -> None:
    dialog.update_idletasks()
    parent.update_idletasks()
    width = dialog.winfo_width()
    height = dialog.winfo_height()
    x = parent.winfo_rootx() + max(0, (parent.winfo_width() - width) // 2)
    y = parent.winfo_rooty() + max(0, (parent.winfo_height() - height) // 2)
    dialog.geometry(f"+{x}+{y}")


class _ModalDialog(ctk.CTkToplevel):
    def __init__(
        self,
        parent: tk.Misc,
        title: str,
        message: str,
        *,
        kind: DialogKind = "info",
        width: int = 440,
    ) -> None:
        super().__init__(parent)
        self._result: object = None
        self.title(title)
        self.transient(parent)
        self.resizable(False, False)

        style = _KIND_STYLES[kind]
        shell = ctk.CTkFrame(self, corner_radius=12, border_width=1, border_color="#333")
        shell.pack(fill="both", expand=True, padx=2, pady=2)

        body = ctk.CTkFrame(shell, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=(20, 12))
        body.grid_columnconfigure(1, weight=1)

        icon_frame = ctk.CTkFrame(
            body,
            width=40,
            height=40,
            corner_radius=20,
            fg_color=style["accent"],
        )
        icon_frame.grid(row=0, column=0, rowspan=3, sticky="nw", padx=(0, 14))
        icon_frame.grid_propagate(False)
        ctk.CTkLabel(
            icon_frame,
            text=style["icon"],
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=style["icon_fg"],
        ).place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(
            body,
            text=title,
            font=ctk.CTkFont(size=16, weight="bold"),
            anchor="w",
            justify="left",
        ).grid(row=0, column=1, sticky="ew")

        ctk.CTkLabel(
            body,
            text=message,
            anchor="nw",
            justify="left",
            wraplength=width - 110,
            text_color="gray85",
        ).grid(row=1, column=1, sticky="ew", pady=(6, 0))

        self._body = body
        self._button_row = ctk.CTkFrame(shell, fg_color="transparent")
        self._button_row.pack(fill="x", padx=20, pady=(0, 20))

        self.bind("<Escape>", lambda _e: self._dismiss(None))
        self.protocol("WM_DELETE_WINDOW", lambda: self._dismiss(None))

        shell.configure(width=width)
        self.update_idletasks()
        shell.configure(height=max(shell.winfo_reqheight(), 140))
        self.update_idletasks()
        _center_on_parent(self, parent)

    def _dismiss(self, result: object) -> None:
        self._result = result
        self.grab_release()
        self.destroy()

    def _show(self) -> object:
        self.grab_set()
        self.focus_force()
        self.lift()
        refresh_layout(self)
        self.wait_window(self)
        return self._result

    def _add_button(
        self,
        text: str,
        *,
        command,
        primary: bool = False,
        destructive: bool = False,
    ) -> None:
        if destructive:
            btn = ctk.CTkButton(
                self._button_row,
                text=text,
                width=100,
                fg_color="#8b0000",
                hover_color="#a52a2a",
                command=command,
            )
        elif primary:
            btn = ctk.CTkButton(self._button_row, text=text, width=100, command=command)
        else:
            btn = ctk.CTkButton(
                self._button_row,
                text=text,
                width=100,
                fg_color="transparent",
                border_width=1,
                command=command,
            )
        btn.pack(side="right", padx=(8, 0))


def show_info(parent: tk.Misc, title: str, message: str) -> None:
    dialog = _ModalDialog(parent, title, message, kind="info")
    dialog._add_button("OK", command=lambda: dialog._dismiss(True), primary=True)
    dialog._show()


def show_warning(parent: tk.Misc, title: str, message: str) -> None:
    dialog = _ModalDialog(parent, title, message, kind="warning")
    dialog._add_button("OK", command=lambda: dialog._dismiss(True), primary=True)
    dialog._show()


def show_error(parent: tk.Misc, title: str, message: str) -> None:
    dialog = _ModalDialog(parent, title, message, kind="error")
    dialog._add_button("OK", command=lambda: dialog._dismiss(True), primary=True)
    dialog._show()


def ask_yes_no(
    parent: tk.Misc,
    title: str,
    message: str,
    *,
    destructive: bool = False,
    yes_text: str = "Yes",
    no_text: str = "No",
) -> bool:
    dialog = _ModalDialog(parent, title, message, kind="question")
    dialog._add_button(yes_text, command=lambda: dialog._dismiss(True), destructive=destructive)
    dialog._add_button(no_text, command=lambda: dialog._dismiss(False))
    return dialog._show() is True


def ask_retry_cancel(parent: tk.Misc, title: str, message: str) -> bool:
    dialog = _ModalDialog(parent, title, message, kind="warning")
    dialog._add_button("Retry", command=lambda: dialog._dismiss(True), primary=True)
    dialog._add_button("Cancel", command=lambda: dialog._dismiss(False))
    return dialog._show() is True


def ask_string(
    parent: tk.Misc,
    title: str,
    message: str,
    *,
    initial: str = "",
    placeholder: str = "",
) -> str | None:
    dialog = _ModalDialog(parent, title, message, kind="question", width=460)
    entry = ctk.CTkEntry(dialog._body, height=36, placeholder_text=placeholder)
    entry.grid(row=2, column=1, sticky="ew", pady=(12, 0))
    if initial:
        entry.insert(0, initial)

    def submit() -> None:
        dialog._dismiss(entry.get())

    entry.bind("<Return>", lambda _e: submit())
    dialog._add_button("OK", command=submit, primary=True)
    dialog._add_button("Cancel", command=lambda: dialog._dismiss(None))
    dialog.update_idletasks()
    _center_on_parent(dialog, parent)
    entry.focus_set()
    result = dialog._show()
    if result is None:
        return None
    return str(result)
