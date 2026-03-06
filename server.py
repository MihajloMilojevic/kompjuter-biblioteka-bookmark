"""
server.py — Knjige Beležnica Backend
Pokreni: python server.py
Zatim otvori: http://localhost:5000
"""

import json
import os
import re
import threading
import time
import uuid
import logging
from datetime import datetime
from pathlib import Path

import requests as http_requests
from bs4 import BeautifulSoup

from flask import Flask, jsonify, request, send_from_directory, Response
from flask_cors import CORS

from scraper import (
    scrape_all_areas, scrape_special,
    get_all_areas, SPECIAL_COLLECTIONS,
    clean, parse_price,
)

# ──────────────────────────────────────────────
# SETUP
# ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent
DATA_FILE = BASE_DIR / "books.json"
STATIC_DIR = BASE_DIR / "static"

app = Flask(__name__, static_folder=str(STATIC_DIR))
CORS(app)

# ──────────────────────────────────────────────
# DATA LAYER
# ──────────────────────────────────────────────
def load_data():
    if DATA_FILE.exists():
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"books": [], "meta": {"last_scrape": None, "total_scraped": 0}}


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def make_id():
    return str(uuid.uuid4())[:8]


# ──────────────────────────────────────────────
# SCRAPE JOB (background thread)
# ──────────────────────────────────────────────
scrape_state = {
    "running": False,
    "progress": 0,          # 0–100
    "current_area": "",
    "current_page": 0,
    "total_pages": 0,
    "found": 0,
    "areas_done": 0,
    "areas_total": 0,
    "log": [],
    "error": None,
    "finished_at": None,
}


def run_scrape(area_ids=None, include_special=None):
    global scrape_state
    all_areas = get_all_areas()
    n_areas   = len(area_ids) if area_ids is not None else len(all_areas)
    n_special = len(include_special) if include_special else 0
    scrape_state.update({
        "running": True,
        "progress": 0,
        "found": 0,
        "areas_done": 0,
        "areas_total": n_areas + n_special,
        "log": [],
        "error": None,
        "finished_at": None,
    })

    def cb(area_name, page, total_pages, new_books):
        scrape_state["current_area"] = area_name
        scrape_state["current_page"] = page
        scrape_state["total_pages"] = total_pages
        scrape_state["found"] += new_books
        if page == total_pages:
            scrape_state["areas_done"] += 1
        done  = scrape_state["areas_done"]
        total = scrape_state["areas_total"]
        scrape_state["progress"] = int(done / total * 100) if total else 0
        msg = f"[{area_name}] strana {page}/{total_pages} — {new_books} knjiga"
        scrape_state["log"].append(msg)
        logger.info(msg)

    try:
        all_books = scrape_all_areas(area_ids=area_ids, include_special=include_special, progress_callback=cb)

        # Merge sa postojećim podacima — čuvamo user podatke (status, beleške)
        # all_books je već deduplikovan po URL-u iz scrapera
        data = load_data()
        existing = {b["url"]: b for b in data["books"]}
        seen_urls = set()
        merged = []

        for b in all_books:
            url = b["url"]
            if url in seen_urls:
                continue  # duplikat — preskočiti (ne bi trebalo, ali sigurnost)
            seen_urls.add(url)

            if url in existing:
                prev = existing[url]
                b["id"]     = prev.get("id", make_id())
                b["status"] = prev.get("status", "")
                b["beleska"]= prev.get("beleska", "")
                b["dodat"]  = prev.get("dodat", "")
                # Spoji oblasti liste (stare + nove, bez duplikata)
                prev_oblasti = prev.get("oblasti", [prev["oblast"]] if prev.get("oblast") else [])
                new_oblasti  = b.get("oblasti", [b["oblast"]] if b.get("oblast") else [])
                combined = list(dict.fromkeys(prev_oblasti + new_oblasti))  # preserves order, deduplicates
                b["oblasti"] = combined
                b["oblast"]  = combined[0] if combined else ""
            else:
                b["id"]     = make_id()
                b["status"] = ""
                b["beleska"]= ""
                b["dodat"]  = datetime.now().isoformat()
                if not b.get("oblasti"):
                    b["oblasti"] = [b["oblast"]] if b.get("oblast") else []
            merged.append(b)

        # Dodaj ručno unete knjige (izvor == "manual") — nikad ih ne brišemo
        for b in data["books"]:
            if b.get("izvor") == "manual" and b["url"] not in seen_urls:
                merged.append(b)

        data["books"] = merged
        data["meta"]["last_scrape"] = datetime.now().isoformat()
        data["meta"]["total_scraped"] = len(merged)
        save_data(data)

        scrape_state["progress"] = 100
        scrape_state["finished_at"] = datetime.now().isoformat()
        logger.info(f"Scraping završen! Ukupno {len(merged)} knjiga.")

    except Exception as e:
        scrape_state["error"] = str(e)
        logger.exception("Greška u scraperu")
    finally:
        scrape_state["running"] = False


