"""Single inventory item card with expandable, editable units."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Optional

import customtkinter as ctk

from phi.expiration import ExpirationStatus, get_expiration_info
from phi.models import Item, Unit, new_id
from phi.ui.images import THUMB_CARD, load_ctk_image

if TYPE_CHECKING:
    from phi.app import PHIApp
UNIT_SAVE_MS = 400


class ItemCard:
    def __init__(self, parent: ctk.CTkFrame, app: PHIApp, item: Item, row: int) -> None:
        self.app = app
        self.parent = parent
        self.item_id = item.id
        self._row = row
        self._info = get_expiration_info(item)
        self._thumb_image: Optional[ctk.CTkImage] = None
        self._panel: Optional[ctk.CTkFrame] = None
        self._units_frame: Optional[ctk.CTkFrame] = None
        self._unit_save_jobs: dict[str, str] = {}

        self.frame = ctk.CTkFrame(
            parent,
            fg_color=self._info.bg_color,
            corner_radius=10,
        )
        self.frame.grid(row=row, column=0, sticky="ew", pady=6)
        self.frame.grid_columnconfigure(0, weight=1)

        self._header = ctk.CTkFrame(self.frame, fg_color="transparent", cursor="hand2")
        self._header.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        self._header.grid_columnconfigure(1, weight=1)

        self._thumb = ctk.CTkLabel(
            self._header,
            text="",
            width=THUMB_CARD[0],
            height=THUMB_CARD[1],
            fg_color="#2a2a2a",
            corner_radius=6,
        )
        self._thumb.grid(row=0, column=0, rowspan=6, padx=(4, 16), pady=4)

        self._chevron = ctk.CTkLabel(
            self._header,
            text="▶",
            width=20,
            text_color=self._info.fg_color,
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self._chevron.grid(row=0, column=3, rowspan=6, padx=8, sticky="ne", pady=4)

        self._name_lbl = ctk.CTkLabel(
            self._header,
            text="",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=self._info.fg_color,
            anchor="w",
        )
        self._name_lbl.grid(row=0, column=1, sticky="ew", pady=(4, 0))

        self._qty_lbl = ctk.CTkLabel(
            self._header,
            text="",
            text_color=self._info.fg_color,
            anchor="w",
        )
        self._qty_lbl.grid(row=1, column=1, sticky="ew", pady=(0, 2))

        self._brand_lbl = ctk.CTkLabel(
            self._header,
            text="",
            text_color=self._info.fg_color,
            anchor="w",
            wraplength=420,
            justify="left",
        )
        self._brand_lbl.grid(row=2, column=1, sticky="ew", pady=(0, 2))

        self._categories_lbl = ctk.CTkLabel(
            self._header,
            text="",
            text_color=self._info.fg_color,
            anchor="w",
            wraplength=420,
            justify="left",
        )
        self._categories_lbl.grid(row=3, column=1, sticky="ew", pady=(0, 2))

        self._labels_lbl = ctk.CTkLabel(
            self._header,
            text="",
            text_color=self._info.fg_color,
            anchor="w",
            wraplength=420,
            justify="left",
        )
        self._labels_lbl.grid(row=4, column=1, sticky="ew", pady=(0, 2))

        self._status_lbl = ctk.CTkLabel(
            self._header,
            text="",
            text_color=self._info.fg_color,
            anchor="w",
            font=ctk.CTkFont(size=12),
        )
        self._status_lbl.grid(row=5, column=1, sticky="ew", pady=(0, 4))

        self._warn_lbl = ctk.CTkLabel(
            self._header,
            text="Consider disposal",
            text_color="#ff6b6b",
            font=ctk.CTkFont(size=12, weight="bold"),
        )

        self._bind_expand(self._header)
        self.update(item, self.item_id in app._expanded, rebuild_units=True)

    def grid(self, row: int) -> None:
        self._row = row
        self.frame.grid(row=row, column=0, sticky="ew", pady=6)

    def destroy(self) -> None:
        for job in self._unit_save_jobs.values():
            try:
                self.app.after_cancel(job)
            except Exception:
                pass
        self._unit_save_jobs.clear()
        self.frame.destroy()

    def _bind_expand(self, widget: ctk.CTkBaseClass) -> None:
        def _on_click(_event) -> None:
            self.app.toggle_item(self.item_id)

        widget.bind("<Button-1>", _on_click)
        for child in widget.winfo_children():
            if child is not self._warn_lbl:
                self._bind_expand(child)

    def update(self, item: Item, expanded: bool, *, rebuild_units: bool = False) -> None:
        self._info = get_expiration_info(item)
        self.frame.configure(fg_color=self._info.bg_color)
        fg = self._info.fg_color

        self._set_card_image(item)
        self._chevron.configure(text="▼" if expanded else "▶", text_color=fg)
        self._name_lbl.configure(text=item.name, text_color=fg)
        self._apply_meta_labels(item, fg)
        self._status_lbl.configure(text=self._info.message, text_color=fg)

        if self._info.status == ExpirationStatus.DISPOSE:
            self._warn_lbl.grid(row=5, column=2, padx=8, sticky="e")
        else:
            self._warn_lbl.grid_remove()

        if expanded:
            self._ensure_panel(item, rebuild_units=rebuild_units)
            self._chevron.configure(text="▼")
            self.app.list_frame.attach_widget(self.frame)
        else:
            self._destroy_panel()
            self._chevron.configure(text="▶")

    def _ensure_panel(self, item: Item, *, rebuild_units: bool = True) -> None:
        if self._panel is None:
            self._panel = ctk.CTkFrame(self.frame, fg_color="#1e1e1e", corner_radius=8)
            self._panel.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 12))
            self._panel.grid_columnconfigure(0, weight=1)

            units_header = ctk.CTkFrame(self._panel, fg_color="transparent")
            units_header.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))
            units_header.grid_columnconfigure(0, weight=1)

            ctk.CTkLabel(
                units_header,
                text="Units",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color=self._info.fg_color,
            ).grid(row=0, column=0, sticky="w")

            ctk.CTkButton(
                units_header,
                text="+ Add Unit",
                width=100,
                height=28,
                command=lambda: self.app.add_unit(self.item_id),
            ).grid(row=0, column=1, sticky="e")

            self._units_frame = ctk.CTkFrame(self._panel, fg_color="transparent")
            self._units_frame.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8))
            self._units_frame.grid_columnconfigure(0, weight=1)

            actions = ctk.CTkFrame(self._panel, fg_color="transparent")
            actions.grid(row=2, column=0, sticky="ew", padx=12, pady=(4, 12))

            ctk.CTkButton(
                actions,
                text="Edit",
                width=90,
                command=lambda: self.app.edit_item(self.item_id),
            ).pack(side="left", padx=(0, 8))
            ctk.CTkButton(
                actions,
                text="Duplicate",
                width=90,
                fg_color="#444",
                hover_color="#555",
                command=lambda: self.app.duplicate_item(self.item_id),
            ).pack(side="left", padx=(0, 8))
            ctk.CTkButton(
                actions,
                text="Remove",
                width=90,
                fg_color="#8b0000",
                hover_color="#a52a2a",
                command=lambda: self.app.remove_item(self.item_id),
            ).pack(side="left")
            rebuild_units = True

        if rebuild_units:
            self._rebuild_unit_rows(item)

    def _destroy_panel(self) -> None:
        if self._panel is not None:
            self._panel.destroy()
            self._panel = None
            self._units_frame = None

    def _rebuild_unit_rows(self, item: Item) -> None:
        if self._units_frame is None:
            return

        for child in self._units_frame.winfo_children():
            child.destroy()

        if not item.units:
            ctk.CTkLabel(
                self._units_frame,
                text="No units yet. Click '+ Add Unit' to track individual items.",
                text_color="gray60",
                anchor="w",
            ).grid(row=0, column=0, sticky="ew", pady=8)
            return

        for idx, unit in enumerate(item.units):
            self._build_unit_row(item, unit, idx)

    def _build_unit_row(self, item: Item, unit: Unit, row: int) -> None:
        assert self._units_frame is not None

        row_frame = ctk.CTkFrame(self._units_frame, fg_color="#2a2a2a", corner_radius=6)
        row_frame.grid(row=row, column=0, sticky="ew", pady=4)
        row_frame.grid_columnconfigure(2, weight=1)

        ctk.CTkLabel(
            row_frame,
            text=f"Unit {row + 1}",
            width=52,
            anchor="w",
            text_color=self._info.fg_color,
        ).grid(row=0, column=0, padx=(12, 4), pady=8, sticky="w")

        ctk.CTkLabel(row_frame, text="Expiration", anchor="w").grid(
            row=0, column=1, padx=4, pady=4, sticky="w"
        )
        exp_entry = ctk.CTkEntry(row_frame, placeholder_text="YYYY-MM-DD")
        exp_entry.grid(row=0, column=2, padx=4, pady=4, sticky="ew")
        if unit.expiration:
            exp_entry.insert(0, unit.expiration)

        ctk.CTkLabel(row_frame, text="Notes", anchor="w").grid(
            row=1, column=1, padx=4, pady=4, sticky="w"
        )
        notes_entry = ctk.CTkEntry(row_frame, placeholder_text="Optional notes")
        notes_entry.grid(row=1, column=2, padx=4, pady=4, sticky="ew")
        if unit.notes:
            notes_entry.insert(0, unit.notes)

        def schedule_save(_event=None) -> None:
            self._schedule_unit_save(item.id, unit.id, exp_entry, notes_entry)

        exp_entry.bind("<KeyRelease>", schedule_save)
        exp_entry.bind("<FocusOut>", schedule_save)
        notes_entry.bind("<KeyRelease>", schedule_save)
        notes_entry.bind("<FocusOut>", schedule_save)

        ctk.CTkButton(
            row_frame,
            text="Remove",
            width=70,
            height=28,
            fg_color="#555",
            hover_color="#666",
            command=lambda u=unit: self.app.remove_unit(self.item_id, u.id),
        ).grid(row=0, column=3, rowspan=2, padx=12, pady=8, sticky="e")

    def _schedule_unit_save(
        self,
        item_id: str,
        unit_id: str,
        exp_entry: ctk.CTkEntry,
        notes_entry: ctk.CTkEntry,
    ) -> None:
        if unit_id in self._unit_save_jobs:
            try:
                self.app.after_cancel(self._unit_save_jobs[unit_id])
            except Exception:
                pass

        def _save() -> None:
            self._unit_save_jobs.pop(unit_id, None)
            self._save_unit(item_id, unit_id, exp_entry, notes_entry)

        self._unit_save_jobs[unit_id] = self.app.after(UNIT_SAVE_MS, _save)

    def _save_unit(
        self,
        item_id: str,
        unit_id: str,
        exp_entry: ctk.CTkEntry,
        notes_entry: ctk.CTkEntry,
    ) -> None:
        exp = exp_entry.get().strip() or None
        if exp:
            try:
                date.fromisoformat(exp)
            except ValueError:
                return

        notes = notes_entry.get().strip()
        stored = self.app.store.get_item(item_id)
        if not stored:
            return

        changed = False
        for unit in stored.units:
            if unit.id == unit_id:
                if unit.expiration != exp or unit.notes != notes:
                    unit.expiration = exp
                    unit.notes = notes
                    changed = True
                break

        if not changed:
            return

        self.app.store.update_item(stored)
        self.app.refresh_card_header(item_id)

    def refresh_units(self, item: Item) -> None:
        """Rebuild unit rows and refresh header without collapsing."""
        if self._panel is not None:
            self._rebuild_unit_rows(item)
        self._info = get_expiration_info(item)
        self.frame.configure(fg_color=self._info.bg_color)
        fg = self._info.fg_color
        self._apply_meta_labels(item, fg)
        self._status_lbl.configure(text=self._info.message, text_color=fg)
        if self._info.status == ExpirationStatus.DISPOSE:
            self._warn_lbl.grid(row=5, column=2, padx=8, sticky="e")
        else:
            self._warn_lbl.grid_remove()

    def refresh_header(self, item: Item) -> None:
        self._info = get_expiration_info(item)
        self.frame.configure(fg_color=self._info.bg_color)
        fg = self._info.fg_color
        self._apply_meta_labels(item, fg)
        self._status_lbl.configure(text=self._info.message, text_color=fg)
        self._chevron.configure(text_color=fg)
        self._name_lbl.configure(text_color=fg)
        if self._info.status == ExpirationStatus.DISPOSE:
            self._warn_lbl.grid(row=5, column=2, padx=8, sticky="e")
        else:
            self._warn_lbl.grid_remove()

    def _apply_meta_labels(self, item: Item, fg: str) -> None:
        qty_parts = [f"Qty: {item.quantity}"]
        if item.location:
            qty_parts.append(f"Location: {item.location}")
        self._qty_lbl.configure(text=" · ".join(qty_parts), text_color=fg)

        self._set_optional_meta(self._brand_lbl, 2, "Brand", item.brand, fg)
        self._set_optional_meta(self._categories_lbl, 3, "Categories", item.categories, fg)
        self._set_optional_meta(self._labels_lbl, 4, "Labels", item.labels, fg)

    def _set_optional_meta(
        self, label: ctk.CTkLabel, row: int, prefix: str, value: str, fg: str
    ) -> None:
        text = value.strip()
        if text:
            label.configure(text=f"{prefix}: {text}", text_color=fg)
            label.grid(row=row, column=1, sticky="ew", pady=(0, 2))
        else:
            label.grid_remove()

    def _meta_label_text(self, item: Item) -> str:
        """Legacy helper — prefer _apply_meta_labels."""
        qty_parts = [f"Qty: {item.quantity}"]
        if item.location:
            qty_parts.append(f"Location: {item.location}")
        return " · ".join(qty_parts)

    def _set_card_image(self, item: Item) -> None:
        if not item.image_path:
            self._thumb.configure(text="—", font=ctk.CTkFont(size=36), image=None)
            return
        path = self.app.store.resolve_image_path(item.image_path)
        if not path.exists():
            self._thumb.configure(text="—", font=ctk.CTkFont(size=36), image=None)
            return
        try:
            self._thumb_image = load_ctk_image(str(path), THUMB_CARD)
            self.app._card_images[item.id] = self._thumb_image
            self._thumb.configure(image=self._thumb_image, text="")
        except OSError:
            self._thumb.configure(text="—", font=ctk.CTkFont(size=36), image=None)
