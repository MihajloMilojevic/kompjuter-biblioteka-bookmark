"""
dedup.py — Privremena skripta za uklanjanje duplikata iz books.json

Pokretanje:
    python dedup.py

Kreira backup (books.json.bak) pre izmena.
"""

import json
import shutil
from pathlib import Path

DATA_FILE = Path(__file__).parent / "books.json"

if not DATA_FILE.exists():
    print("❌ books.json nije pronađen.")
    exit(1)

# Backup
backup = DATA_FILE.with_suffix(".json.bak")
shutil.copy(DATA_FILE, backup)
print(f"✅ Backup sačuvan: {backup}")

with open(DATA_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)

books = data.get("books", [])
print(f"📚 Knjiga pre: {len(books)}")

seen_urls = {}
duplicates = 0

for b in books:
    url = b.get("url", "")
    if not url:
        continue

    if url not in seen_urls:
        seen_urls[url] = b
    else:
        duplicates += 1
        existing = seen_urls[url]

        # Spoji oblasti liste
        prev = existing.get("oblasti", [existing["oblast"]] if existing.get("oblast") else [])
        curr = b.get("oblasti", [b["oblast"]] if b.get("oblast") else [])
        merged = list(dict.fromkeys(prev + curr))
        existing["oblasti"] = merged
        if merged:
            existing["oblast"] = merged[0]

        # Sačuvaj status/belešku ako nova kopija ima a stara nema
        if not existing.get("status") and b.get("status"):
            existing["status"] = b["status"]
        if not existing.get("beleska") and b.get("beleska"):
            existing["beleska"] = b["beleska"]

deduped = list(seen_urls.values())
print(f"🗑️  Uklonjeno duplikata: {duplicates}")
print(f"📚 Knjiga posle: {len(deduped)}")

data["books"] = deduped
with open(DATA_FILE, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("✅ books.json ažuriran.")
print(f"   (Za povratak: cp {backup} {DATA_FILE})")
