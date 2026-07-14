"""
Centrální konfigurace archivačního systému úřední desky.
"""

import os
from pathlib import Path

# === Cesty ===
BASE_DIR = Path(__file__).parent.resolve()
DATA_DIR = BASE_DIR / "data"
ARCHIVE_DIR = BASE_DIR / "archive"
LOG_DIR = BASE_DIR / "logs"

# Zajistit vytvoření adresářů (Vercel je read-only, nepoužíváme je, tak je nevytváříme)
# DATA_DIR.mkdir(exist_ok=True)
# ARCHIVE_DIR.mkdir(exist_ok=True)
# LOG_DIR.mkdir(exist_ok=True)

# === Databáze (Supabase) ===
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

# === URL webu ===
BASE_URL = "https://egov.opava-city.cz/Uredni_deska/"
LIST_URL = BASE_URL + "SeznamDokumentu.aspx"
DETAIL_URL_TEMPLATE = BASE_URL + "DetailDokument.aspx?IdFile={doc_id}&Por=0"
ATTACHMENT_URL_TEMPLATE = BASE_URL + "Dokument.aspx?file={doc_id}&pc=0&filepri={file_id}"

# === Scraper nastavení ===
HEADLESS = True                    # Spouštět prohlížeč bez GUI
REQUEST_TIMEOUT_MS = 30_000        # Timeout pro načtení stránky (ms)
NAVIGATION_TIMEOUT_MS = 60_000     # Timeout pro navigaci (ms)
DOWNLOAD_TIMEOUT_MS = 60_000       # Timeout pro stahování souborů (ms)
MAX_RETRIES = 3                    # Počet opakování při selhání
RETRY_DELAY_BASE = 2               # Základ pro exponenciální backoff (sekundy)
MIN_DELAY_BETWEEN_REQUESTS = 1.0   # Minimální pauza mezi requesty (sekundy)
MAX_DELAY_BETWEEN_REQUESTS = 3.0   # Maximální pauza mezi requesty (sekundy)

# === Logging ===
LOG_FILE = LOG_DIR / "archiver.log"
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_MAX_BYTES = 10 * 1024 * 1024   # 10 MB
LOG_BACKUP_COUNT = 5               # Počet záložních logů

# === Interval scrapování ===
SCRAPE_INTERVAL_HOURS = 12

# === AI Analýza (Gemini) ===
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-3.1-flash-lite"
AI_MAX_TEXT_CHARS = 7000  # Max znaků z PDF pro analýzu
AI_INPUT_PRICE_PER_TOKEN = 0.000000075   # USD za 1 vstupní token
AI_OUTPUT_PRICE_PER_TOKEN = 0.0000003    # USD za 1 výstupní token
AI_USD_TO_CZK = 24.0                     # Kurz USD/CZK
