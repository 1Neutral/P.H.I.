"""Main P.H.I. desktop application."""

from __future__ import annotations

import customtkinter as ctk

from phi.models import Item, Unit, new_id
from phi.storage import InventoryStore
from phi.ui import dialogs
from phi.ui.item_card import ItemCard
from phi.ui.item_editor import ItemEditor
from phi.ui.multi_scan import MultiScanDialog
from phi.ui.scroll import LocalScrollFrame
from phi.ui.window_utils import bind_resize_refresh, refresh_layout, schedule_maximize

PAGE_SIZE = 25


class PHIApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("P.H.I. — Personal Home Inventory")
        self.minsize(720, 500)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("green")

        self.store = InventoryStore()
        self.store.load()
        self._search_var = ctk.StringVar()
        self._search_after_id: str | None = None
        self._search_var.trace_add("write", self._on_search_changed)
        self._card_images: dict[str, ctk.CTkImage] = {}
        self._editors: list[ItemEditor] = []
        self._multi_scans: list[MultiScanDialog] = []
        self._expanded: set[str] = set()
        self._cards: dict[str, ItemCard] = {}
        self._empty_label: ctk.CTkLabel | None = None
        self._current_page = 0

        self._build_ui()
        bind_resize_refresh(self)
        schedule_maximize(self)
        self._sync_list(preserve_scroll=False)

    def _build_ui(self) -> None:
        root = ctk.CTkFrame(self, fg_color="transparent")
        root.pack(fill="both", expand=True, padx=20, pady=16)
        root.grid_rowconfigure(2, weight=1)
        root.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(root, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))

        ctk.CTkLabel(
            header,
            text="P.H.I.",
            font=ctk.CTkFont(size=28, weight="bold"),
            anchor="w",
        ).pack(anchor="w")

        ctk.CTkLabel(
            header,
            text="Personal Home Inventory",
            font=ctk.CTkFont(size=14),
            text_color="gray70",
            anchor="w",
        ).pack(anchor="w")

        toolbar = ctk.CTkFrame(root, fg_color="transparent")
        toolbar.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        toolbar.grid_columnconfigure(0, weight=1)

        self.search_entry = ctk.CTkEntry(
            toolbar,
            placeholder_text="Search by name, brand, or category…",
            textvariable=self._search_var,
            height=36,
        )
        self.search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 12))

        ctk.CTkButton(
            toolbar,
            text="Multi Scan",
            width=110,
            height=36,
            fg_color="#444",
            hover_color="#555",
            command=self._multi_scan,
        ).grid(row=0, column=1, padx=(0, 8))

        ctk.CTkButton(
            toolbar, text="+ Add Item", width=130, height=36, command=self._add_item
        ).grid(row=0, column=2, sticky="e")

        self.list_frame = LocalScrollFrame(root, label_text="Inventory")
        self.list_frame.grid(row=2, column=0, sticky="nsew")
        self.list_frame.grid_columnconfigure(0, weight=1)

        self.pagination_bar = ctk.CTkFrame(root, fg_color="transparent")
        self.pagination_bar.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        self.pagination_bar.grid_columnconfigure(1, weight=1)

        self._prev_btn = ctk.CTkButton(
            self.pagination_bar,
            text="◀ Prev",
            width=90,
            command=self._prev_page,
        )
        self._prev_btn.grid(row=0, column=0, padx=(0, 12))

        self._page_label = ctk.CTkLabel(
            self.pagination_bar,
            text="Page 1 of 1",
            font=ctk.CTkFont(size=13),
            text_color="gray80",
        )
        self._page_label.grid(row=0, column=1)

        self._next_btn = ctk.CTkButton(
            self.pagination_bar,
            text="Next ▶",
            width=90,
            command=self._next_page,
        )
        self._next_btn.grid(row=0, column=2, padx=(12, 0))

        legend = ctk.CTkFrame(root, fg_color="transparent")
        legend.grid(row=4, column=0, sticky="ew", pady=(12, 8))
        self._build_legend(legend)

        self.status_bar = ctk.CTkLabel(
            root, text="", anchor="w", text_color="gray60", font=ctk.CTkFont(size=12)
        )
        self.status_bar.grid(row=5, column=0, sticky="ew")

    def _build_legend(self, parent: ctk.CTkFrame) -> None:
        entries = [
            ("OK / no date", "#1a2a3d", "#6eb5ff"),
            ("Expired <1yr", "#1a3d1a", "#6fcf6f"),
            ("Expired 1–3yr", "#3d3a1a", "#f2c94c"),
            ("Expired 3–5yr", "#3d1a1a", "#eb5757"),
            ("Dispose 5yr+", "#0d0d0d", "#ffffff"),
        ]
        for i, (label, bg, fg) in enumerate(entries):
            chip = ctk.CTkLabel(
                parent,
                text=label,
                fg_color=bg,
                text_color=fg,
                corner_radius=6,
                padx=8,
                pady=4,
                font=ctk.CTkFont(size=11),
            )
            chip.grid(row=0, column=i, padx=(0, 8), sticky="w")

    def _on_search_changed(self, *_args) -> None:
        if self._search_after_id is not None:
            self.after_cancel(self._search_after_id)
        self._search_after_id = self.after(250, self._run_debounced_search)

    def _run_debounced_search(self) -> None:
        self._search_after_id = None
        self._current_page = 0
        self._sync_list(preserve_scroll=False)

    def _filtered_items(self) -> list[Item]:
        query = self._search_var.get().strip().lower()
        items = self.store.inventory.items
        if not query:
            return list(items)
        tokens = query.split()
        result: list[Item] = []
        for item in items:
            haystack = " ".join(
                [
                    item.name.lower(),
                    item.location.lower(),
                    item.brand.lower(),
                    item.categories.lower(),
                    item.labels.lower(),
                    item.upc or "",
                ]
            ).lower()
            if all(tok in haystack for tok in tokens):
                result.append(item)
        return result

    def _page_count(self, filtered_count: int) -> int:
        if filtered_count == 0:
            return 1
        return (filtered_count + PAGE_SIZE - 1) // PAGE_SIZE

    def _clamp_page(self, filtered_count: int) -> None:
        max_page = self._page_count(filtered_count) - 1
        if self._current_page > max_page:
            self._current_page = max_page
        if self._current_page < 0:
            self._current_page = 0

    def _paged_items(self) -> tuple[list[Item], int]:
        all_items = self._filtered_items()
        total = len(all_items)
        self._clamp_page(total)
        start = self._current_page * PAGE_SIZE
        return all_items[start : start + PAGE_SIZE], total

    def _prev_page(self) -> None:
        if self._current_page > 0:
            self._current_page -= 1
            self._sync_list(preserve_scroll=False)

    def _next_page(self) -> None:
        all_items = self._filtered_items()
        if self._current_page < self._page_count(len(all_items)) - 1:
            self._current_page += 1
            self._sync_list(preserve_scroll=False)

    def _update_pagination(self, filtered_count: int) -> None:
        page_count = self._page_count(filtered_count)
        showing_start = self._current_page * PAGE_SIZE + 1 if filtered_count else 0
        showing_end = min((self._current_page + 1) * PAGE_SIZE, filtered_count)

        if filtered_count:
            self._page_label.configure(
                text=(
                    f"Page {self._current_page + 1} of {page_count}"
                    f"  ·  showing {showing_start}–{showing_end} of {filtered_count}"
                )
            )
        else:
            self._page_label.configure(text="Page 1 of 1")

        if self._current_page > 0:
            self._prev_btn.configure(state="normal")
        else:
            self._prev_btn.configure(state="disabled")

        if filtered_count and self._current_page < page_count - 1:
            self._next_btn.configure(state="normal")
        else:
            self._next_btn.configure(state="disabled")

    def _get_scroll_y(self) -> float:
        try:
            return self.list_frame._parent_canvas.yview()[0]
        except Exception:
            return 0.0

    def _set_scroll_y(self, position: float) -> None:
        try:
            self.list_frame._parent_canvas.yview_moveto(position)
        except Exception:
            pass

    def _update_status_bar(self, filtered_count: int) -> None:
        total = len(self.store.inventory.items)
        if self._search_var.get().strip():
            self.status_bar.configure(
                text=f"{filtered_count} matching item{'s' if filtered_count != 1 else ''}"
                f" (of {total} total in inventory)"
            )
        else:
            self.status_bar.configure(
                text=f"{total} item{'s' if total != 1 else ''} in inventory"
            )

    def _show_empty(self) -> None:
        for card in self._cards.values():
            card.destroy()
        self._cards.clear()

        if self._empty_label is None:
            self._empty_label = ctk.CTkLabel(
                self.list_frame.content,
                text="No items yet. Click '+ Add Item' to get started.",
                text_color="gray60",
                anchor="center",
                justify="center",
            )
        self._empty_label.grid(row=0, column=0, sticky="ew", pady=60, padx=20)
        self._update_status_bar(0)
        self._update_pagination(0)

    def _hide_empty(self) -> None:
        if self._empty_label is not None:
            self._empty_label.grid_remove()

    def _sync_list(self, preserve_scroll: bool = True) -> None:
        scroll_y = self._get_scroll_y() if preserve_scroll else 0.0
        items, filtered_count = self._paged_items()
        visible_ids = {item.id for item in items}

        if filtered_count == 0:
            self._show_empty()
            return

        self._hide_empty()

        for item_id in list(self._cards.keys()):
            if item_id not in visible_ids:
                self._cards[item_id].destroy()
                del self._cards[item_id]

        for row_idx, item in enumerate(items):
            expanded = item.id in self._expanded
            if item.id in self._cards:
                card = self._cards[item.id]
                card.grid(row_idx)
                card.update(item, expanded, rebuild_units=False)
            else:
                card = ItemCard(self.list_frame.content, self, item, row_idx)
                self._cards[item.id] = card
                self.list_frame.attach_widget(card.frame)

        self.list_frame.refresh_scroll_region()
        self._update_status_bar(filtered_count)
        self._update_pagination(filtered_count)

        if preserve_scroll:
            self.after_idle(lambda: self._set_scroll_y(scroll_y))
        else:
            self.after_idle(lambda: self._set_scroll_y(0.0))

    def toggle_item(self, item_id: str) -> None:
        if item_id in self._expanded:
            self._expanded.discard(item_id)
        else:
            self._expanded.add(item_id)

        item = self.store.get_item(item_id)
        card = self._cards.get(item_id)
        if item and card:
            card.update(item, item_id in self._expanded, rebuild_units=True)
            self.list_frame.refresh_scroll_region()

    def refresh_card_header(self, item_id: str) -> None:
        item = self.store.get_item(item_id)
        card = self._cards.get(item_id)
        if item and card:
            card.refresh_header(item)

    def add_unit(self, item_id: str) -> None:
        stored = self.store.get_item(item_id)
        card = self._cards.get(item_id)
        if not stored or not card:
            return
        stored.units.append(Unit(id=new_id()))
        self.store.update_item(stored)
        self._expanded.add(item_id)
        card.refresh_units(stored)

    def remove_unit(self, item_id: str, unit_id: str) -> None:
        stored = self.store.get_item(item_id)
        card = self._cards.get(item_id)
        if not stored or not card:
            return
        stored.units = [u for u in stored.units if u.id != unit_id]
        self.store.update_item(stored)
        card.refresh_units(stored)

    def _open_editor(self, **kwargs) -> ItemEditor:
        editor = ItemEditor(self, self.store, **kwargs)

        def _cleanup(_e=None) -> None:
            if editor in self._editors:
                self._editors.remove(editor)

        editor.bind("<Destroy>", _cleanup)
        self._editors.append(editor)
        return editor

    def _refresh_item(self, item_id: str) -> None:
        item = self.store.get_item(item_id)
        card = self._cards.get(item_id)
        if item and card:
            card.update(item, item_id in self._expanded, rebuild_units=True)
        else:
            self._sync_list(preserve_scroll=True)

    def _open_multi_scan(self, **kwargs) -> MultiScanDialog:
        dialog = MultiScanDialog(self, self.store, **kwargs)

        def _cleanup(_e=None) -> None:
            if dialog in self._multi_scans:
                self._multi_scans.remove(dialog)

        dialog.bind("<Destroy>", _cleanup)
        self._multi_scans.append(dialog)
        return dialog

    def _multi_scan(self) -> None:
        self._open_multi_scan(on_saved=lambda: self._sync_list(preserve_scroll=True))

    def _add_item(self) -> None:
        self._open_editor(
            item=Item(),
            is_new=True,
            on_saved=lambda _i: self._sync_list(preserve_scroll=True),
        )

    def edit_item(self, item_id: str) -> None:
        stored = self.store.get_item(item_id)
        if not stored:
            self._sync_list(preserve_scroll=True)
            return

        def _on_deleted(deleted_id: str) -> None:
            self._expanded.discard(deleted_id)
            self._sync_list(preserve_scroll=True)
            self.after_idle(lambda: refresh_layout(self))

        self._open_editor(
            item=stored,
            is_new=False,
            on_saved=lambda i: self._refresh_item(i.id),
            on_deleted=_on_deleted,
        )

    def duplicate_item(self, item_id: str) -> None:
        stored = self.store.get_item(item_id)
        if not stored:
            self._sync_list(preserve_scroll=True)
            return
        copy = stored.duplicate()
        self._open_editor(
            item=copy,
            is_new=True,
            on_saved=lambda _i: self._sync_list(preserve_scroll=True),
        )

    def remove_item(self, item_id: str) -> None:
        stored = self.store.get_item(item_id)
        if not stored:
            return
        if dialogs.ask_yes_no(
            self,
            "Remove item",
            f"Remove '{stored.name}' from inventory?",
            destructive=True,
            yes_text="Remove",
        ):
            self.store.remove_item(item_id)
            self._expanded.discard(item_id)
            self._clamp_page(len(self._filtered_items()))
            self._sync_list(preserve_scroll=True)
            self.after_idle(lambda: refresh_layout(self))


def run() -> None:
    app = PHIApp()
    app.mainloop()
