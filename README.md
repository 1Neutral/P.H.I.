# P.H.I. — Personal Home Inventory

A local desktop app for tracking your walk-in pantry (and beyond). Each item has a **location**, optional **brand / categories / labels**, plus multiple **units** with optional expiration and notes.

## Features

- **Per-unit tracking** — optional expiration (YYYY-MM-DD) and notes for every unit
- **Location** — one location per item (not per unit)
- **Brand, categories, labels** — optional fields to distinguish similar items; UPC lookup fills them automatically
- **Search** — matches name, location, brand, categories, labels, UPC/EAN/GTIN, and ASIN
- **Expandable items** — click an item to show its units; add/remove units inline; Edit/Duplicate/Remove appear when expanded
- **Photos** — upload an image per item (stored in `data/images/`)
- **UPC / EAN / ASIN lookup** — scan a UPC, EAN-8, EAN-13, GTIN-14, or Amazon ASIN to look up product details and a photo online (requires internet; ASIN lookup is best-effort because Amazon may block automated requests)
- **Edit / Remove / Duplicate** — duplicate opens the editor on a copy (handy for similar items)
- **Expiration tinting** (based on the *oldest* expiration among units):
  - **Blue** — not expired, or no expiration dates
  - **Green** — expired less than 1 year ago
  - **Yellow** — expired 1–3 years ago
  - **Red** — expired 3–5 years ago
  - **Black** — expired 5+ years ago (dispose warning)

Data is saved immediately to `data/inventory.json` on every change.

## Requirements

- Python 3.10+
- Linux, Windows, or macOS

## Setup (first time)

```bash
git clone https://github.com/1Neutral/phi.git
cd phi
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Launch for testing

Always start via `main.py` (it bootstraps fonts into `data/fonts/` before the UI opens):

```bash
source .venv/bin/activate   # skip if already active
python main.py
```

## Packaging (later)

When you're ready to ship a standalone binary:

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name PHI main.py
```

On Linux the output is a single executable in `dist/PHI`. On Windows, `dist/PHI.exe`.

## Data location

| Path | Purpose |
|------|---------|
| `data/inventory.json` | All inventory records |
| `data/images/` | Item photos |

Back up the `data/` folder to preserve your inventory.