# ──────────────────────────────────────────────
# ROUTES — STATIC
# ──────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory(str(STATIC_DIR), "index.html")


# ──────────────────────────────────────────────
# ROUTES — BOOKS API
# ──────────────────────────────────────────────
@app.route("/api/books", methods=["GET"])
def get_books():
    data = load_data()
    books = data["books"]

    # Filteri
    q = request.args.get("q", "").lower()
    status = request.args.get("status", "")
    oblast = request.args.get("oblast", "")
    akcija = request.args.get("akcija", "")

    if q:
        books = [b for b in books if q in b.get("naslov","").lower() or q in b.get("autor","").lower()]
    if status:
        books = [b for b in books if b.get("status") == status]
    if oblast:
        def matches_oblast(b, o):
            if b.get("oblast") == o:
                return True
            return o in b.get("oblasti", [])
        books = [b for b in books if matches_oblast(b, oblast)]
    if akcija == "1":
        books = [b for b in books if b.get("akcija")]

    return jsonify({
        "books": books,
        "total": len(books),
        "meta": data.get("meta", {})
    })


@app.route("/api/books", methods=["POST"])
def add_book():
    """Ručno dodavanje knjige."""
    body = request.get_json()
    if not body or not body.get("naslov"):
        return jsonify({"error": "Naslov je obavezan"}), 400

    data = load_data()
    book = {
        "id": make_id(),
        "naslov": body.get("naslov", "").strip(),
        "autor": body.get("autor", "").strip(),
        "oblast": body.get("oblast", "Ostalo").strip() or "Ostalo",
        "oblasti": body.get("oblasti") or ([body.get("oblast")] if body.get("oblast") else []),
        "oblast_id": 0,
        "godina": body.get("godina"),
        "strane": body.get("strane"),
        "cena_originalna": body.get("cena_originalna"),
        "cena_snizena": body.get("cena_snizena"),
        "akcija": bool(body.get("akcija")),
        "url": body.get("url", "").strip(),
        "slika": body.get("slika", "").strip(),
        "isbn": body.get("isbn", "").strip(),
        "opis": body.get("opis", "").strip(),
        "status": body.get("status", ""),
        "beleska": body.get("beleska", ""),
        "izvor": "manual",
        "dodat": datetime.now().isoformat(),
    }
    data["books"].append(book)
    save_data(data)
    return jsonify(book), 201


@app.route("/api/books/<book_id>", methods=["PUT"])
def update_book(book_id):
    data = load_data()
    book = next((b for b in data["books"] if b["id"] == book_id), None)
    if not book:
        return jsonify({"error": "Knjiga nije pronađena"}), 404

    body = request.get_json()
    allowed = ["status", "beleska", "naslov", "autor", "oblast", "godina",
               "strane", "cena_originalna", "cena_snizena", "akcija",
               "url", "slika", "isbn", "opis"]
    for field in allowed:
        if field in body:
            book[field] = body[field]

    save_data(data)
    return jsonify(book)


