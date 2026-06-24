"""Local JSON persistence for inventory data."""

from __future__ import annotations

import json
import shutil
import urllib.request
from pathlib import Path

from phi.models import Inventory, Item

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
INVENTORY_FILE = "inventory.json"
IMAGES_DIR = "images"


class InventoryStore:
    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir or DEFAULT_DATA_DIR
        self.inventory_path = self.data_dir / INVENTORY_FILE
        self.images_dir = self.data_dir / IMAGES_DIR
        self._inventory = Inventory()
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)

    @property
    def inventory(self) -> Inventory:
        return self._inventory

    def load(self) -> Inventory:
        if self.inventory_path.exists():
            with open(self.inventory_path, encoding="utf-8") as f:
                self._inventory = Inventory.from_dict(json.load(f))
        else:
            self._inventory = Inventory()
            self.save()
        return self._inventory

    def save(self) -> None:
        with open(self.inventory_path, "w", encoding="utf-8") as f:
            json.dump(self._inventory.to_dict(), f, indent=2)

    def add_item(self, item: Item) -> Item:
        self._inventory.items.append(item)
        self.save()
        return item

    def update_item(self, item: Item) -> None:
        for i, existing in enumerate(self._inventory.items):
            if existing.id == item.id:
                self._inventory.items[i] = item
                self.save()
                return
        raise KeyError(f"Item {item.id} not found")

    def remove_item(self, item_id: str) -> None:
        self._inventory.items = [i for i in self._inventory.items if i.id != item_id]
        self.save()

    def get_item(self, item_id: str) -> Item | None:
        for item in self._inventory.items:
            if item.id == item_id:
                return item
        return None

    def find_by_upc(self, upc: str) -> Item | None:
        for item in self._inventory.items:
            if item.upc and item.upc == upc:
                return item
        return None

    def store_image(self, source_path: Path, item_id: str) -> str:
        """Copy an image into data/images and return the stored relative path."""
        suffix = source_path.suffix.lower() or ".png"
        dest = self.images_dir / f"{item_id}{suffix}"
        shutil.copy2(source_path, dest)
        return str(dest.relative_to(self.data_dir.parent))

    def store_image_from_url(self, url: str, item_id: str) -> str | None:
        """Download a product image into data/images."""
        suffix = ".jpg"
        lower = url.lower()
        if ".png" in lower:
            suffix = ".png"
        elif ".webp" in lower:
            suffix = ".webp"

        dest = self.images_dir / f"{item_id}{suffix}"
        request = urllib.request.Request(url, headers={"User-Agent": "PHI-Inventory/0.1"})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                dest.write_bytes(response.read())
            return str(dest.relative_to(self.data_dir.parent))
        except Exception:
            return None

    def resolve_image_path(self, relative_or_absolute: str) -> Path:
        path = Path(relative_or_absolute)
        if path.is_absolute():
            return path
        return self.data_dir.parent / path
