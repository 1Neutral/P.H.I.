"""Product lookup via UPC databases and Amazon ASIN pages."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from typing import Callable

USER_AGENT = "PHI-Inventory/0.1 (personal home inventory)"
OFF_URL = "https://world.openfoodfacts.org/api/v2/product/{}.json"
OBF_URL = "https://world.openbeautyfacts.org/api/v2/product/{}.json"
OPF_URL = "https://world.openproductsfacts.org/api/v2/product/{}.json"
OPFF_URL = "https://world.openpetfoodfacts.org/api/v2/product/{}.json"
UPCITEMDB_URL = "https://api.upcitemdb.com/prod/trial/lookup?upc={}"
OPENLIBRARY_URL = "https://openlibrary.org/isbn/{}.json"
OPENLIBRARY_COVER_URL = "https://covers.openlibrary.org/b/isbn/{}-L.jpg?default=false"
AMAZON_PRODUCT_URL = "https://www.amazon.com/dp/{}"
AMAZON_SEARCH_URL = "https://www.amazon.com/s?k={}"
ASIN_PATTERN = re.compile(r"B[A-Z0-9]{9}")
AMAZON_DP_LINK_PATTERN = re.compile(r"/dp/(B[A-Z0-9]{9})")
AMAZON_SEARCH_MAX_CANDIDATES = 3
AMAZON_SEARCH_ATTEMPTS = 3


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
    code_type: str = "UPC"


def normalize_upc(value: str) -> str | None:
    """Return digits-only UPC if valid (8–14 digits), else None."""
    digits = re.sub(r"\D", "", value.strip())
    if 8 <= len(digits) <= 14:
        return digits
    return None


def normalize_asin(value: str) -> str | None:
    """Return an uppercase Amazon ASIN, or None when the value is not one."""
    code = re.sub(r"[\s-]", "", value).upper()
    return code if ASIN_PATTERN.fullmatch(code) else None


def normalize_product_code(value: str) -> tuple[str, str] | None:
    """Normalize a supported product code and return (code, type)."""
    asin = normalize_asin(value)
    if asin:
        return asin, "ASIN"
    if re.search(r"[A-Za-z]", value):
        return None
    upc = normalize_upc(value)
    if upc:
        return upc, numeric_code_type(upc)
    return None


def numeric_code_type(value: str) -> str:
    """Identify the standard represented by a normalized numeric barcode."""
    if len(value) == 8:
        # EAN-8 and compressed UPC-E have the same length and require database
        # context to distinguish, so retain both names in the UI.
        return "EAN-8 / UPC-E"
    if len(value) == 13:
        return "ISBN" if value.startswith(("978", "979")) else "EAN-13"
    if len(value) == 14:
        return "GTIN-14"
    return "UPC"


def product_code_label(value: str) -> str:
    """Return the display label for a stored product identifier."""
    if normalize_asin(value):
        return "ASIN"
    normalized = normalize_upc(value)
    return numeric_code_type(normalized) if normalized else "Product code"


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


def _fetch_html(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return response.read().decode(response.headers.get_content_charset() or "utf-8", "replace")


class _AmazonProductParser(HTMLParser):
    """Extract stable product fields without depending on Amazon's full DOM."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.brand = ""
        self.image_url: str | None = None
        self._capture: str | None = None
        self._capture_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._capture:
            self._capture_depth += 1

        attributes = dict(attrs)
        element_id = attributes.get("id")
        if not self._capture and element_id in {"productTitle", "bylineInfo"}:
            self._capture = "title" if element_id == "productTitle" else "brand"
            self._capture_depth = 1
            self._parts = []

        if tag == "meta":
            property_name = attributes.get("property") or attributes.get("name")
            content = (attributes.get("content") or "").strip()
            if property_name == "og:title" and content and not self.title:
                self.title = content
            elif property_name == "og:image" and content and not self.image_url:
                self.image_url = content

        if element_id == "landingImage" and not self.image_url:
            self.image_url = attributes.get("data-old-hires") or attributes.get("src")

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._parts.append(data)

    def handle_endtag(self, _tag: str) -> None:
        if not self._capture:
            return
        self._capture_depth -= 1
        if self._capture_depth:
            return

        value = " ".join(" ".join(self._parts).split())
        if self._capture == "title" and value:
            self.title = value
        elif self._capture == "brand" and value:
            self.brand = value
        self._capture = None
        self._parts = []


