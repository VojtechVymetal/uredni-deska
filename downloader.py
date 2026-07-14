"""
Modul pro stahování příloh, výpočet hashů a upload do Supabase Storage.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Optional

import aiohttp

import config
import database as db

logger = logging.getLogger(__name__)

SUPABASE_BUCKET = "attachments"

def compute_file_hash(file_path: str | Path) -> str:
    """Vypočítá SHA-256 hash souboru."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def _sanitize_filename(name: str) -> str:
    """Odstraní nebezpečné znaky z názvu souboru."""
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = name.strip('. ')
    return name or "unnamed"


def _get_storage_path(doc_id: str, file_name: str, version: int) -> str:
    """Vytvoří cestu k verzovanému souboru uvnitř Supabase Storage."""
    stem = Path(file_name).stem
    suffix = Path(file_name).suffix
    safe_stem = _sanitize_filename(stem)
    return f"{doc_id}/{safe_stem}_v{version}{suffix}"


async def download_file(url: str, doc_id: str, file_name: str,
                         version: int = 1) -> Optional[str]:
    """
    Stáhne soubor dočasně na disk a následně ho nahraje do Supabase Storage.
    Vrací cestu k uloženému souboru ve Storage (nebo None při chybě).
    """
    storage_path = _get_storage_path(doc_id, file_name, version)
    
    # Použití /tmp pro Vercel Serverless (nebo běžný tmp)
    temp_dir = Path(tempfile.gettempdir()) / "uredni-deska-downloads"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_file_path = temp_dir / _sanitize_filename(file_name)

    try:
        timeout = aiohttp.ClientTimeout(total=60)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            }
            async with session.get(url, headers=headers, ssl=False) as response:
                if response.status != 200:
                    logger.error("Stahování selhalo (%d): %s", response.status, url)
                    return None

                with open(temp_file_path, "wb") as f:
                    async for chunk in response.content.iter_chunked(8192):
                        f.write(chunk)

        file_size = temp_file_path.stat().st_size
        logger.info("Stažen soubor do tmp: %s (%d B)", file_name, file_size)

        # Upload do Supabase
        client = db.get_client()
        with open(temp_file_path, "rb") as f:
            res = client.storage.from_(SUPABASE_BUCKET).upload(
                path=storage_path,
                file=f,
                file_options={"content-type": response.headers.get("content-type", "application/octet-stream")}
            )
            
        logger.info("Soubor nahrán do Supabase: %s", storage_path)
        return storage_path

    except Exception as e:
        logger.error("Chyba při stahování/uploadu %s: %s", url, e)
        return None
    finally:
        # Úklid dočasného souboru
        if temp_file_path.exists():
            try:
                temp_file_path.unlink()
            except Exception as cleanup_err:
                logger.warning("Nepodařilo se smazat temp soubor %s: %s", temp_file_path, cleanup_err)

