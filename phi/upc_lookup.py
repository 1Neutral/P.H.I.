"""UPC barcode lookup via Open *Facts databases and UPCitemdb."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

USER_AGENT = "PHI-Inventory/0.1 (personal home inventory)"
OFF_URL = "https://world.openfoodfacts.org/api/v2/product/{}.json"
OBF_URL = "https://world.openbeautyfacts.org/api/v2/product/{}.json"
OPF_URL = "https://world.openproductsfacts.org/api/v2/product/{}.json"
OPFF_URL = "https://world.openpetfoodfacts.org/api/v2/product/{}.json"
UPCITEMDB_URL = "https://api.upcitemdb.com/prod/trial/lookup?upc={}"


@dataclass
class UPCLookupResult:
    found: bool
    upc: str
    name: str = ""
    brand: str = ""
    categories: str = ""
    labels: str = ""
    image_url: str | None = None
    source: str = ""
    error: str | None = None


def normalize_upc(value: str) -> str | None:
    """Return digits-only UPC if valid (8–14 digits), else None."""
    digits = re.sub(r"\D", "", value.strip())
    if 8 <= len(digits) <= 14:
        return digits
    return None


def expand_upce(upc: str) -> str | None:
    """Expand a compressed 8-digit UPC-E code to its full 12-digit UPC-A form.

    Returns None if the code is not a plausible UPC-E (must be 8 digits with a
    number-system digit of 0 or 1). The check digit is preserved because it is
    computed from the UPC-A representation and is identical for both forms.
    """
    if len(upc) != 8 or not upc.isdigit():
        return None
    number_system = upc[0]
    if number_system not in ("0", "1"):
        return None

    body = upc[1:7]
    check = upc[7]
    last = body[5]

    if last in ("0", "1", "2"):
        manufacturer = body[0] + body[1] + last + "00"
        product = "00" + body[2] + body[3] + body[4]
    elif last == "3":
        manufacturer = body[0] + body[1] + body[2] + "00"
        product = "000" + body[3] + body[4]
    elif last == "4":
        manufacturer = body[0] + body[1] + body[2] + body[3] + "0"
        product = "0000" + body[4]
    else:  # 5–9
        manufacturer = body[0] + body[1] + body[2] + body[3] + body[4]
        product = "0000" + last

    return number_system + manufacturer + product + check


def barcode_variants(upc: str) -> list[str]:
    """Return barcode formats commonly used by lookup APIs."""
    variants: list[str] = []

    def add(code: str) -> None:
        code = code.strip()
        if code and code not in variants:
            variants.append(code)

    add(upc)

    # A scanned 8-digit code may be a compressed UPC-E; databases store the
    # expanded UPC-A (and its EAN-13). Add both so the product still matches.
    expanded = expand_upce(upc)
    if expanded:
        add(expanded)
        add(f"0{expanded}")

    if len(upc) == 12:
        add(f"0{upc}")
    elif len(upc) == 13 and upc.startswith("0"):
        add(upc[1:])
    if len(upc) < 13:
        add(upc.zfill(13))
    if len(upc) < 12:
        add(upc.zfill(12))
    return variants


def _fetch_json(url: str, *, accept: str = "application/json") -> dict:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": accept},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.load(response)
    except urllib.error.HTTPError as err:
        if err.code == 404:
            body = err.read()
            if body:
                try:
                    return json.loads(body)
                except json.JSONDecodeError:
                    pass
        raise


def _clean_tag_list(value: str, *, max_items: int = 8) -> str:
    """Turn OFF comma/colon tag strings into readable comma-separated text."""
    parts: list[str] = []
    for raw in value.split(","):
        tag = raw.split(":")[-1].replace("-", " ").strip()
        if not tag or len(tag) <= 2:
            continue
        if tag.lower() not in [p.lower() for p in parts]:
            parts.append(tag)
    return ", ".join(parts[:max_items])


def _parse_open_facts(data: dict, upc: str) -> UPCLookupResult | None:
    if data.get("status") != 1:
        return None

    product = data.get("product", {})
    name = (
        product.get("product_name")
        or product.get("product_name_en")
        or product.get("generic_name")
        or product.get("abbreviated_product_name")
        or product.get("product_name_fr")
        or product.get("title")
        or ""
    ).strip()
    if not name:
        return None

    brand = (product.get("brands") or "").strip()
    categories = _clean_tag_list(product.get("categories") or "")
    labels = _clean_tag_list(product.get("labels") or product.get("labels_tags") or "")

    quantity = (product.get("quantity") or "").strip()
    if quantity and quantity.lower() not in categories.lower():
        categories = f"{categories}, {quantity}" if categories else quantity

    image_url = product.get("image_front_url") or product.get("image_url")

    return UPCLookupResult(
        found=True,
        upc=upc,
        name=name,
        brand=brand,
        categories=categories,
        labels=labels,
        image_url=image_url,
    )


def _parse_upcitemdb(data: dict, upc: str) -> UPCLookupResult | None:
    items = data.get("items") or []
    if not items:
        return None

    item = items[0]
    name = (item.get("title") or "").strip()
    if not name:
        return None

    brand = (item.get("brand") or "").strip()
    category = (item.get("category") or "").strip()
    categories = category.replace(" > ", ", ") if category else ""
    images = item.get("images") or []
    image_url = images[0] if images else None

    return UPCLookupResult(
        found=True,
        upc=upc,
        name=name,
        brand=brand,
        categories=categories,
        image_url=image_url,
    )


def _try_source(
    lookup: Callable[[str], UPCLookupResult | None],
    upc: str,
) -> UPCLookupResult | None:
    for code in barcode_variants(upc):
        result = lookup(code)
        if result:
            result.upc = upc
            return result
    return None


def lookup_upc(value: str) -> UPCLookupResult:
    """Look up a UPC online across food, beauty, general, and retail databases."""
    upc = normalize_upc(value)
    if not upc:
        return UPCLookupResult(found=False, upc=value.strip(), error="Enter a valid 8–14 digit UPC.")

    sources: list[tuple[str, Callable[[str], UPCLookupResult | None]]] = [
        (
            "Open Food Facts",
            lambda code: _parse_open_facts(_fetch_json(OFF_URL.format(code)), code),
        ),
        (
            "Open Products Facts",
            lambda code: _parse_open_facts(_fetch_json(OPF_URL.format(code)), code),
        ),
        (
            "Open Beauty Facts",
            lambda code: _parse_open_facts(_fetch_json(OBF_URL.format(code)), code),
        ),
        (
            "Open Pet Food Facts",
            lambda code: _parse_open_facts(_fetch_json(OPFF_URL.format(code)), code),
        ),
        (
            "UPCitemdb",
            lambda code: _parse_upcitemdb(_fetch_json(UPCITEMDB_URL.format(code)), code),
        ),
    ]

    rate_limited = False
    for source_name, lookup in sources:
        try:
            result = _try_source(lookup, upc)
            if result:
                result.source = source_name
                return result
        except urllib.error.HTTPError as err:
            if source_name == "UPCitemdb" and err.code == 429:
                rate_limited = True
                continue
            if source_name == "UPCitemdb" and err.code in {400, 404}:
                continue
            if err.code >= 500:
                continue
        except urllib.error.URLError as err:
            return UPCLookupResult(
                found=False,
                upc=upc,
                error=f"Could not reach lookup service. Check your internet connection.\n{err}",
            )
        except Exception:
            continue

    if rate_limited:
        return UPCLookupResult(
            found=False,
            upc=upc,
            error="Lookup rate limit reached. Wait a moment and try again, or enter details manually.",
        )

    return UPCLookupResult(
        found=False,
        upc=upc,
        error="No product found for this UPC in food, pet, beauty, general, or retail databases. Try entering details manually.",
    )
