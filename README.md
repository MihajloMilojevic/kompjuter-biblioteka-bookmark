# 📚 Knjige Beležnica

Lokalna web aplikacija za praćenje, organizovanje i naručivanje knjiga sa [kombib.rs](https://kombib.rs) (Kompjuter biblioteka).

> **Napomena:** Ova aplikacija je u celosti generisana pomoću veštačke inteligencije — [Claude](https://claude.ai) (Anthropic). Kompletan kod (backend, scraper, frontend) nastao je kroz razgovor bez ručnog pisanja ijednog reda koda.

---

## Šta aplikacija radi

- **Automatski preuzima** katalog knjiga sa kombib.rs — sve oblasti (auto-discovery sa sajta), sve strane
- **Višestruke kategorije** — svaka knjiga pamti sve oblasti kojima pripada
- **Prati status** svake knjige: imam / zanima me / pročitana / nije za mene
- **Beleške** po knjizi
- **Dodavanje po URL-u** — nalepiš link sa kombib.rs i svi podaci (naslov, autor, cena, naslovnica…) se automatski preuzmu; ako knjiga već postoji, podaci se ažuriraju
- **Ručno dodavanje** novih knjiga sa punom formom
- **Popust kod** — uneseš promotivni kod i dobiješ listu knjiga na popustu, ukrštenu sa tvojom bibliotekom
- **JavaScript snippet** — automatski generiše kod koji nalepiš u browser konzolu da selektuješ željene knjige direktno na kombib.rs
- **Provera akcija** — unesi listu naslova, dobij izveštaj
- **Izvoz u CSV**

---

## Instalacija

### Zahtevi

- Python 3.8+
- pip

### Koraci

```bash
git clone https://github.com/MihajloMilojevic/kompjuter-biblioteka-bookmark.git
cd kompjuter-biblioteka-bookmark

pip install -r requirements.txt

python server.py
```

Otvori browser na **http://localhost:5000**

### Pri prvom pokretanju

Baza je prazna. Klikni **"Osveži sve knjige"** u donjem levom uglu da pokreneš scraping — trajanje zavisi od broja oblasti, obično 5–15 minuta. Progres se prati uživo u aplikaciji.

---

## Korišćenje

### Knjige i statusi

Svaka knjiga ima četiri statusa koja možeš dodeliti jednim klikom:

| Dugme | Status | Opis |
|-------|--------|------|
| ✅ | Imam | Knjiga je u tvojoj kolekciji |
| ⭐ | Zanima me | Razmatraš kupovinu |
| 📖 | Pročitana | Pročitao si je |
| ✗ | Nije za mene | Nije od interesa |

Klikni na **"+ beleška"** ispod svake knjige za lične napomene. Klik na bilo koji **badge kategorije** na kartici automatski filtrira po toj oblasti.

### Scraping (osvežavanje kataloga)

- **Brzo:** Dugme "Osveži sve knjige" u sidebaru → scraping svih oblasti odjednom
- **Selektivno:** Tab "Scraping" → biraju se tačno koje oblasti i specijalne kolekcije (akcija, malo oštećene, novo, najtraženije), praćenje progresa i log u realnom vremenu

Oblasti se **automatski otkrivaju sa sajta** pri svakom pokretanju — nove kategorije se dodaju bez ikakvih izmena koda.

Knjige sa oznakom **"Predlog za prevod"** se automatski preskakaju. Ista knjiga koja se pojavljuje u više oblasti neće biti duplirana — sve kategorije se pamte u `oblasti` listi.

Tvoji statusi i beleške se **čuvaju** pri svakom novom scrapingu.

### Dodavanje knjige po URL-u

1. Otvori tab **"➕ Dodaj knjigu"**
2. Nalepi URL knjige sa kombib.rs u polje na vrhu i klikni **"🔍 Preuzmi"**
3. Forma se automatski popuni — naslov, autor, oblasti, cena, naslovnica, ISBN, opis
4. Ako knjiga **već postoji u bazi**, forma prikaže upozorenje i dugme postaje **"💾 Ažuriraj knjigu"** — postojeći status i beleška se čuvaju
5. Dodaj status i belešku po želji, pa klikni dugme

### Ručno dodavanje knjiga

Isti tab, ispod URL sekcije nalazi se puna forma za ručni unos. Ručno dodate knjige su označene badge-om ✏️ i nikad se ne brišu pri re-scrapingu.

### Popust kod

1. Otvori tab **"🏷️ Popust kod"**
2. Unesi aktivan kod (npr. `SolaR2026`)
3. Aplikacija preuzima listu knjiga direktno sa kombib.rs
4. Svaka knjiga je ukrštena sa tvojom bazom — vidiš odmah koje imaš, koje te zanimaju
5. Označi čekboksovima šta hoćeš da naručiš
6. Klikni **"📋 Kopiraj JS"** — dobijaš JavaScript snippet

**Kako koristiti snippet:**
1. Otvori [kombib.rs/popust-kod.php](https://kombib.rs/popust-kod.php) u browseru
2. Unesi isti kod i klikni "Dalje"
3. Pritisni `F12` → tab **Console**
4. Nalepi kopirani kod → `Enter`
5. Skripta automatski selektuje tvoje knjige u listi, pa samo klikneš "Naruči"

### Provera akcija

Tab **"🔖 Proveri akciju"** — uneseš listu naslova ili URL-ova (svaki u novom redu), dobiješ izveštaj koji ih ukršta sa tvojim statusima.

---

## Struktura projekta

```
kompjuter-biblioteka-bookmark/
├── server.py           ← Flask server + REST API
├── scraper.py          ← Web scraper (auto-discovery oblasti, dedup, oblasti[])
├── dedup.py            ← Jednokratna skripta za čišćenje duplikata iz books.json
├── books.json          ← Baza podataka (auto-generiše se, u .gitignore)
├── requirements.txt
└── static/
    └── index.html      ← Kompletna web aplikacija (single-file SPA)
```

### Tehnologije

| Komponenta | Tehnologija |
|------------|-------------|
| Backend | Python / Flask |
| Scraping | requests + BeautifulSoup4 |
| Frontend | Vanilla HTML/CSS/JS (single file, bez build toolchain-a) |
| Baza podataka | JSON fajl (books.json) |
| Fontovi | Cormorant Garamond + DM Sans (Google Fonts) |

---

## API

| Metod | Ruta | Opis |
|-------|------|------|
| `GET` | `/api/books` | Lista knjiga (parametri: `q`, `status`, `oblast`) |
| `POST` | `/api/books` | Dodaj knjigu ručno |
| `PUT` | `/api/books/:id` | Izmeni status, belešku ili podatke |
| `DELETE` | `/api/books/:id` | Obriši knjigu |
| `POST` | `/api/scrape/start` | Pokreni scraping (`{"areas": [169, 165], "special": ["akcija"]}` ili `null` za sve) |
| `GET` | `/api/scrape/status` | Status scrapinga (za polling) |
| `POST` | `/api/scrape/stop` | Zaustavi scraping |
| `GET` | `/api/areas` | Lista svih oblasti (sa sajta, live) |
| `POST` | `/api/areas/refresh` | Prisili re-discovery oblasti sa sajta |
| `POST` | `/api/fetch-book` | Preuzmi podatke knjige po URL-u (`{"url": "https://knjige.kombib.rs/..."}`) |
| `POST` | `/api/popust` | Preuzmi knjige za popust kod (`{"kod": "SolaR2026"}`) |
| `GET` | `/api/stats` | Statistike biblioteke |
| `GET` | `/api/export/csv` | Preuzmi celu bazu kao CSV |

---

## Čišćenje duplikata

Ako si koristio stariju verziju aplikacije i imaš duplirane knjige u bazi, pokreni:

```bash
python dedup.py
```

Skripta pravi backup (`books.json.bak`), uklanja duplikate po URL-u i spaja oblasti liste.

---

## .gitignore

`books.json` je već u `.gitignore` — sadrži lične podatke (statusi, beleške) koji ne treba da idu u repozitorijum.

---

## Odricanje odgovornosti

Ova aplikacija koristi web scraping za preuzimanje javno dostupnih podataka sa kombib.rs isključivo za ličnu upotrebu. Nemoj je koristiti za masovno preuzimanje podataka u komercijalne svrhe. Scraper već ima ugrađene pauze između zahteva (0.8s između strana, 1s između oblasti).

---

## O projektu

Cela aplikacija — od ideje do finalnog koda — nastala je kroz konverzaciju sa **[Claude](https://claude.ai)** (Anthropic), AI asistentom. Nije napisan ni jedan red koda ručno. Razvoj je tekao iterativno kroz chat: postavljanjem zahteva, debugovanjem grešaka i dodavanjem novih funkcionalnosti.

Ovo je praktičan primer kako AI može biti korišćen kao kompletan razvojni partner za izgradnju funkcionalne aplikacije od nule.
