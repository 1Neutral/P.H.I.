"""Data models for P.H.I."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional


def new_id() -> str:
    return str(uuid.uuid4())


@dataclass
class Unit:
    """A single physical unit of an inventory item."""

    id: str = field(default_factory=new_id)
    expiration: Optional[str] = None  # ISO date YYYY-MM-DD or None
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "expiration": self.expiration,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Unit:
        return cls(
            id=data.get("id") or new_id(),
            expiration=data.get("expiration"),
            notes=data.get("notes", ""),
        )


@dataclass
class Item:
    """An inventory item type (e.g. 'Canned tomatoes') with one or more units."""

    id: str = field(default_factory=new_id)
    name: str = ""
    upc: Optional[str] = None
    brand: str = ""
    categories: str = ""
    labels: str = ""
    location: str = ""
    image_path: Optional[str] = None
    units: list[Unit] = field(default_factory=list)

    @property
    def quantity(self) -> int:
        return len(self.units)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "upc": self.upc,
            "brand": self.brand,
            "categories": self.categories,
            "labels": self.labels,
            "location": self.location,
            "image_path": self.image_path,
            "units": [u.to_dict() for u in self.units],
        }

    @classmethod
    def from_dict(cls, data: dict) -> Item:
        location = data.get("location", "")
        units = [Unit.from_dict(u) for u in data.get("units", [])]

        if not location:
            for unit_data in data.get("units", []):
                legacy_loc = unit_data.get("location", "").strip()
                if legacy_loc:
                    location = legacy_loc
                    break

        brand = data.get("brand", "")
        categories = data.get("categories", "")
        labels = data.get("labels", "")

        # Migrate legacy details/tags into categories when new fields are absent.
        if not brand and not categories and not labels:
            legacy = data.get("details") or data.get("tags", [])
            if legacy:
                categories = ", ".join(str(d) for d in legacy)

        return cls(
            id=data.get("id") or new_id(),
            name=data.get("name", ""),
            upc=data.get("upc"),
            brand=brand,
            categories=categories,
            labels=labels,
            location=location,
            image_path=data.get("image_path"),
            units=units,
        )

    def duplicate(self) -> Item:
        """Create a copy with a new id, ready for editing similar items."""
        return Item(
            id=new_id(),
            name=f"{self.name} (copy)" if self.name else "",
            upc=self.upc,
            brand=self.brand,
            categories=self.categories,
            labels=self.labels,
            location=self.location,
            image_path=self.image_path,
            units=[
                Unit(
                    expiration=u.expiration,
                    notes=u.notes,
                )
                for u in self.units
            ],
        )


@dataclass
class Inventory:
    items: list[Item] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"items": [i.to_dict() for i in self.items]}

    @classmethod
    def from_dict(cls, data: dict) -> Inventory:
        return cls(items=[Item.from_dict(i) for i in data.get("items", [])])
