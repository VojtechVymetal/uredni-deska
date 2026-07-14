# 🏛️ Archivační systém úřední desky města Opavy

Automatický systém pro periodické monitorování a hloubkové verzované archivování [úřední desky statutárního města Opavy](https://egov.opava-city.cz/Uredni_deska/SeznamDokumentu.aspx).

## ✨ Funkce

- **Kompletní archivace** – stahuje metadata i přílohy (PDF, DOCX, …)
- **Verzování** – při změně metadat nebo obsahu přílohy se automaticky vytvoří nová verze
- **Detekce změn** – SHA-256 hashing pro spolehlivou detekci změn v souborech
- **Detekce odstraněných dokumentů** – automaticky označí dokumenty, které zmizí z desky
- **Časová osa** – kompletní historie: kdy byl dokument poprvé viděn, kdy změněn, kdy odstraněn
- **Robustní error handling** – retry logika, timeouty, graceful degradation
- **Logging** – podrobné záznamy o každém běhu

## 📋 Prerekvizity

- **Python 3.10+**
- Připojení k internetu

## 🚀 Instalace

```bash
# 1. Klonuj repozitář / přejdi do složky projektu
cd uredni-deska

# 2. Vytvoř virtuální prostředí (doporučeno)
python -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate  # Linux/Mac

# 3. Nainstaluj závislosti
pip install -r requirements.txt

# 4. Nainstaluj Playwright prohlížeč
playwright install chromium
```

## 📖 Použití

### Jednorázový scrape (archivační cyklus)

```bash
python main.py
# nebo explicitně:
python main.py scrape
```

### Seznam dokumentů v databázi

```bash
python main.py list                 # Aktivní dokumenty
python main.py list --all           # Včetně odstraněných
```

### Historie dokumentu

```bash
python main.py history MMOP0B546TIS         # Časová osa dokumentu
python main.py history MMOP0B546TIS --json  # Výstup jako JSON
```

### Statistiky archivu

```bash
python main.py stats
python main.py stats --json
```

### Export databáze

```bash
python main.py export -o archiv.json   # Export do souboru
python main.py export                  # Export na stdout
```

### Podrobný výstup (debug)

```bash
python main.py -v scrape
```

## 🗄️ Struktura databáze

```
documents                  Hlavní tabulka dokumentů
├── doc_id (unique)        ID dokumentu z webu
├── kategorie, nazev       Metadata
├── cj_zn, vyveseni_dne    Číslo jednací, datum vyvěšení
├── popis, poznamka, zdroj Další pole
├── first_seen_at          Kdy jsme dokument poprvé viděli
├── last_seen_at           Kdy jsme ho naposledy viděli na desce
├── removed_at             Kdy zmizel z desky (= datum sejmutí)
└── is_active              Je stále na desce?

document_versions          Verze metadat (při změně)
├── version                Číslo verze (1, 2, 3, …)
├── metadata_hash          SHA-256 hash metadat
└── [všechna metadata]     Snapshot metadat v dané verzi

attachments                Přílohy dokumentů
├── file_name              Název souboru
├── download_url           URL ke stažení
└── current_version        Aktuální číslo verze

attachment_versions        Verze příloh (při změně obsahu)
├── version                Číslo verze
├── file_hash              SHA-256 hash obsahu souboru
└── local_path             Cesta k lokálnímu souboru

scrape_log                 Auditní log
├── run_id                 ID běhu
├── event_type             NEW_DOC / UPDATED_META / UPDATED_FILE / REMOVED_DOC / ERROR
└── message                Podrobnosti
```

## 📂 Struktura souborů

```
uredni-deska/
├── config.py              Konfigurace
├── database.py            Databázový modul
├── scraper.py             Playwright scraper
├── downloader.py          Stahování + hashing
├── archiver.py            Hlavní orchestrátor
├── main.py                CLI vstupní bod
├── requirements.txt       Závislosti
├── README.md              Tato dokumentace
├── data/                  SQLite databáze
│   └── uredni_deska.db
├── archive/               Stažené přílohy
│   └── <DOC_ID>/
│       ├── soubor_v1.pdf
│       └── soubor_v2.pdf
└── logs/                  Záznamy
    └── archiver.log
```

## ⏰ Automatické spouštění

### Windows (Task Scheduler)

1. Otevřete **Plánovač úloh** (Task Scheduler)
2. **Vytvořit základní úlohu…**
3. Název: `Uredni deska archivace`
4. Trigger: **Denně**, opakovat každých **12 hodin**
5. Akce: **Spustit program**
   - Program: `C:\cesta\k\venv\Scripts\python.exe`
   - Argumenty: `main.py`
   - Spustit v: `C:\cesta\k\uredni-deska`

### Linux/Mac (Cron)

```bash
# Otevřete crontab editor
crontab -e

# Přidejte řádek (každých 12 hodin v 6:00 a 18:00):
0 6,18 * * * cd /cesta/k/uredni-deska && /cesta/k/venv/bin/python main.py >> /cesta/k/logs/cron.log 2>&1
```

## ⚙️ Konfigurace

Všechna nastavení jsou v `config.py`:

| Parametr | Výchozí | Popis |
|---|---|---|
| `HEADLESS` | `True` | Prohlížeč bez GUI |
| `MAX_RETRIES` | `3` | Počet opakování při selhání |
| `MIN_DELAY_BETWEEN_REQUESTS` | `1.0s` | Min. pauza mezi requesty |
| `MAX_DELAY_BETWEEN_REQUESTS` | `3.0s` | Max. pauza mezi requesty |
| `SCRAPE_INTERVAL_HOURS` | `12` | Interval pro automatické spouštění |

## 📝 Licence

Tento projekt je poskytován „tak, jak je" pro účely archivace veřejných informací.