@app.route("/api/books/<book_id>", methods=["DELETE"])
def delete_book(book_id):
    data = load_data()
    before = len(data["books"])
    data["books"] = [b for b in data["books"] if b["id"] != book_id]
    if len(data["books"]) == before:
        return jsonify({"error": "Knjiga nije pronađena"}), 404
    save_data(data)
    return jsonify({"ok": True})


# ──────────────────────────────────────────────
# ROUTES — SCRAPE API
# ──────────────────────────────────────────────
@app.route("/api/scrape/start", methods=["POST"])
def scrape_start():
    if scrape_state["running"]:
        return jsonify({"error": "Scraping je već u toku"}), 409

    body = request.get_json() or {}
    area_ids        = body.get("areas")    # lista ID-ova ili null za sve oblasti
    include_special = body.get("special")  # lista slugova ili null

    t = threading.Thread(target=run_scrape, kwargs={"area_ids": area_ids, "include_special": include_special}, daemon=True)
    t.start()
    return jsonify({"ok": True, "message": "Scraping pokrenut"})


@app.route("/api/scrape/status", methods=["GET"])
def scrape_status():
    return jsonify(dict(scrape_state))


@app.route("/api/scrape/stop", methods=["POST"])
def scrape_stop():
    # Soft stop — ne može zaista zaustaviti thread, ali označava flag
    scrape_state["running"] = False
    return jsonify({"ok": True})


# ──────────────────────────────────────────────
# ROUTES — META
# ──────────────────────────────────────────────
@app.route("/api/areas", methods=["GET"])
def get_areas():
    areas   = get_all_areas()
    special = [{"slug": k, "name": v[0]} for k, v in SPECIAL_COLLECTIONS.items()]
    return jsonify({
        "areas":   [{"id": k, "name": v} for k, v in sorted(areas.items(), key=lambda x: x[1])],
        "special":  special,
    })


@app.route("/api/areas/refresh", methods=["POST"])
def refresh_areas():
    """Prisiljava re-discovery oblasti sa sajta (briše keš)."""
    from scraper import discover_areas
    areas = discover_areas(force=True)
    return jsonify({
        "ok": True,
        "count": len(areas),
        "areas": [{"id": k, "name": v} for k, v in sorted(areas.items(), key=lambda x: x[1])],
    })


@app.route("/api/stats", methods=["GET"])
def get_stats():
    data = load_data()
    books = data["books"]
    statuses = {}
    for b in books:
        s = b.get("status") or "bez_statusa"
        statuses[s] = statuses.get(s, 0) + 1

    oblasti = {}
    for b in books:
        o = b.get("oblast", "Ostalo")
        oblasti[o] = oblasti.get(o, 0) + 1

    bez_statusa = sum(1 for b in books if not b.get("status"))
    return jsonify({
        "ukupno": len(books),
        "statusi": statuses,
        "oblasti": oblasti,
        "na_akciji": sum(1 for b in books if b.get("akcija")),
        "bez_statusa": bez_statusa,
        "rucno_dodato": sum(1 for b in books if b.get("izvor") == "manual"),
        "meta": data.get("meta", {}),
    })


