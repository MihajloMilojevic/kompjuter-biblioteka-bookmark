# 📚 Knjige Beležnica

Lokalna web aplikacija za praćenje, organizovanje i naručivanje knjiga sa [kombib.rs](https://kombib.rs) (Kompjuter biblioteka).

> **Napomena:** Ova aplikacija je u celosti generisana pomoću veštačke inteligencije — [Claude](https://claude.ai) (Anthropic). Kompletan kod (backend, scraper, frontend) nastao je kroz razgovor bez ručnog pisanja ijednog reda koda.

---

## Šta aplikacija radi

- **Automatski preuzima** katalog knjiga sa kombib.rs (63 oblasti, sve strane)
- **Prati status** svake knjige: imam / zanima me / pročitana / nije za mene
- **Beleške** po knjizi
- **Ručno dodavanje** novih knjiga koje izlaze mesečno
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
# Kloniraj repozitorijum
git clone https://github.com/tvoj-username/knjige-beleznca.git
cd knjige-beleznca

# Instaliraj zavisnosti
pip install -r requirements.txt

# Pokreni server
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

Klikni na **"+ beleška"** ispod svake knjige za lične napomene.

### Scraping (osvežavanje kataloga)

- **Brzo:** Dugme "Osveži sve knjige" u sidebaru → scraping svih 63 oblasti odjednom
- **Selektivno:** Tab "Scraping" → biraju se tačno koje oblasti, praćenje progresa i log u realnom vremenu

Knjige sa oznakom **"Predlog za prevod"** se automatski preskakaju — to su knjige koje još nisu prevedene na srpski.

Tvoji statusi i beleške se **čuvaju** i pri svakom novom scrapingu.

### Popust kod

1. Otvori tab **"🏷️ Popust kod"**
2. Unesi aktivan kod (npr. `SolaR2026`)
3. Aplikacija preuzima listu knjiga direktno sa kombib.rs
4. Svaka knjiga je ukrštena sa tvojom bazom — vidiš odmah koje imaš, koje te zanimaju
5. Označi čekboksovima šta hoćeš da naručiš
6. Klikni **"📋 Kopiraj JS"** — dobijаš JavaScript snippet

**Kako koristiti snippet:**
1. Otvori [kombib.rs/popust-kod.php](https://kombib.rs/popust-kod.php) u browseru
2. Unesi isti kod i klikni "Dalje"
3. Pritisni `F12` → tab **Console**
4. Nalepi kopirani kod → `Enter`
5. Skripta automatski selektuje tvoje knjige u listi, pa samo klikneš "Naruči"

### Ručno dodavanje knjiga

Tab **"➕ Dodaj knjigu"** — forma za unos svih podataka. Korisno za nove knjige koje izlaze između dva scrapinga. Ručno dodate knjige su označene badge-om ✏️ i nikad se ne brišu pri re-scrapingu.

### Provera akcija

Tab **"🔖 Proveri akciju"** — uneseš listu naslova ili URL-ova (svaki u novom redu), dobiješ izveštaj koji ih ukršta sa tvojim statusima.

---

## Struktura projekta

```
knjige-beleznca/
├── server.py           ← Flask server + REST API
├── scraper.py          ← Web scraper (sve oblasti, sve strane)
├── books.json          ← Baza podataka (auto-generiše se, u .gitignore)
├── requirements.txt
└── static/
    └── index.html      ← Kompletna web aplikacija (single-file)
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
| `POST` | `/api/scrape/start` | Pokreni scraping (`{"areas": [169, 165]}` ili `null` za sve) |
| `GET` | `/api/scrape/status` | Status scrapinga (za polling) |
| `POST` | `/api/popust` | Preuzmi knjige za popust kod (`{"kod": "SolaR2026"}`) |
| `GET` | `/api/stats` | Statistike biblioteke |
| `GET` | `/api/areas` | Lista svih oblasti |
| `GET` | `/api/export/csv` | Preuzmi celu bazu kao CSV |

---

## .gitignore

Preporučuje se da dodate `books.json` u `.gitignore` jer sadrži lične podatke (statusi, beleške):

```gitignore
books.json
__pycache__/
*.pyc
.env
```

---

## Odricanje odgovornosti

Ova aplikacija koristi web scraping za preuzimanje javno dostupnih podataka sa kombib.rs isključivo za ličnu upotrebu. Nemoj je koristiti za masovno preuzimanje podataka u komercijalne svrhe. Koristi razumne pauze između zahteva (već ugrađeno u scraper).

---

## O projektu

Cela aplikacija — od ideje do finalnog koda — nastala je kroz konverzaciju sa **[Claude](https://claude.ai)** (Anthropic), AI asistentom. Nije napisan ni jedan red koda ručno. Razvoj je tekao iterativno kroz chat: postavljanjem zahteva, debugovanjem grešaka i dodavanjem novih funkcionalnosti, sve unutar jednog razgovora.

Ovo je praktičan primer kako AI može biti korišćen kao kompletan razvojni partner za izgradnju funkcionalne aplikacije od nule.
