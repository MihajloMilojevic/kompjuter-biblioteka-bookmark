"""
scraper.py — Kombib.rs scraper
Scrape-uje oblasti, akcije, oštećene knjige, novo i najtraženije.
Preskača knjige sa oznakom "Predlog za prevod".
Podržava automatsko otkrivanje novih oblasti sa sajta.
"""

import requests
from bs4 import BeautifulSoup
import re
import time
import logging

logger = logging.getLogger(__name__)

BASE_URL   = "https://kombib.rs"
BOOKS_BASE = "https://knjige.kombib.rs"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "sr,en;q=0.9",
}

# Poznate oblasti (fallback ako auto-discovery ne radi)
KNOWN_AREAS = {
    169: "Mašinsko učenje",
    15:  "C, C++ i C#",
    190: "Algoritmi",
    182: "Generativna veštačka inteligencija",
    178: "Veštačka inteligencija",
    181: "ChatGPT",
    184: "Blockchain",
    183: "GPT",
    170: "Računarstvo u oblaku",
    27:  "Web design",
    18:  "JavaScript",
    37:  "Apple - MAC OS X",
    187: "Analiza podataka",
    186: "Funkcionalno programiranje",
    185: "Git i GitHub",
    189: "Projektovanje softvera",
    188: "Razvoj",
    16:  "Visual Basic .NET, VBA, V. Studio",
    126: "Android",
    155: "PHP i MySQL",
    176: "Full Stack Development",
    165: "Python programiranje",
    13:  "SQL",
    177: "Java",
    102: "Marketing",
    133: "WordPress",
    22:  "AutoCad, ArchiCAD, SolidWorks",
    179: "Serija Roberta C. Martina",
    14:  "Access",
    28:  "Animacija",
    26:  "Audio, Multimedia, Video",
    2:   "Baze podataka",
    135: "CSS",
    17:  "Delphi",
    31:  "Digitalna fotografija",
    171: "Django",
    168: "E-komerc",
    36:  "ECDL",
    138: "Google",
    21:  "Grafika, Dizajn, Štampa",
    9:   "Hardver",
    6:   "Internet",
    139: "Joomla",
    136: "jQuery",
    11:  "Mreže",
    23:  "MS Office",
    20:  "Obrada teksta",
    130: "Office 2013",
    180: "Poslovanje",
    32:  "Programiranje",
    161: "Raspberry PI",
    24:  "Rečnici",
    172: "Robotika",
    174: "Ruby i Ruby on Rails",
    25:  "Sertifikati",
    146: "Statistika",
    19:  "Tabele",
    148: "Telekomunikacije",
    10:  "Unix, Linux",
    8:   "Windows",
    43:  "Windows 7",
    131: "Windows 8",
    29:  "Zaštita i sigurnost",
}

# Specijalne kolekcije: slug -> (naziv, URL šablon, tip paginacije)
# tip "numeric"  = slug-N  (npr. akcija-1, akcija-2...)
# tip "static"   = fiksan URL, nema paginacije
SPECIAL_COLLECTIONS = {
    "akcija":        ("Akcija",         f"{BOOKS_BASE}/akcija-{{page}}",          "numeric"),
    "malo-ostecene": ("Malo oštećene",  f"{BOOKS_BASE}/malo-ostecene-{{page}}",   "numeric"),
    "novo":          ("Novo",           f"{BOOKS_BASE}/20_najnovijih_knjiga.html", "static"),
    "najtrazenije":  ("Najtraženije",   f"{BOOKS_BASE}/najtrazenije_knjige.html", "static"),
}

_discovered_areas = None  # memorijski keš (reset pri svakom pokretanju servera)


def clean(text):
    return re.sub(r'\s+', ' ', text or "").strip()


def parse_price(text):
    m = re.findall(r'(\d[\d.]*)\s*rsd', text, re.IGNORECASE)
    results = []
    for p in m:
        try:
            results.append(int(p.replace(".", "").replace(",", "")))
        except Exception:
            pass
    return results


