"""Batch UPC scanning dialog — scan many items, then assign a location per item."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Callable, Literal, Optional

import customtkinter as ctk

from phi.models import Item, Unit, new_id
from phi.storage import InventoryStore
from phi.ui import dialogs
from phi.ui.scroll import LocalScrollFrame
from phi.ui.window_utils import bind_resize_refresh, refresh_layout, schedule_maximize
from phi.upc_lookup import UPCLookupResult, lookup_upc, normalize_upc

ScanKind = Literal["existing", "new", "pending", "error"]


@dataclass
class ScanLine:
    row_id: str
    upc: str
    kind: ScanKind
    name: str
    count: int = 1
    item_id: str | None = None
    result: UPCLookupResult | None = None
    row_frame: ctk.CTkFrame | None = field(default=None, repr=False)
    name_label: ctk.CTkLabel | None = field(default=None, repr=False)
    detail_label: ctk.CTkLabel | None = field(default=None, repr=False)
    location_entry: ctk.CTkEntry | None = field(default=None, repr=False)


def build_item_from_lookup(
    store: InventoryStore, result: UPCLookupResult, *, location: str
) -> Item:
    item_id = new_id()
    image_path = None
    if result.image_url:
        image_path = store.store_image_from_url(result.image_url, item_id)
    return Item(
        id=item_id,
        name=result.name,
        upc=result.upc,
        brand=result.brand,
        categories=result.categories,
        labels=result.labels,
        location=location,
        image_path=image_path,
        units=[Unit(id=new_id())],
    )


class MultiScanDialog(ctk.CTkToplevel):
    def __init__(
        self,
        parent: ctk.CTk,
        store: InventoryStore,
        *,
        on_saved: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.on_saved = on_saved
        self._lines: list[ScanLine] = []
        self._active_lookups = 0

        self.title("Multi Scan")
        self.minsize(560, 480)
        self.transient(parent)

        self.container = ctk.CTkFrame(self)
        self.container.pack(fill="both", expand=True, padx=16, pady=16)

        self._build_ui()
        bind_resize_refresh(self)
        refresh_layout(self)
        self.grab_set()
        self.focus_force()
        self.lift()
        schedule_maximize(self)
        self.after_idle(self._focus_scan_entry)

    def _build_ui(self) -> None:
        ctk.CTkLabel(
            self.container,
            text="Multi Scan",
            font=ctk.CTkFont(size=18, weight="bold"),
            anchor="w",
        ).pack(fill="x", pady=(0, 4))

        ctk.CTkLabel(
            self.container,
            text=(
                "Scan a UPC, then scan its location. Press Enter after each scan "
                "to move to the next step."
            ),
            text_color="gray60",
            anchor="w",
            wraplength=680,
            justify="left",
        ).pack(fill="x", pady=(0, 12))

        scan_frame = ctk.CTkFrame(self.container, fg_color="#252525", corner_radius=8)
        scan_frame.pack(fill="x", pady=(0, 12))
        scan_frame.grid_columnconfigure(0, weight=1)

        self.upc_entry = ctk.CTkEntry(
            scan_frame,
            placeholder_text="Scan UPC barcode…",
            height=40,
            font=ctk.CTkFont(size=14),
        )
        self.upc_entry.grid(row=0, column=0, sticky="ew", padx=12, pady=12)
        self.upc_entry.bind("<Return>", lambda _e: self._on_scan())

        self._summary_label = ctk.CTkLabel(
            self.container,
            text="No items scanned yet",
            text_color="gray70",
            anchor="w",
        )
        self._summary_label.pack(fill="x", pady=(0, 8))

        self.list_scroll = LocalScrollFrame(self.container, label_text="Scanned items")
        self.list_scroll.pack(fill="both", expand=True, pady=(0, 12))
        self.list_scroll.content.grid_columnconfigure(0, weight=1)

        footer = ctk.CTkFrame(self.container, fg_color="transparent")
        footer.pack(fill="x")
        footer.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(
            footer,
            text="Cancel",
            fg_color="transparent",
            border_width=1,
            command=self.destroy,
        ).grid(row=0, column=1, padx=(0, 8))

        self._save_btn = ctk.CTkButton(
            footer,
            text="Save All",
            width=120,
            command=self._save_all,
            state="disabled",
        )
        self._save_btn.grid(row=0, column=2)

    def _focus_scan_entry(self) -> None:
        self.upc_entry.select_range(0, "end")
        self.upc_entry.focus_set()

    def _clear_scan_entry(self, *, focus: bool = True) -> None:
        self.upc_entry.delete(0, "end")
        if focus:
            self._focus_scan_entry()

    def _focus_location(self, line: ScanLine) -> None:
        entry = line.location_entry
        row = line.row_frame
        if entry is None or row is None:
            return

        def focus() -> None:
            self.list_scroll.refresh_scroll_region()
            content_height = self.list_scroll.content.winfo_height()
            if content_height > 0:
                self.list_scroll._parent_canvas.yview_moveto(
                    max(0.0, min(1.0, row.winfo_y() / content_height))
                )
            entry.select_range(0, "end")
            entry.focus_set()

        self.after_idle(focus)

    def _on_location_entered(self, row_id: str) -> str:
        line = next((line for line in self._lines if line.row_id == row_id), None)
        if line is None or not self._line_location(line):
            if line and line.location_entry:
                line.location_entry.focus_set()
            return "break"
        self._focus_scan_entry()
        return "break"

    def _find_line(self, upc: str) -> ScanLine | None:
        for line in self._lines:
            if line.upc == upc and line.kind in {"existing", "new", "pending"}:
                return line
        return None

    def _existing_location(self, item_id: str) -> str:
        item = self.store.get_item(item_id)
        return item.location if item else ""

    def _on_scan(self) -> None:
        upc = normalize_upc(self.upc_entry.get().strip())
        if not upc:
            dialogs.show_warning(
                self,
                "Invalid UPC",
                "Enter a valid UPC barcode (8–14 digits).",
            )
            return

        existing = self.store.find_by_upc(upc)
        if existing:
            line = self._find_line(upc)
            if line and line.kind == "existing":
                line.count += 1
                self._refresh_line(line)
            else:
                line = ScanLine(
                    row_id=new_id(),
                    upc=upc,
                    kind="existing",
                    name=existing.name,
                    item_id=existing.id,
                )
                self._add_line(
                    line
                )
            self._clear_scan_entry(focus=False)
            self._update_summary()
            self._focus_location(line)
            return

        line = self._find_line(upc)
        if line and line.kind in {"new", "pending"}:
            line.count += 1
            self._refresh_line(line)
            self._clear_scan_entry(focus=False)
            self._update_summary()
            if line.kind == "new":
                self._focus_location(line)
            return

        pending = ScanLine(
            row_id=new_id(),
            upc=upc,
            kind="pending",
            name="Looking up…",
        )
        self._add_line(pending)
        self._clear_scan_entry(focus=False)
        self._update_summary()
        self._start_lookup(pending)

    def _start_lookup(self, line: ScanLine) -> None:
        self._active_lookups += 1
        self._update_save_state()

        def worker() -> None:
            result = lookup_upc(line.upc)
            self.after(0, lambda: self._on_lookup_complete(line.row_id, result))

        threading.Thread(target=worker, daemon=True).start()

    def _on_lookup_complete(self, row_id: str, result: UPCLookupResult) -> None:
        self._active_lookups = max(0, self._active_lookups - 1)
        line = next((l for l in self._lines if l.row_id == row_id), None)
        if line is None:
            self._update_save_state()
            return

        existing = self.store.find_by_upc(result.upc if result.found else line.upc)
        location_line: ScanLine | None = None
        if existing:
            self._remove_line_ui(line)
            self._lines.remove(line)
            merged = self._find_line(line.upc)
            if merged and merged.kind == "existing":
                merged.count += line.count
                self._refresh_line(merged)
                location_line = merged
            else:
                location_line = ScanLine(
                    row_id=new_id(),
                    upc=line.upc,
                    kind="existing",
                    name=existing.name,
                    item_id=existing.id,
                    count=line.count,
                )
                self._add_line(
                    location_line
                )
        elif result.found:
            line.kind = "new"
            line.name = result.name
            line.result = result
            self._rebuild_line_ui(line)
            location_line = line
        else:
            line.kind = "error"
            line.name = "Not found"
            line.result = result
            self._rebuild_line_ui(line)

        self._update_summary()
        self._update_save_state()
        if location_line:
            self._focus_location(location_line)
        else:
            self._focus_scan_entry()

    def _add_line(self, line: ScanLine) -> None:
        self._lines.append(line)
        self._build_line_ui(line)
        self._update_summary()
        self._update_save_state()

    def _build_line_ui(self, line: ScanLine) -> None:
        row = ctk.CTkFrame(self.list_scroll.content, fg_color="#2a2a2a", corner_radius=6)
        row.pack(fill="x", pady=3)
        row.grid_columnconfigure(0, weight=1)

        name_label = ctk.CTkLabel(
            row,
            text=self._line_title(line),
            anchor="w",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        name_label.grid(row=0, column=0, sticky="ew", padx=12, pady=(8, 0))

        detail_label = ctk.CTkLabel(
            row,
            text=self._line_detail(line),
            anchor="w",
            text_color="gray65",
            font=ctk.CTkFont(size=12),
        )
        detail_label.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 4))

        remove_rowspan = 4 if line.kind in {"existing", "new"} else 2
        ctk.CTkButton(
            row,
            text="Remove",
            width=72,
            height=28,
            fg_color="#555",
            hover_color="#666",
            command=lambda: self._remove_line(line.row_id),
        ).grid(row=0, column=1, rowspan=remove_rowspan, padx=12, pady=8)

        location_entry: ctk.CTkEntry | None = None
        if line.kind in {"existing", "new"}:
            ctk.CTkLabel(
                row,
                text="Location",
                anchor="w",
                font=ctk.CTkFont(size=12),
                text_color="gray75",
            ).grid(row=2, column=0, sticky="w", padx=12, pady=(0, 2))
            location_entry = ctk.CTkEntry(
                row,
                placeholder_text="e.g. Pantry shelf 2",
                height=32,
            )
            location_entry.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 8))
            location_entry.bind(
                "<Return>",
                lambda _event, row_id=line.row_id: self._on_location_entered(row_id),
            )
            initial = ""
            if line.kind == "existing" and line.item_id:
                initial = self._existing_location(line.item_id)
            if initial:
                location_entry.insert(0, initial)

        line.row_frame = row
        line.name_label = name_label
        line.detail_label = detail_label
        line.location_entry = location_entry
        self.list_scroll.attach_widget(row)
        self.list_scroll.refresh_scroll_region()

    def _rebuild_line_ui(self, line: ScanLine) -> None:
        saved_location = ""
        if line.location_entry:
            saved_location = line.location_entry.get().strip()
        self._remove_line_ui(line)
        self._build_line_ui(line)
        if saved_location and line.location_entry:
            line.location_entry.insert(0, saved_location)
        else:
            self._refresh_line(line)

    def _line_title(self, line: ScanLine) -> str:
        qty = f" ×{line.count}" if line.count > 1 else ""
        if line.kind == "existing":
            return f"+ Unit{qty} — {line.name}"
        if line.kind == "new":
            return f"New{qty} — {line.name}"
        if line.kind == "pending":
            return f"Pending{qty} — {line.name}"
        return f"Error — UPC {line.upc}"

    def _line_detail(self, line: ScanLine) -> str:
        if line.kind == "existing":
            return f"Already in inventory · UPC {line.upc}"
        if line.kind == "new":
            brand = line.result.brand if line.result else ""
            parts = [f"UPC {line.upc}"]
            if brand:
                parts.append(brand)
            return " · ".join(parts)
        if line.kind == "pending":
            return f"UPC {line.upc} · looking up online…"
        error = line.result.error if line.result and line.result.error else "Product not found"
        return f"UPC {line.upc} · {error}"

    def _refresh_line(self, line: ScanLine) -> None:
        if line.name_label:
            line.name_label.configure(text=self._line_title(line))
        if line.detail_label:
            line.detail_label.configure(text=self._line_detail(line))

    def _remove_line_ui(self, line: ScanLine) -> None:
        if line.row_frame:
            line.row_frame.destroy()
            line.row_frame = None
            line.name_label = None
            line.detail_label = None
            line.location_entry = None

    def _remove_line(self, row_id: str) -> None:
        line = next((l for l in self._lines if l.row_id == row_id), None)
        if line is None:
            return
        self._remove_line_ui(line)
        self._lines.remove(line)
        self._update_summary()
        self._update_save_state()
        self.list_scroll.refresh_scroll_region()

    def _update_summary(self) -> None:
        if not self._lines:
            self._summary_label.configure(text="No items scanned yet")
            return
        units = sum(line.count for line in self._lines)
        kinds = len(self._lines)
        pending = sum(1 for line in self._lines if line.kind == "pending")
        errors = sum(1 for line in self._lines if line.kind == "error")
        parts = [f"{kinds} item{'s' if kinds != 1 else ''}", f"{units} unit{'s' if units != 1 else ''}"]
        if pending:
            parts.append(f"{pending} looking up")
        if errors:
            parts.append(f"{errors} failed")
        self._summary_label.configure(text=" · ".join(parts))

    def _update_save_state(self) -> None:
        savable = any(line.kind in {"existing", "new"} for line in self._lines)
        ready = savable and self._active_lookups == 0
        self._save_btn.configure(state="normal" if ready else "disabled")

    def _line_location(self, line: ScanLine) -> str:
        if line.location_entry:
            return line.location_entry.get().strip()
        return ""

    def _save_all(self) -> None:
        if self._active_lookups:
            return

        savable = [line for line in self._lines if line.kind in {"existing", "new"}]
        if not savable:
            return

        errors = [line for line in self._lines if line.kind == "error"]
        if errors and not dialogs.ask_yes_no(
            self,
            "Skip failed scans?",
            f"{len(errors)} scanned item(s) could not be looked up.\n\n"
            "Save the rest and skip those?",
        ):
            return

        for line in savable:
            if not self._line_location(line):
                dialogs.show_warning(
                    self,
                    "Location required",
                    f"Enter a location for '{line.name}' before saving.",
                )
                if line.location_entry:
                    line.location_entry.focus_set()
                return

        for line in savable:
            location = self._line_location(line)
            if line.kind == "existing" and line.item_id:
                item = self.store.get_item(line.item_id)
                if item:
                    item.location = location
                    for _ in range(line.count):
                        item.units.append(Unit(id=new_id()))
                    self.store.update_item(item)
            elif line.kind == "new" and line.result:
                item = build_item_from_lookup(self.store, line.result, location=location)
                for _ in range(line.count - 1):
                    item.units.append(Unit(id=new_id()))
                self.store.add_item(item)

        if self.on_saved:
            self.on_saved()
        self.destroy()