def _clean_amazon_brand(value: str) -> str:
    value = value.strip()
    match = re.fullmatch(r"Visit the (.+) Store", value, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip()
    match = re.fullmatch(r"Brand:\s*(.+)", value, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return value


def _clean_amazon_title(value: str) -> str:
    value = " ".join(value.split())
    if value.startswith("Amazon.com: "):
        value = value.removeprefix("Amazon.com: ")
        value = re.sub(r"\s*:\s*Amazon(?:\.com)?\s*$", "", value)
    return value.strip()


def _parse_amazon_product(html: str, asin: str) -> UPCLookupResult | None:
    parser = _AmazonProductParser()
    parser.feed(html)
    name = _clean_amazon_title(parser.title)
    if not name or name in {"Amazon.com", "Robot Check"}:
        return None
    brand = _clean_amazon_brand(parser.brand)
    if not brand:
        brand_match = re.search(
            r">\s*Brand(?:\s+Name)?\s*</th>\s*<td[^>]*>(.*?)</td>",
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if brand_match:
            brand = " ".join(
                unescape(re.sub(r"<[^>]+>", " ", brand_match.group(1))).split()
            )
    return UPCLookupResult(
        found=True,
        upc=asin,
        name=name,
        brand=brand,
        image_url=parser.image_url,
        source="Amazon",
        code_type="ASIN",
    )


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


def _is_bookland_ean(upc: str) -> bool:
    """True when the EAN-13 is an ISBN (Bookland prefixes 978/979)."""
    return len(upc) == 13 and upc.startswith(("978", "979"))


def _parse_openlibrary(data: dict, isbn: str) -> UPCLookupResult | None:
    name = (data.get("title") or "").strip()
    if not name:
        return None
    subtitle = (data.get("subtitle") or "").strip()
    if subtitle:
        name = f"{name}: {subtitle}"

    publishers = data.get("publishers") or []
    brand = str(publishers[0]).strip() if publishers else ""

    return UPCLookupResult(
        found=True,
        upc=isbn,
        name=name,
        brand=brand,
        categories="Books",
        image_url=OPENLIBRARY_COVER_URL.format(isbn),
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
    """Look up a UPC, EAN, or GTIN across product databases."""
    upc = normalize_upc(value)
    if not upc:
        return UPCLookupResult(
            found=False,
            upc=value.strip(),
            error="Enter a valid 8–14 digit UPC, EAN, or GTIN.",
        )
    code_type = numeric_code_type(upc)

    sources: list[tuple[str, Callable[[str], UPCLookupResult | None]]] = []

    if _is_bookland_ean(upc):
        sources.append(
            (
                "Open Library",
                lambda code: _parse_openlibrary(_fetch_json(OPENLIBRARY_URL.format(code)), code),
            )
        )

    sources += [
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
                result.code_type = code_type
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
                code_type=code_type,
                error=f"Could not reach lookup service. Check your internet connection.\n{err}",
            )
        except Exception:
            continue

    amazon_result = _search_amazon_by_barcode(upc)
    if amazon_result:
        return amazon_result

    if rate_limited:
        return UPCLookupResult(
            found=False,
            upc=upc,
            code_type=code_type,
            error="Lookup rate limit reached. Wait a moment and try again, or enter details manually.",
        )

    return UPCLookupResult(
        found=False,
        upc=upc,
        code_type=code_type,
        error=(
            f"No product found for this {code_type} in food, pet, beauty, general, "
            "or retail databases. Try entering details manually."
        ),
    )


def _search_amazon_by_barcode(upc: str) -> UPCLookupResult | None:
    """Resolve a barcode to a product via Amazon search, as a last resort.

    Amazon search returns ads and unrelated recommendations alongside real
    matches, so a candidate ASIN only counts when its product page actually
    lists the scanned barcode (any variant) in the product details.
    """
    variants = set(barcode_variants(upc))

    # Amazon intermittently serves a stripped-down page with no results;
    # retry a couple of times before concluding the search found nothing.
    candidates: list[str] = []
    for _attempt in range(AMAZON_SEARCH_ATTEMPTS):
        try:
            search_html = _fetch_html(AMAZON_SEARCH_URL.format(upc))
        except Exception:
            return None
        candidates = list(dict.fromkeys(AMAZON_DP_LINK_PATTERN.findall(search_html)))
        if candidates:
            break

    for asin in candidates[:AMAZON_SEARCH_MAX_CANDIDATES]:
        try:
            product_html = _fetch_html(AMAZON_PRODUCT_URL.format(asin))
        except Exception:
            continue
        if not any(variant in product_html for variant in variants):
            continue
        result = _parse_amazon_product(product_html, asin)
        if result:
            result.upc = upc
            result.code_type = numeric_code_type(upc)
            result.source = "Amazon search"
            return result
    return None


def lookup_asin(value: str) -> UPCLookupResult:
    """Look up an Amazon product from its ASIN without requiring an API key."""
    asin = normalize_asin(value)
    if not asin:
        return UPCLookupResult(
            found=False,
            upc=value.strip(),
            code_type="ASIN",
            error="Enter a valid 10-character ASIN beginning with B.",
        )

    try:
        html = _fetch_html(AMAZON_PRODUCT_URL.format(asin))
        result = _parse_amazon_product(html, asin)
        if result:
            return result
    except urllib.error.HTTPError as err:
        if err.code not in {403, 404, 429, 503}:
            return UPCLookupResult(
                found=False,
                upc=asin,
                code_type="ASIN",
                error=f"Amazon lookup failed (HTTP {err.code}).",
            )
    except urllib.error.URLError as err:
        return UPCLookupResult(
            found=False,
            upc=asin,
            code_type="ASIN",
            error=f"Could not reach Amazon. Check your internet connection.\n{err}",
        )
    except Exception:
        pass

    return UPCLookupResult(
        found=False,
        upc=asin,
        code_type="ASIN",
        error=(
            "Amazon did not return product details for this ASIN. "
            "The listing may be unavailable or Amazon may be temporarily blocking automated requests."
        ),
    )


def lookup_product(value: str) -> UPCLookupResult:
    """Look up either a UPC/EAN barcode or an Amazon ASIN."""
    normalized = normalize_product_code(value)
    if not normalized:
        return UPCLookupResult(
            found=False,
            upc=value.strip(),
            error=(
                "Enter a valid UPC/EAN/GTIN (8–14 digits) "
                "or ASIN (B plus 9 letters/digits)."
            ),
        )
    code, code_type = normalized
    if code_type == "ASIN":
        return lookup_asin(code)
    return lookup_upc(code)
