"""
scraper.py — Kombib.rs scraper
Scrape-uje SVE oblasti i SVE strane.
Preskače knjige sa oznakom "Predlog za prevod".
"""

import requests
from bs4 import BeautifulSoup
import re
import time
import logging

logger = logging.getLogger(__name__)

BASE_URL = "https://kombib.rs"
BOOKS_BASE = "https://knjige.kombib.rs"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "sr,en;q=0.9",
}

# Sve oblasti sa sajta (ID → naziv)
ALL_AREAS = {
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


def clean(text):
    return re.sub(r'\s+', ' ', text or "").strip()


def parse_price(text):
    m = re.findall(r'(\d[\d.]*)\s*rsd', text, re.IGNORECASE)
    results = []
    for p in m:
        try:
            results.append(int(p.replace(".", "").replace(",", "")))
        except:
            pass
    return results


def scrape_page(area_id, page_num, area_name=""):
    """Scrape jedne strane jedne oblasti. Vraća (lista knjiga, ukupno strana)."""
    url = f"{BOOKS_BASE}/oblasti-knjiga-{area_id}-{page_num}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.encoding = "utf-8"
    except Exception as e:
        logger.error(f"Greška pri dohvatanju {url}: {e}")
        return [], 1

    soup = BeautifulSoup(resp.text, "html.parser")
    books = []

    # Pronađi ukupan broj strana iz paginacije
    total_pages = page_num  # bar toliko
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        m = re.search(rf'oblasti-knjiga-{area_id}-(\d+)', href)
        if m:
            total_pages = max(total_pages, int(m.group(1)))

    # Pronađi sve "Ceo tekst" linkove — svaki je jedna knjiga
    ceo_tekst_links = soup.find_all("a", string="Ceo tekst")

    for link in ceo_tekst_links:
        book_url = link.get("href", "")
        if not book_url:
            continue
        if not book_url.startswith("http"):
            book_url = BOOKS_BASE + "/" + book_url.lstrip("/")

        # Nađi kontejner koji sadrži sve podatke knjige
        container = link
        found = False
        for _ in range(25):
            container = container.parent
            if container is None:
                break
            h2s = container.find_all("h2")
            if len(h2s) >= 1:
                found = True
                break

        if not found or container is None:
            continue

        container_text = container.get_text(separator=" ")

        # Preskoči "Predlog za prevod"
        if "Predlog za prevod" in container_text:
            continue

        h2s = container.find_all("h2")
        naslov = clean(h2s[0].get_text()) if h2s else ""
        autor = clean(h2s[1].get_text()).replace("*", "").strip() if len(h2s) > 1 else ""

        if not naslov:
            continue

        # Slika
        img = container.find("img")
        slika_url = ""
        if img:
            src = img.get("src", "")
            if src.startswith("http"):
                slika_url = src
            elif src:
                slika_url = BASE_URL + src

        # Godina i strane
        godina_m = re.search(r'Godina izdanja:\s*(\d{4})', container_text)
        strane_m = re.search(r'Strana:\s*(\d+)', container_text)
        godina = int(godina_m.group(1)) if godina_m else None
        strane = int(strane_m.group(1)) if strane_m else None

        # Cene
        cene = parse_price(container_text)
        cena_originalna = cene[0] if cene else None
        cena_snizena = cene[-1] if len(cene) >= 2 else None
        if cena_snizena == cena_originalna:
            cena_snizena = None
        akcija = "Akcija" in container_text

        # Opis
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

        # ISBN (ako postoji)
        isbn_m = re.search(r'ISBN[:\s]*([0-9\-X]{10,17})', container_text, re.IGNORECASE)
        isbn = isbn_m.group(1) if isbn_m else ""

        book = {
            "naslov": naslov,
            "autor": autor,
            "oblast": area_name or ALL_AREAS.get(area_id, str(area_id)),
            "oblast_id": area_id,
            "godina": godina,
            "strane": strane,
            "cena_originalna": cena_originalna,
            "cena_snizena": cena_snizena,
            "akcija": akcija,
            "url": book_url,
            "slika": slika_url,
            "isbn": isbn,
            "opis": opis,
            "izvor": "scraper",
        }
        books.append(book)

    return books, total_pages


def scrape_area(area_id, area_name="", progress_callback=None):
    """Scrape-uje celu oblast (sve strane)."""
    area_name = area_name or ALL_AREAS.get(area_id, str(area_id))
    all_books = []

    # Prva strana
    books, total_pages = scrape_page(area_id, 1, area_name)
    all_books.extend(books)
    if progress_callback:
        progress_callback(area_name, 1, total_pages, len(books))

    for page in range(2, total_pages + 1):
        time.sleep(0.8)  # Pauza između zahteva — kulturno scraping
        books, _ = scrape_page(area_id, page, area_name)
        all_books.extend(books)
        if progress_callback:
            progress_callback(area_name, page, total_pages, len(books))

    return all_books


def scrape_all_areas(area_ids=None, progress_callback=None):
    """
    Scrape-uje sve (ili zadane) oblasti.
    progress_callback(oblast, strana, ukupno_strana, nove_knjige)
    Vraća listu svih knjiga.
    """
    if area_ids is None:
        area_ids = list(ALL_AREAS.keys())

    all_books = []
    for i, area_id in enumerate(area_ids):
        area_name = ALL_AREAS.get(area_id, str(area_id))
        logger.info(f"Oblast [{i+1}/{len(area_ids)}]: {area_name}")
        books = scrape_area(area_id, area_name, progress_callback)
        all_books.extend(books)
        time.sleep(1.0)  # Pauza između oblasti

    return all_books