@app.route("/api/popust", methods=["POST"])
def get_popust():
    """
    POSTuje kod na kombib.rs/popust-kod.php koristeći pravo ime polja (popKOD),
    parsira <select name="knjiga[]"> i ukršta sa lokalnom bazom.
    """
    body = request.get_json() or {}
    kod  = (body.get("kod") or "").strip()
    if not kod:
        return jsonify({"error": "Kod je obavezan"}), 400

    HDRS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer":  "https://kombib.rs/popust-kod.php",
        "Origin":   "https://kombib.rs",
        "Accept":   "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "sr,en;q=0.9",
    }

    try:
        session = http_requests.Session()
        # Korak 1: GET da dobijemo cookies/session
        session.get("https://kombib.rs/popust-kod.php", headers=HDRS, timeout=15)

        # Korak 2: POST sa pravim imenom polja "popKOD" i submit dugmetom "Dalje"
        resp = session.post(
            "https://kombib.rs/popust-kod.php",
            data={"popKOD": kod, "button": "Dalje"},
            headers=HDRS,
            timeout=20,
        )
        resp.encoding = "utf-8"
    except Exception as e:
        return jsonify({"error": f"Nije moguće kontaktirati kombib.rs: {e}"}), 502

    soup = BeautifulSoup(resp.text, "html.parser")

    # Knjige su u <select name="knjiga[]" multiple>
    select = soup.find("select", {"name": re.compile(r'knjiga')})
    if not select:
        page_text = soup.get_text()
        return jsonify({
            "error": "Nije pronađen spisak knjiga. Provjeri da li je kod tačan.",
            "knjige": [],
            "debug": {
                "html_length": len(resp.text),
                "inputs": [(i.get("name"), i.get("value","")) for i in soup.find_all("input")],
                "selects": [s.get("name") for s in soup.find_all("select")],
                "snippet": resp.text[3000:5000],
            }
        }), 200

    options = select.find_all("option")
    if not options:
        return jsonify({"error": "Kod je validan ali nema knjiga na listi.", "knjige": []}), 200

    raw_books = [
        {"knjiga_id": o.get("value", ""), "naslov": clean(o.get_text())}
        for o in options if o.get("value")
    ]

    # Ukrsti sa lokalnom bazom po naslovu
    data = load_data()

    def norm(s):
        s = (s or "").lower()
        for a, b_c in [("č","c"),("ć","c"),("š","s"),("ž","z"),("đ","dj"),("dž","dz")]:
            s = s.replace(a, b_c)
        return re.sub(r'[^a-z0-9 ]', '', s).strip()

    local_by_norm = {}
    for b in data["books"]:
        key = norm(b["naslov"])
        local_by_norm[key] = b
        local_by_norm[key[:30]] = b

    def find_local(naslov):
        n = norm(naslov)
        if n in local_by_norm:
            return local_by_norm[n]
        if n[:30] in local_by_norm:
            return local_by_norm[n[:30]]
        for key, book in local_by_norm.items():
            if len(n) > 10 and (n[:20] in key or key[:20] in n):
                return book
        return None

    result = []
    for rb in raw_books:
        local = find_local(rb["naslov"])
        result.append({
            "knjiga_id": rb["knjiga_id"],
            "naslov":    rb["naslov"],
            "autor":     local.get("autor", "") if local else "",
            "slika":     local.get("slika", "") if local else "",
            "godina":    local.get("godina") if local else None,
            "oblast":    local.get("oblast", "") if local else "",
            "url":       local.get("url", "") if local else "",
            "cena_orig": local.get("cena_originalna") if local else None,
            "in_db":     local is not None,
            "db_id":     local["id"] if local else None,
            "status":    local.get("status", "") if local else "",
            "beleska":   local.get("beleska", "") if local else "",
        })

    return jsonify({
        "kod":    kod,
        "knjige": result,
        "ukupno": len(result),
    })


@app.route("/api/popust/debug", methods=["POST"])
def popust_debug():
    """
    Dijagnostički endpoint — vraća sirovi HTML i šta je pronađeno,
    bez ukrštanja sa bazom. Otvori http://localhost:5000/api/popust/debug
    sa POST {"kod":"SolaR2026"} da vidiš šta server stvarno prima.
    """
    body = request.get_json() or {}
    kod  = (body.get("kod") or "").strip()
    if not kod:
        return jsonify({"error": "Kod je obavezan"}), 400

    HDRS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": "https://kombib.rs/popust-kod.php",
        "Origin":  "https://kombib.rs",
    }

    # Pokušaj sve kombinacije naziva polja
    attempts = []
    for field_name in ["kod", "popust_kod", "code", "sifra", "kupon", "discount_code"]:
        try:
            r = http_requests.post(
                "https://kombib.rs/popust-kod.php",
                data={field_name: kod},
                headers=HDRS,
                timeout=15,
            )
            r.encoding = "utf-8"
            soup = BeautifulSoup(r.text, "html.parser")
            select = soup.find("select", {"name": re.compile(r'knjiga')})
            options_count = len(select.find_all("option")) if select else 0
            all_selects = [(s.get("name","?"), len(s.find_all("option")))
                           for s in soup.find_all("select")]
            all_inputs  = [(i.get("name","?"), i.get("type","?"), i.get("value",""))
                           for i in soup.find_all("input")]
            attempts.append({
                "field_name":     field_name,
                "http_status":    r.status_code,
                "html_length":    len(r.text),
                "select_found":   select is not None,
                "options_count":  options_count,
                "all_selects":    all_selects,
                "all_inputs":     all_inputs,
                "html_snippet":   r.text[2000:4000],  # srednji deo HTML-a
            })
            if options_count > 0:
                break  # Pronašli smo pravo polje!
        except Exception as e:
            attempts.append({"field_name": field_name, "error": str(e)})

    return jsonify({"attempts": attempts, "kod": kod})