def discover_areas(force=False):
    """
    Čita sidebar sa sajta i vraća {id: naziv} za SVE oblasti.
    KNOWN_AREAS je samo fallback ako sajt nije dostupan.
    Keš se čuva dok je server pokrenut; force=True prisiljava refresh.
    """
    global _discovered_areas
    if _discovered_areas is not None and not force:
        return _discovered_areas

    discovered = {}
    try:
        resp = requests.get(f"{BOOKS_BASE}/akcija-1", headers=HEADERS, timeout=15)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        for a in soup.find_all("a", href=re.compile(r'oblasti-knjiga-(\d+)-')):
            m = re.search(r'oblasti-knjiga-(\d+)-', a.get("href", ""))
            if m:
                area_id   = int(m.group(1))
                area_name = clean(a.get_text())
                if area_name:
                    discovered[area_id] = area_name

        if discovered:
            logger.info(f"Auto-discovery: pronađeno {len(discovered)} oblasti sa sajta.")
            # Dodaj iz KNOWN_AREAS ako neka oblast nije u sidebaru (npr. skrivene)
            for k, v in KNOWN_AREAS.items():
                if k not in discovered:
                    discovered[k] = v
        else:
            logger.warning("Auto-discovery vratio 0 oblasti — koristim KNOWN_AREAS kao fallback.")
            discovered = dict(KNOWN_AREAS)

    except Exception as e:
        logger.warning(f"Auto-discovery neuspešan ({e}), koristim KNOWN_AREAS.")
        discovered = dict(KNOWN_AREAS)

    _discovered_areas = discovered
    return discovered


def get_all_areas():
    """Javni API: vrati dict svih oblasti (ID -> naziv)."""
    return discover_areas()


def _extract_books_from_soup(soup, area_name, source_tag="scraper", area_id=None):
    """Zajednička logika: izvlači sve knjige iz jedne učitane stranice."""
    books = []

    for link in soup.find_all("a", string="Ceo tekst"):
        book_url = link.get("href", "")
        if not book_url:
            continue
        if not book_url.startswith("http"):
            book_url = BOOKS_BASE + "/" + book_url.lstrip("/")

        container = link
        found = False
        for _ in range(25):
            container = container.parent
            if container is None:
                break
            if container.find_all("h2"):
                found = True
                break
        if not found or container is None:
            continue

        container_text = container.get_text(separator=" ")
        if "Predlog za prevod" in container_text:
            continue

        h2s   = container.find_all("h2")
        naslov = clean(h2s[0].get_text()) if h2s else ""
        autor  = clean(h2s[1].get_text()).replace("*", "").strip() if len(h2s) > 1 else ""
        if not naslov:
            continue

        img = container.find("img")
        slika_url = ""
        if img:
            src = img.get("src", "")
            slika_url = src if src.startswith("http") else (BASE_URL + src if src else "")

        godina_m = re.search(r'Godina izdanja:\s*(\d{4})', container_text)
        strane_m = re.search(r'Strana:\s*(\d+)', container_text)
        isbn_m   = re.search(r'ISBN[:\s]*([0-9\-X]{10,17})', container_text, re.IGNORECASE)

        cene = parse_price(container_text)
        cena_originalna = cene[0] if cene else None
        cena_snizena    = cene[-1] if len(cene) >= 2 else None
        if cena_snizena == cena_originalna:
            cena_snizena = None

        opis = ""
        for t in container.stripped_strings:
            t = t.strip()
            if (len(t) > 60
                    and "rsd" not in t.lower()
                    and "Godina" not in t
                    and "Strana" not in t
                    and "Predlog" not in t
                    and "Naruči" not in t
                    and "Ceo tekst" not in t):
                opis = t[:400]
                break

        books.append({
            "naslov":          naslov,
            "autor":           autor,
            "oblasti":         [area_name] if area_name else [],
            "oblast_ids":      [area_id] if area_id else [],
            # oblast (singular) kept for backwards compat with existing books.json
            "oblast":          area_name,
            "oblast_id":       area_id,
            "godina":          int(godina_m.group(1)) if godina_m else None,
            "strane":          int(strane_m.group(1)) if strane_m else None,
            "cena_originalna": cena_originalna,
            "cena_snizena":    cena_snizena,
            "akcija":          "Akcija" in container_text,
            "url":             book_url,
            "slika":           slika_url,
            "isbn":            isbn_m.group(1) if isbn_m else "",
            "opis":            opis,
            "izvor":           source_tag,
        })

    return books


def _count_pages(soup, pattern_re, current_page=1):
    """Detektuje ukupan broj strana iz paginacionih linkova."""
    total = current_page
    for a in soup.find_all("a", href=True):
        m = re.search(pattern_re, a.get("href", ""))
        if m:
            total = max(total, int(m.group(1)))
    return total


# ── Oblast ──────────────────────────────────────────────────────────────────

def scrape_page(area_id, page_num, area_name=""):
    """Scrape jedne strane jedne oblasti. Vraća (knjige, ukupno_strana)."""
    all_areas = get_all_areas()
    area_name = area_name or all_areas.get(area_id, str(area_id))
    url = f"{BOOKS_BASE}/oblasti-knjiga-{area_id}-{page_num}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.encoding = "utf-8"
    except Exception as e:
        logger.error(f"Greška {url}: {e}")
        return [], 1

    soup        = BeautifulSoup(resp.text, "html.parser")
    books       = _extract_books_from_soup(soup, area_name, "scraper", area_id)
    total_pages = _count_pages(soup, rf'oblasti-knjiga-{area_id}-(\d+)', page_num)
    return books, total_pages


