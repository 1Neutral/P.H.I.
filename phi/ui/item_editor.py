"""Dialog for creating and editing inventory items."""

from __future__ import annotations

import threading
import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog
from typing import Callable, Optional

import customtkinter as ctk

from phi.expiration import get_expiration_info
from phi.models import Item, Unit, new_id
from phi.storage import InventoryStore
from phi.ui import dialogs
from phi.ui.images import THUMB_EDITOR, load_ctk_image
from phi.ui.window_utils import bind_resize_refresh, refresh_layout
from phi.upc_lookup import (
    UPCLookupResult,
    lookup_product,
    normalize_product_code,
    product_code_label,
)

EDITOR_GEOMETRY = "900x720"


class ItemEditor(ctk.CTkToplevel):
    def __init__(
        self,
        parent: ctk.CTk,
        store: InventoryStore,
        item: Item,
        *,
        is_new: bool = False,
        on_saved: Optional[Callable[[Item], None]] = None,
        on_deleted: Optional[Callable[[str], None]] = None,
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.item = item
        self.is_new = is_new
        self.on_saved = on_saved
        self.on_deleted = on_deleted
        self._thumb_image: Optional[ctk.CTkImage] = None
        self._unit_rows: list[dict] = []
        self._lookup_running = False
        self._closed = False
        self.bind(
            "<Destroy>",
            lambda e: setattr(self, "_closed", True) if e.widget is self else None,
            add="+",
        )

        title = "Add Item" if is_new else f"Edit — {item.name or 'Item'}"
        self.title(title)
        self.minsize(600, 500)
        self.transient(parent)

        self.container = ctk.CTkFrame(self)
        self.container.pack(fill="both", expand=True, padx=16, pady=16)

        self._build_ui()
        self._populate_fields()
        self._refresh_status()

        self.geometry(EDITOR_GEOMETRY)
        bind_resize_refresh(self)
        refresh_layout(self)
        self.grab_set()
        self.focus_force()
        self.lift()
        if self.is_new:
            self.after_idle(self._focus_upc_entry)

    def _build_ui(self) -> None:
        if self.is_new:
            upc_frame = ctk.CTkFrame(self.container, fg_color="#252525", corner_radius=8)
            upc_frame.pack(fill="x", pady=(0, 16))
            upc_frame.grid_columnconfigure(1, weight=1)

            ctk.CTkLabel(
                upc_frame,
                text="Scan or enter UPC / EAN / ASIN",
                font=ctk.CTkFont(size=14, weight="bold"),
                anchor="w",
            ).grid(row=0, column=0, columnspan=3, sticky="w", padx=12, pady=(12, 4))

            ctk.CTkLabel(
                upc_frame,
                text="Looks up product info online and adds the item to your inventory.",
                text_color="gray60",
                anchor="w",
                wraplength=640,
                justify="left",
            ).grid(row=1, column=0, columnspan=3, sticky="ew", padx=12, pady=(0, 8))

            self.upc_entry = ctk.CTkEntry(
                upc_frame,
                placeholder_text="UPC / EAN / GTIN (8–14 digits) or ASIN (B…)",
                height=36,
            )
            self.upc_entry.grid(row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 12))
            self.upc_entry.bind("<Return>", lambda _e: self._lookup_upc())

            self._lookup_btn = ctk.CTkButton(
                upc_frame,
                text="Look up & Add",
                width=130,
                height=36,
                command=self._lookup_upc,
            )
            self._lookup_btn.grid(row=2, column=2, padx=(0, 12), pady=(0, 12))

            ctk.CTkLabel(
                upc_frame,
                text="— or enter manually below —",
                text_color="gray55",
            ).grid(row=3, column=0, columnspan=3, pady=(0, 12))

        header = ctk.CTkFrame(self.container, fg_color="transparent")
        header.pack(fill="x", pady=(0, 12))
        header.grid_columnconfigure(1, weight=1)

        self.image_label = ctk.CTkLabel(
            header,
            text="No image",
            width=THUMB_EDITOR[0],
            height=THUMB_EDITOR[1],
            corner_radius=8,
            fg_color="#333",
        )
        self.image_label.grid(row=0, column=0, rowspan=3, padx=(0, 16), sticky="nw")

        ctk.CTkButton(header, text="Upload Photo", width=140, command=self._upload_image).grid(
            row=0, column=1, sticky="nw", pady=(0, 8)
        )

        self.name_entry = ctk.CTkEntry(header, placeholder_text="Item name")
        self.name_entry.grid(row=1, column=1, sticky="ew", pady=(0, 8))

        if not self.is_new and self.item.upc:
            ctk.CTkLabel(
                header,
                text=f"{product_code_label(self.item.upc)}: {self.item.upc}",
                text_color="gray60",
                anchor="w",
            ).grid(row=2, column=1, sticky="w")

        ctk.CTkLabel(self.container, text="Location", anchor="w").pack(fill="x", pady=(0, 4))
        self.location_entry = ctk.CTkEntry(
            self.container, placeholder_text="e.g. Pantry shelf 2, Garage bin A"
        )
        self.location_entry.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(self.container, text="Brand (optional)", anchor="w").pack(
            fill="x", pady=(0, 4)
        )
        self.brand_entry = ctk.CTkEntry(
            self.container, placeholder_text="e.g. Campbell's, Kirkland"
        )
        self.brand_entry.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(self.container, text="Categories (optional)", anchor="w").pack(
            fill="x", pady=(0, 4)
        )
        self.categories_entry = ctk.CTkEntry(
            self.container, placeholder_text="e.g. canned goods, soups"
        )
        self.categories_entry.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(self.container, text="Labels (optional)", anchor="w").pack(
            fill="x", pady=(0, 4)
        )
        self.labels_entry = ctk.CTkEntry(
            self.container, placeholder_text="e.g. organic, gluten-free"
        )
        self.labels_entry.pack(fill="x", pady=(0, 8))

        self.status_label = ctk.CTkLabel(
            self.container, text="", anchor="w", height=28, corner_radius=6
        )
        self.status_label.pack(fill="x", pady=(0, 12))

        units_header = ctk.CTkFrame(self.container, fg_color="transparent")
        units_header.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(units_header, text="Units", font=ctk.CTkFont(size=14, weight="bold")).pack(
            side="left"
        )
        ctk.CTkButton(
            units_header, text="+ Add Unit", width=100, command=self._add_unit_row
        ).pack(side="right")

        self.units_scroll = ctk.CTkScrollableFrame(self.container, label_text="")
        self.units_scroll.pack(fill="both", expand=True, pady=(0, 12))
        self.units_scroll.grid_columnconfigure(0, weight=1)

        footer = ctk.CTkFrame(self.container, fg_color="transparent")
        footer.pack(fill="x")
        footer.grid_columnconfigure(0, weight=1)

        left_footer = ctk.CTkFrame(footer, fg_color="transparent")
        left_footer.grid(row=0, column=0, sticky="w")

        if not self.is_new:
            ctk.CTkButton(
                left_footer,
                text="Delete Item",
                fg_color="#8b0000",
                hover_color="#a52a2a",
                command=self._delete_item,
            ).pack(side="left")

        btn_row = ctk.CTkFrame(footer, fg_color="transparent")
        btn_row.grid(row=0, column=1, sticky="e")

        ctk.CTkButton(
            btn_row,
            text="Cancel",
            fg_color="transparent",
            border_width=1,
            command=self.destroy,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="Save", command=self._save).pack(side="left")

    def _populate_fields(self) -> None:
        self.name_entry.insert(0, self.item.name)
        self.location_entry.insert(0, self.item.location)
        self.brand_entry.insert(0, self.item.brand)
        self.categories_entry.insert(0, self.item.categories)
        self.labels_entry.insert(0, self.item.labels)
        self._load_thumbnail()
        for unit in self.item.units:
            self._add_unit_row(unit)
        if not self.item.units:
            self._add_unit_row()

    def _load_thumbnail(self) -> None:
        if not self.item.image_path:
            return
        path = self.store.resolve_image_path(self.item.image_path)
        if not path.exists():
            return
        try:
            self._thumb_image = load_ctk_image(str(path), THUMB_EDITOR)
            self.image_label.configure(image=self._thumb_image, text="")
        except OSError:
            pass

    def _set_lookup_busy(self, busy: bool) -> None:
        self._lookup_running = busy
        if not self.is_new:
            return
        if busy:
            self._lookup_btn.configure(state="disabled", text="Looking up…")
            self.upc_entry.configure(state="disabled")
        else:
            self._lookup_btn.configure(state="normal", text="Look up & Add")
            self.upc_entry.configure(state="normal")

    def _focus_upc_entry(self) -> None:
        if hasattr(self, "upc_entry"):
            self.upc_entry.focus_set()

    def _handle_existing_upc(self, existing: Item) -> None:
        code_label = product_code_label(existing.upc or "")
        if dialogs.ask_yes_no(
            self,
            "Already in inventory",
            f"'{existing.name}' is already tracked with this {code_label}.\n\n"
            "Add another unit to that item?",
        ):
            existing.units.append(Unit(id=new_id()))
            self.store.update_item(existing)
            if self.on_saved:
                self.on_saved(existing)
            self.destroy()

    def _lookup_upc(self) -> None:
        if not self.is_new or self._lookup_running:
            return

        normalized = normalize_product_code(self.upc_entry.get().strip())
        if not normalized:
            dialogs.show_warning(
                self,
                "Invalid product code",
                "Enter a valid UPC/EAN/GTIN (8–14 digits) or ASIN (B plus 9 letters/digits).",
            )
            return
        code, _code_type = normalized

        existing = self.store.find_by_identifier(code)
        if existing:
            self._handle_existing_upc(existing)
            return

        self._set_lookup_busy(True)

        def worker() -> None:
            result = lookup_product(code)
            if self._closed:
                return
            try:
                self.after(0, lambda: self._on_lookup_complete(result))
            except (RuntimeError, tk.TclError):
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _on_lookup_complete(self, result: UPCLookupResult) -> None:
        if self._closed:
            return
        self._set_lookup_busy(False)
        if not result.found:
            dialogs.show_error(
                self,
                f"{result.code_type} lookup failed",
                result.error or "Product not found.",
            )
            return

        existing = self.store.find_by_identifier(result.upc)
        if existing:
            self._handle_existing_upc(existing)
            return

        location = self._prompt_location_for_upc(result.name)
        if location is None:
            return

        item = self._build_item_from_lookup(result, location=location)
        if item is None:
            return

        self.store.add_item(item)
        if self.on_saved:
            self.on_saved(item)
        self.destroy()

    def _prompt_location_for_upc(self, product_name: str) -> str | None:
        initial = self.location_entry.get().strip()
        while True:
            entered = dialogs.ask_string(
                self,
                "Item location",
                f"Where are you putting '{product_name}'?\n\n"
                "e.g. Pantry shelf 2, Garage bin A",
                initial=initial,
                placeholder="e.g. Pantry shelf 2, Garage bin A",
            )
            if entered is None:
                return None
            location = entered.strip()
            if location:
                return location
            if not dialogs.ask_retry_cancel(
                self,
                "Location required",
                "Please enter a location for this item.",
            ):
                return None
            initial = ""

    def _build_item_from_lookup(
        self, result: UPCLookupResult, *, location: str
    ) -> Item | None:
        image_path = self.item.image_path
        if result.image_url and not image_path:
            image_path = self.store.store_image_from_url(result.image_url, self.item.id)

        return Item(
            id=self.item.id,
            name=result.name,
            upc=result.upc,
            brand=result.brand,
            categories=result.categories,
            labels=result.labels,
            location=location,
            image_path=image_path,
            units=[Unit(id=new_id())],
        )

    def _upload_image(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="Select item photo",
            filetypes=[
                ("Images", "*.png *.jpg *.jpeg *.gif *.webp *.bmp"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        stored = self.store.store_image(Path(path), self.item.id)
        self.item.image_path = stored
        self._load_thumbnail()

    def _add_unit_row(self, unit: Unit | None = None) -> None:
        row_frame = ctk.CTkFrame(self.units_scroll, fg_color="#2a2a2a")
        row_frame.pack(fill="x", pady=4)
        row_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(row_frame, text="Expiration").grid(row=0, column=0, padx=4, pady=4, sticky="w")
        exp_entry = ctk.CTkEntry(row_frame, placeholder_text="YYYY-MM-DD (optional)")
        exp_entry.grid(row=0, column=1, padx=4, pady=4, sticky="ew")
        exp_entry.bind("<KeyRelease>", lambda _e: self._refresh_status())

        ctk.CTkLabel(row_frame, text="Notes").grid(row=1, column=0, padx=4, pady=4, sticky="nw")
        notes_entry = ctk.CTkTextbox(row_frame, height=48)
        notes_entry.grid(row=1, column=1, padx=4, pady=4, sticky="ew")

        if unit:
            if unit.expiration:
                exp_entry.insert(0, unit.expiration)
            if unit.notes:
                notes_entry.insert("1.0", unit.notes)

        def remove_row() -> None:
            row_frame.destroy()
            self._unit_rows[:] = [r for r in self._unit_rows if r["frame"] is not row_frame]
            self._refresh_status()

        ctk.CTkButton(
            row_frame, text="Remove", width=70, fg_color="#555", command=remove_row
        ).grid(row=2, column=1, padx=4, pady=4, sticky="e")

        row_data = {
            "frame": row_frame,
            "id": unit.id if unit else new_id(),
            "expiration": exp_entry,
            "notes": notes_entry,
        }
        self._unit_rows.append(row_data)

    def _collect_item(self) -> Item | None:
        name = self.name_entry.get().strip()
        if not name:
            dialogs.show_warning(self, "Missing name", "Please enter an item name.")
            return None

        units: list[Unit] = []
        for row in self._unit_rows:
            exp = row["expiration"].get().strip() or None
            if exp:
                try:
                    date.fromisoformat(exp)
                except ValueError:
                    dialogs.show_warning(
                        self,
                        "Invalid date",
                        f"Expiration must be YYYY-MM-DD. Got: {exp}",
                    )
                    return None
            notes = row["notes"].get("1.0", "end").strip()
            units.append(
                Unit(
                    id=row["id"],
                    expiration=exp,
                    notes=notes,
                )
            )

        self.item.name = name
        self.item.location = self.location_entry.get().strip()
        self.item.brand = self.brand_entry.get().strip()
        self.item.categories = self.categories_entry.get().strip()
        self.item.labels = self.labels_entry.get().strip()
        self.item.units = units
        if not self.item.upc and self.is_new and hasattr(self, "upc_entry"):
            normalized = normalize_product_code(self.upc_entry.get())
            if normalized:
                self.item.upc = normalized[0]
        return self.item

    def _refresh_status(self) -> None:
        draft = self._collect_item_silent()
        if draft is None:
            self.status_label.configure(text="")
            return
        info = get_expiration_info(draft)
        self.status_label.configure(
            text=info.message,
            fg_color=info.bg_color,
            text_color=info.fg_color,
        )

    def _collect_item_silent(self) -> Item | None:
        name = self.name_entry.get().strip()
        units: list[Unit] = []
        for row in self._unit_rows:
            exp = row["expiration"].get().strip() or None
            notes = row["notes"].get("1.0", "end").strip()
            units.append(
                Unit(
                    id=row["id"],
                    expiration=exp,
                    notes=notes,
                )
            )
        return Item(
            id=self.item.id,
            name=name,
            upc=self.item.upc,
            brand=self.brand_entry.get().strip(),
            categories=self.categories_entry.get().strip(),
            labels=self.labels_entry.get().strip(),
            location=self.location_entry.get().strip(),
            image_path=self.item.image_path,
            units=units,
        )

    def _save(self) -> None:
        item = self._collect_item()
        if item is None:
            return
        if self.is_new:
            self.store.add_item(item)
        else:
            self.store.update_item(item)
        if self.on_saved:
            self.on_saved(item)
        self.destroy()

    def _delete_item(self) -> None:
        if not dialogs.ask_yes_no(
            self,
            "Delete item",
            f"Remove '{self.item.name}' from inventory?",
            destructive=True,
            yes_text="Remove",
        ):
            return
        self.store.remove_item(self.item.id)
        if self.on_deleted:
            self.on_deleted(self.item.id)
        self.destroy()