# ──────────────────────────────────────────────
# ROUTE — FETCH BOOK FROM URL
# ──────────────────────────────────────────────
@app.route("/api/fetch-book", methods=["POST"])
def fetch_book_from_url():
    """
    Prima URL knjige sa knjige.kombib.rs, scrape-uje stranicu
    i vraća sve podatke popunjene, spremne za formu.
    """
    body = request.get_json() or {}
    url  = (body.get("url") or "").strip()

    if not url:
        return jsonify({"error": "URL je obavezan"}), 400
    if "kombib.rs" not in url:
        return jsonify({"error": "URL mora biti sa kombib.rs"}), 400

    HDRS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "sr,en;q=0.9",
    }

    try:
        resp = http_requests.get(url, headers=HDRS, timeout=20)
        resp.encoding = "utf-8"
    except Exception as e:
        return jsonify({"error": f"Nije moguće učitati stranicu: {e}"}), 502

    soup = BeautifulSoup(resp.text, "html.parser")
    text = soup.get_text(separator=" ")

    # Naslov — h1 ili prvi h2
    naslov = ""
    h1 = soup.find("h1")
    if h1:
        naslov = clean(h1.get_text())
    if not naslov:
        h2 = soup.find("h2")
        if h2:
            naslov = clean(h2.get_text())

    # Autor — drugi h2 ili meta
    autor = ""
    h2s = soup.find_all("h2")
    if len(h2s) >= 2:
        autor = clean(h2s[1].get_text()).replace("*", "").strip()

    # Oblast(i) iz breadcrumb / sidebar linkova koji se poklapaju sa poznatim oblastima
    all_areas = get_all_areas()
    oblasti = []
    oblast_ids = []
    for a in soup.find_all("a", href=re.compile(r"oblasti-knjiga-(\d+)-")):
        m = re.search(r"oblasti-knjiga-(\d+)-", a.get("href", ""))
        if m:
            aid = int(m.group(1))
            aname = clean(a.get_text())
            if not aname:
                aname = all_areas.get(aid, str(aid))
            if aname and aname not in oblasti:
                oblasti.append(aname)
                oblast_ids.append(aid)

    # Fallback — iz sidebara aktivan link
    if not oblasti:
        for a in soup.find_all("a", class_=re.compile(r"active|current|selected")):
            href = a.get("href", "")
            m = re.search(r"oblasti-knjiga-(\d+)-", href)
            if m:
                aid = int(m.group(1))
                oblasti.append(all_areas.get(aid, str(aid)))
                oblast_ids.append(aid)
                break

    # Slika — kombib naslovnica uvek ima alt=naslov i src u /images/ putanji
    slika = ""

    def make_abs(src):
        if not src: return ""
        if src.startswith("http"): return src
        if src.startswith("//"): return "https:" + src
        if src.startswith("/"): return "https://kombib.rs" + src
        return ""

    # Pokušaj 1: img čiji alt ili title odgovara naslovu knjige (najpouzdanije)
    if naslov:
        for img in soup.find_all("img", alt=True):
            if naslov.lower()[:20] in img["alt"].lower():
                candidate = make_abs(img.get("src", ""))
                if candidate:
                    slika = candidate
                    break

    # Pokušaj 2: img čiji src sadrži /images/ (kombib pattern za naslovnice)
    if not slika:
        for img in soup.find_all("img"):
            src = img.get("src", "")
            if "/images/" in src and "resp-dizajn" not in src:
                candidate = make_abs(src)
                if candidate:
                    slika = candidate
                    break

    # Pokušaj 3: prvi img sa alt koji nije prazan i nije UI element
    if not slika:
        skip = ("meni", "logo", "icon", "banner", "spacer", "gif", "resp-dizajn", "t-naran", "facebook", "twitter")
        for img in soup.find_all("img"):
            src = img.get("src", "")
            if not src or any(s in src.lower() for s in skip):
                continue
            candidate = make_abs(src)
            if candidate:
                slika = candidate
                break

    # Godina, strane, ISBN
    godina_m = re.search(r"Godina izdanja[:\s]*(\d{4})", text)
    strane_m = re.search(r"Stran[ae][:\s]*(\d+)", text)
    isbn_m   = re.search(r"ISBN[:\s]*([0-9\-X]{10,17})", text, re.IGNORECASE)

    # Cene
    cene = parse_price(text)
    cena_orig = cene[0] if cene else None
    cena_sniz = cene[-1] if len(cene) >= 2 and cene[-1] != cene[0] else None

    # Opis — najduži paragraf koji nije metapodatak
    opis = ""
    for tag in soup.find_all(["p", "div"]):
        t = clean(tag.get_text())
        if (len(t) > 80
                and "rsd" not in t.lower()
                and "Godina" not in t
                and "Naruči" not in t
                and "ISBN" not in t
                and len(t) > len(opis)):
            opis = t[:500]

    # Provjeri da li knjiga već postoji u bazi po URL-u
    data = load_data()
    existing = next((b for b in data["books"] if b.get("url") == url), None)

    return jsonify({
        "naslov":          naslov,
        "autor":           autor,
        "oblasti":         oblasti,
        "oblast_ids":      oblast_ids,
        "oblast":          oblasti[0] if oblasti else "",
        "godina":          int(godina_m.group(1)) if godina_m else None,
        "strane":          int(strane_m.group(1)) if strane_m else None,
        "cena_originalna": cena_orig,
        "cena_snizena":    cena_sniz,
        "slika":           slika,
        "isbn":            isbn_m.group(1) if isbn_m else "",
        "opis":            opis,
        "url":             url,
        # Ako knjiga postoji, vrati njen ID da frontend može da uradi PUT
        "existing_id":     existing["id"] if existing else None,
        "existing_status": existing.get("status", "") if existing else None,
        "existing_beleska":existing.get("beleska", "") if existing else None,
    })


@app.route("/api/export/csv", methods=["GET"])
def export_csv():
    import csv
    import io
    data = load_data()
    output = io.StringIO()
    w = csv.DictWriter(output, fieldnames=[
        "id","naslov","autor","oblast","godina","strane",
        "cena_originalna","cena_snizena","akcija",
        "url","slika","isbn","opis","status","beleska","izvor","dodat"
    ], extrasaction="ignore")
    w.writeheader()
    w.writerows(data["books"])
    from flask import Response
    return Response(
        "\ufeff" + output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=knjige.csv"}
    )


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────
if __name__ == "__main__":
    STATIC_DIR.mkdir(exist_ok=True)
    if not DATA_FILE.exists():
        save_data({"books": [], "meta": {"last_scrape": None, "total_scraped": 0}})
        logger.info("Kreirana prazna baza. Pokreni scraping iz aplikacije.")

    logger.info("=" * 50)
    logger.info("  Knjige Beležnica server pokrenut")
    logger.info("  Otvori: http://localhost:5000")
    logger.info("=" * 50)
    app.run(host="0.0.0.0", port=5000, debug=False)