def scrape_area(area_id, area_name="", progress_callback=None):
    """Scrape-uje celu oblast (sve strane)."""
    all_areas = get_all_areas()
    area_name = area_name or all_areas.get(area_id, str(area_id))
    all_books = []

    books, total_pages = scrape_page(area_id, 1, area_name)
    all_books.extend(books)
    if progress_callback:
        progress_callback(area_name, 1, total_pages, len(books))

    for page in range(2, total_pages + 1):
        time.sleep(0.8)
        books, _ = scrape_page(area_id, page, area_name)
        all_books.extend(books)
        if progress_callback:
            progress_callback(area_name, page, total_pages, len(books))

    return all_books


# ── Specijalne kolekcije ─────────────────────────────────────────────────────

def scrape_special_page(slug, page_num=1):
    """Scrape jedne strane specijalne kolekcije. Vraća (knjige, ukupno_strana)."""
    if slug not in SPECIAL_COLLECTIONS:
        raise ValueError(f"Nepoznat slug: {slug!r}. Dostupni: {list(SPECIAL_COLLECTIONS)}")

    area_name, url_template, pag_type = SPECIAL_COLLECTIONS[slug]
    url = url_template if pag_type == "static" else url_template.format(page=page_num)

    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.encoding = "utf-8"
    except Exception as e:
        logger.error(f"Greška {url}: {e}")
        return [], 1

    soup  = BeautifulSoup(resp.text, "html.parser")
    books = _extract_books_from_soup(soup, area_name, f"special:{slug}")

    if pag_type == "static":
        total_pages = 1
    else:
        pat = slug.replace("-", r"\-") + r"-(\d+)"
        total_pages = _count_pages(soup, pat, page_num)

    return books, total_pages


def scrape_special(slug, progress_callback=None):
    """Scrape-uje celu specijalnu kolekciju."""
    area_name, _, pag_type = SPECIAL_COLLECTIONS[slug]
    all_books = []

    books, total_pages = scrape_special_page(slug, 1)
    all_books.extend(books)
    if progress_callback:
        progress_callback(area_name, 1, total_pages, len(books))

    if pag_type != "static":
        for page in range(2, total_pages + 1):
            time.sleep(0.8)
            books, _ = scrape_special_page(slug, page)
            all_books.extend(books)
            if progress_callback:
                progress_callback(area_name, page, total_pages, len(books))

    return all_books


# ── Sve odjednom ─────────────────────────────────────────────────────────────

def scrape_all_areas(area_ids=None, include_special=None, progress_callback=None):
    """
    Scrape-uje oblasti i/ili specijalne kolekcije.
    Deduplikuje po URL-u i akumulira `oblasti` listu za svaku knjigu.

    area_ids:        lista ID-ova oblasti, ili None za sve
    include_special: lista slugova, npr. ["akcija","malo-ostecene","novo","najtrazenije"]
                     None  → preskoči specijalne
                     []    → uključi sve specijalne
    """
    all_areas = get_all_areas()
    if area_ids is None:
        area_ids = list(all_areas.keys())

    # Koristimo OrderedDict po URL-u da deduplikujemo i akumuliramo oblasti
    by_url = {}

    def add_books(books):
        for b in books:
            url = b["url"]
            if url not in by_url:
                by_url[url] = b
            else:
                # Knjiga već postoji — samo dodaj novu oblast ako je nema
                existing = by_url[url]
                for oblast in b.get("oblasti", []):
                    if oblast and oblast not in existing.setdefault("oblasti", []):
                        existing["oblasti"].append(oblast)
                for oid in b.get("oblast_ids", []):
                    if oid and oid not in existing.setdefault("oblast_ids", []):
                        existing["oblast_ids"].append(oid)
                # Ažuriraj primarnu oblast samo ako prethodno nije bila postavljena
                if not existing.get("oblast") and b.get("oblast"):
                    existing["oblast"] = b["oblast"]

    for i, area_id in enumerate(area_ids):
        area_name = all_areas.get(area_id, str(area_id))
        logger.info(f"Oblast [{i+1}/{len(area_ids)}]: {area_name}")
        add_books(scrape_area(area_id, area_name, progress_callback))
        time.sleep(1.0)

    if include_special is not None:
        slugs = list(SPECIAL_COLLECTIONS.keys()) if include_special == [] else include_special
        for slug in slugs:
            if slug not in SPECIAL_COLLECTIONS:
                continue
            logger.info(f"Specijalna kolekcija: {slug}")
            add_books(scrape_special(slug, progress_callback))
            time.sleep(1.0)

    return list(by_url.values())
