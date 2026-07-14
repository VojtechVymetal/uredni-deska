"""
httpx + BeautifulSoup scraper pro úřední desku.
Neužívá Playwright z důvodu kompatibility s Vercel Serverless.
"""

import asyncio
import logging
import random
import re
from dataclasses import dataclass, field
from typing import Optional

import httpx
from bs4 import BeautifulSoup

import config

logger = logging.getLogger(__name__)


@dataclass
class AttachmentData:
    file_name: str
    file_size: Optional[str] = None
    file_description: Optional[str] = None
    download_url: Optional[str] = None
    file_id: Optional[str] = None


@dataclass
class DocumentData:
    doc_id: str
    kategorie: Optional[str] = None
    nazev: Optional[str] = None
    cj_zn: Optional[str] = None
    vyveseni_dne: Optional[str] = None
    sejmuti_dne: Optional[str] = None
    popis: Optional[str] = None
    poznamka: Optional[str] = None
    zdroj: Optional[str] = None
    attachments: list = field(default_factory=list)

    def to_metadata_dict(self) -> dict:
        return {
            "kategorie": self.kategorie,
            "nazev": self.nazev,
            "cj_zn": self.cj_zn,
            "vyveseni_dne": self.vyveseni_dne,
            "sejmuti_dne": self.sejmuti_dne,
            "popis": self.popis,
            "poznamka": self.poznamka,
            "zdroj": self.zdroj,
        }


async def _random_delay():
    delay = random.uniform(config.MIN_DELAY_BETWEEN_REQUESTS, config.MAX_DELAY_BETWEEN_REQUESTS)
    await asyncio.sleep(delay)


async def _retry_async(coro_func, *args, max_retries=None, **kwargs):
    retries = max_retries or config.MAX_RETRIES
    last_error = None
    for attempt in range(retries):
        try:
            return await coro_func(*args, **kwargs)
        except Exception as e:
            last_error = e
            wait_time = config.RETRY_DELAY_BASE ** (attempt + 1)
            logger.warning("Pokus %d/%d selhal: %s. Čekám %ds...", attempt + 1, retries, str(e)[:200], wait_time)
            await asyncio.sleep(wait_time)
    raise last_error


def _extract_doc_ids(html_content: str) -> list[str]:
    soup = BeautifulSoup(html_content, 'html.parser')
    links = soup.find_all("a", href=re.compile(r"javascript:D\("))
    doc_ids = []
    
    for link in links:
        href = link.get("href")
        match = re.search(r"D\('([^']+)'", href)
        if match:
            doc_id = match.group(1)
            if doc_id not in doc_ids:
                doc_ids.append(doc_id)
                
    logger.info("Nalezeno %d dokumentů na stránce", len(doc_ids))
    return doc_ids


def _parse_detail_page(html_content: str, doc_id: str) -> DocumentData:
    doc = DocumentData(doc_id=doc_id)
    soup = BeautifulSoup(html_content, 'html.parser')
    
    rows = soup.find_all("tr")
    for row in rows:
        cells = row.find_all("td")
        if len(cells) >= 2:
            label_el = cells[0]
            value_el = cells[1]
            
            label = label_el.get_text(strip=True).lower()
            value = value_el.get_text(strip=True)
            
            if "kategorie" in label:
                doc.kategorie = value
            elif "název" in label or "nazev" in label:
                doc.nazev = value
            elif "čj" in label or "č.j" in label or "cj" in label:
                doc.cj_zn = value
            elif "vyvěšení" in label or "vyveseni" in label:
                doc.vyveseni_dne = value
            elif "sejmutí" in label or "sejmuti" in label:
                doc.sejmuti_dne = value
            elif "popis" in label:
                doc.popis = value
            elif "poznámka" in label or "poznamka" in label:
                doc.poznamka = value
            elif "zdroj" in label:
                doc.zdroj = value
            elif "dokument" in label:
                doc.attachments = _parse_attachments(value_el, doc_id)

    return doc


def _parse_attachments(cell_element, doc_id: str) -> list[AttachmentData]:
    attachments = []
    links = cell_element.find_all("a", href=True)
    full_text = cell_element.get_text(strip=True)

    for link in links:
        href = link.get("href", "")
        link_text = link.get_text(strip=True)
        if not link_text:
            continue

        att = AttachmentData(file_name=link_text)

        if "Dokument.aspx" in href or href.startswith("http"):
            att.download_url = href if href.startswith("http") else config.BASE_URL + href
        elif href.startswith("/"):
            att.download_url = "https://egov.opava-city.cz" + href

        file_id_match = re.search(r"filepri=([^&]+)", href)
        if file_id_match:
            att.file_id = file_id_match.group(1)

        attachments.append(att)

    size_matches = re.findall(r'\((\d+[\s,.]?\d*\s*(?:KB|MB|GB|B))\)', full_text, re.IGNORECASE)
    for i, size in enumerate(size_matches):
        if i < len(attachments):
            attachments[i].file_size = size.strip()

    # Velmi primitivní extrakce popisu pro BS4, jelikož struktura uzlů je těžko predikovatelná
    return attachments


async def _fetch_page(client: httpx.AsyncClient, url: str) -> str:
    response = await client.get(url, timeout=30.0)
    response.raise_for_status()
    return response.text


async def scrape_all_documents() -> list[DocumentData]:
    documents = []
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    async with httpx.AsyncClient(headers=headers, verify=False) as client:
        try:
            logger.info("Načítám seznam dokumentů: %s", config.LIST_URL)
            list_html = await _retry_async(_fetch_page, client, config.LIST_URL)
            
            doc_ids = _extract_doc_ids(list_html)
            logger.info("Celkem nalezeno %d unikátních dokumentů", len(doc_ids))
            
            for i, doc_id in enumerate(doc_ids):
                try:
                    logger.info("Zpracovávám dokument %d/%d: %s", i + 1, len(doc_ids), doc_id)
                    detail_url = config.DETAIL_URL_TEMPLATE.format(doc_id=doc_id)
                    await _random_delay()
                    
                    detail_html = await _retry_async(_fetch_page, client, detail_url)
                    doc_data = _parse_detail_page(detail_html, doc_id)
                    documents.append(doc_data)
                    
                    logger.debug("Dokument %s: %s, %d příloh", doc_id, doc_data.nazev, len(doc_data.attachments))
                except Exception as e:
                    logger.error("Chyba při zpracování dokumentu %s: %s", doc_id, e)
                    continue

        except Exception as e:
            logger.error("Kritická chyba při scrapování: %s", e)
            raise

    logger.info("Scraping dokončen. Zpracováno %d dokumentů.", len(documents))
    return documents
