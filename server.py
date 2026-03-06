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

from scraper import scrape_all_areas, ALL_AREAS, clean, parse_price

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


def run_scrape(area_ids=None):
    global scrape_state
    scrape_state.update({
        "running": True,
        "progress": 0,
        "found": 0,
        "areas_done": 0,
        "areas_total": len(area_ids) if area_ids else len(ALL_AREAS),
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
        done = scrape_state["areas_done"]
        total = scrape_state["areas_total"]
        scrape_state["progress"] = int(done / total * 100) if total else 0
        msg = f"[{area_name}] strana {page}/{total_pages} — {new_books} knjiga"
        scrape_state["log"].append(msg)
        logger.info(msg)

    try:
        all_books = scrape_all_areas(area_ids=area_ids, progress_callback=cb)

        # Merge sa postojećim podacima — čuvamo user podatke (status, beleške)
        data = load_data()
        existing = {b["url"]: b for b in data["books"]}

        merged = []
        for b in all_books:
            key = b["url"]
            if key in existing:
                old = existing[key]
                # Sačuvaj user podatke
                b["id"] = old.get("id", make_id())
                b["status"] = old.get("status", "")
                b["beleska"] = old.get("beleska", "")
                b["dodat"] = old.get("dodat", "")
            else:
                b["id"] = make_id()
                b["status"] = ""
                b["beleska"] = ""
                b["dodat"] = datetime.now().isoformat()
            merged.append(b)

        # Dodaj ručno unete knjige (izvor == "manual")
        for b in data["books"]:
            if b.get("izvor") == "manual":
                if not any(m["id"] == b["id"] for m in merged):
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
        books = [b for b in books if b.get("oblast") == oblast]
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
        "oblast": body.get("oblast", "Ostalo").strip(),
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
    # areas: lista ID-ova ili null za sve
    area_ids = body.get("areas")  # npr. [169, 165] ili null

    t = threading.Thread(target=run_scrape, args=(area_ids,), daemon=True)
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
    return jsonify([{"id": k, "name": v} for k, v in ALL_AREAS.items()])


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

    return jsonify({
        "ukupno": len(books),
        "statusi": statuses,
        "oblasti": oblasti,
        "na_akciji": sum(1 for b in books if b.get("akcija")),
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
