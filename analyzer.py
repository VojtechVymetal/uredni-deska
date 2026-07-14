"""
Modul pro AI analýzu dokumentů úřední desky (Vercel Serverless ready).
Používá lokální předfiltraci a Google Gemini 1.5 Flash pro klasifikaci.
"""

import json
import logging
import os
import tempfile
from typing import Optional

from supabase import Client
from pypdf import PdfReader
import config
import database as db

logger = logging.getLogger(__name__)

# ── Běžné fráze pro lokální filtraci (rule-based) ──────────
ROUTINE_PATTERNS = [
    "oznámení o uložení zásilky",
    "oznámení o možnosti převzít písemnost",
    "přestupkové řízení",
    "ztráty a nálezy",
    "uložení písemnosti",
    "doručení veřejnou vyhláškou",
    "veřejná vyhláška - doručení",
    "výzva k vyzvednutí",
    "nedoručená zásilka",
    "seznámení s podklady rozhodnutí",
    "předvolání k ústnímu jednání",
    "sdělení o přestupku",
    "doplnění podání",
    "výzva k doplnění",
    "přerušení řízení",
    "zahájení řízení o přestupku",
    "oznámení o zahájení správního řízení",
    "odstavka energií",
    "odstávka vody",
    "odstávka elektřiny",
    "odstávka plynu",
    "omezení dodávky",
    "plánovaná odstávka",
]

ROUTINE_CATEGORIES = [
    "uložení písemnosti",
    "odstavka energií",
    "odstávka energií",
]


def _extract_pdf_text(pdf_path: str, max_chars: int = 7000) -> Optional[str]:
    """Extrahuje text z PDF (prvních max_chars znaků)."""
    try:
        reader = PdfReader(pdf_path)
        text_parts = []
        total_len = 0
        for page in reader.pages:
            page_text = page.extract_text() or ""
            text_parts.append(page_text)
            total_len += len(page_text)
            if total_len >= max_chars:
                break
        full_text = "\n".join(text_parts)
        return full_text[:max_chars]
    except Exception as e:
        logger.warning("Nelze extrahovat text z PDF %s: %s", pdf_path, e)
        return None


def _is_routine_document(nazev: str, kategorie: str, text: str) -> bool:
    """Lokální rule-based filtr – vrátí True pokud je dokument běžný."""
    combined = f"{nazev} {kategorie} {text}".lower()
    for pattern in ROUTINE_PATTERNS:
        if pattern.lower() in combined:
            return True
    if kategorie:
        kat_lower = kategorie.lower()
        for rcat in ROUTINE_CATEGORIES:
            if rcat.lower() in kat_lower:
                return True
    return False


def _call_gemini_api(text: str, nazev: str, kategorie: str) -> dict:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=config.GEMINI_API_KEY)

    prompt = f"""Jsi analytik úřední desky. Klasifikuj tento dokument.
Název: {nazev}
Kategorie: {kategorie}
Text dokumentu (zkrácený):
{text}

Odpověz POUZE tímto JSON (bez markdown):
{{"severity": "Běžný" nebo "Vyžaduje pozornost" nebo "Závažné", "summary": "Shrnutí max 2 věty, max 30 slov."}}

Pravidla klasifikace:
- "Běžný": procesní dokumenty, doručení, oznámení, výzvy, přestupky, odstávky energií
- "Vyžaduje pozornost": územní plánování, stavební povolení, dotace, prodej majetku města, veřejné zakázky, změny vyhlášek
- "Závažné": zásadní změny pro občany, nové regulace, velké investice, rozpočet města, krizová opatření"""

    response = client.models.generate_content(
        model=config.GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            max_output_tokens=150,
            temperature=0.1,
        ),
    )

    usage = response.usage_metadata
    prompt_tokens = usage.prompt_token_count
    completion_tokens = usage.candidates_token_count

    cost_usd = (prompt_tokens * config.AI_INPUT_PRICE_PER_TOKEN +
                completion_tokens * config.AI_OUTPUT_PRICE_PER_TOKEN)
    cost_czk = round(cost_usd * config.AI_USD_TO_CZK, 6)

    try:
        result = json.loads(response.text)
    except json.JSONDecodeError:
        logger.warning("Gemini vrátil nevalidní JSON: %s", response.text)
        result = {"severity": "Běžný", "summary": "Nepodařilo se analyzovat."}

    valid_severities = ["Běžný", "Vyžaduje pozornost", "Závažné"]
    severity = result.get("severity", "Běžný")
    if severity not in valid_severities:
        severity = "Běžný"

    return {
        "severity": severity,
        "summary": result.get("summary", ""),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "cost_czk": cost_czk,
        "model": config.GEMINI_MODEL
    }


def analyze_document(client: Client, doc_id: str, force: bool = False):
    """Provede analýzu jednoho dokumentu (Vercel Serverless)."""
    # 1. Zkontroluj, zda už analýza existuje
    existing = db.get_analysis(client, doc_id)
    if existing and not force:
        logger.debug("Dokument %s již analyzován, přeskakuji.", doc_id)
        return

    # 2. Načti dokument a přílohy
    doc = db.get_document(client, doc_id)
    if not doc:
        logger.error("Dokument %s nenalezen.", doc_id)
        return

    attachments = db.get_attachments_for_doc(client, doc_id)
    
    pdf_text = ""
    # Najdi PDF a stáhni ze Supabase Storage do /tmp
    for att in attachments:
        if (att["file_name"] or "").lower().endswith(".pdf"):
            # Získej verzi (local_path je ted storage path)
            latest_v = db.get_latest_attachment_version(client, att["id"])
            if latest_v:
                storage_path = latest_v["local_path"]
                try:
                    res = client.storage.from_("attachments").download(storage_path)
                    
                    # Ulož do tmp a analyzuj
                    fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
                    with os.fdopen(fd, 'wb') as f:
                        f.write(res)
                        
                    pdf_text = _extract_pdf_text(tmp_path, config.AI_MAX_TEXT_CHARS) or ""
                    os.unlink(tmp_path)
                    break
                except Exception as e:
                    logger.warning("Chyba při stahování/analýze PDF %s ze Storage: %s", storage_path, e)

    # 3. Lokální předfiltrace (Zdarma)
    nazev = doc.get("nazev") or ""
    kategorie = doc.get("kategorie") or ""
    
    if not pdf_text:
        # Bez PDF – klasifikuj jen na základě metadat
        if _is_routine_document(nazev, kategorie, ""):
            severity = "Běžný"
            summary = "Automaticky klasifikováno lokálním filtrem (bez PDF)."
        else:
            severity = "Vyžaduje pozornost"
            summary = "Dokument bez čitelné PDF přílohy – doporučena ruční kontrola."

        db.upsert_analysis(client, {
            "doc_id": doc_id,
            "severity": severity,
            "summary": summary,
            "is_analyzed_by_ai": False,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "cost_czk": 0.0,
            "model": None
        })
        logger.info("📋 Analýza %s: %s (lokální filtr, bez PDF)", doc_id, severity)
        return

    if _is_routine_document(nazev, kategorie, pdf_text):
        logger.info("Dokument %s vyhodnocen jako BĚŽNÝ (lokální filtr).", doc_id)
        db.upsert_analysis(client, {
            "doc_id": doc_id,
            "severity": "Běžný",
            "summary": "Běžný úřední dokument.",
            "is_analyzed_by_ai": False,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "cost_czk": 0.0,
            "model": None
        })
        return

    # 4. Zavolej Gemini API
    logger.info("Dokument %s -> Odesílám do AI analýzy.", doc_id)
    try:
        ai_result = _call_gemini_api(pdf_text, nazev, kategorie)
        db.upsert_analysis(client, {
            "doc_id": doc_id,
            "severity": ai_result["severity"],
            "summary": ai_result["summary"],
            "is_analyzed_by_ai": True,
            "prompt_tokens": ai_result["prompt_tokens"],
            "completion_tokens": ai_result["completion_tokens"],
            "cost_czk": ai_result["cost_czk"],
            "model": ai_result["model"]
        })
        logger.info("Analýza %s dokončena: %s (%.4f Kč)", doc_id, ai_result["severity"], ai_result["cost_czk"])
    except Exception as e:
        logger.error("Chyba AI analýzy dokumentu %s: %s", doc_id, e)
        db.upsert_analysis(client, {
            "doc_id": doc_id,
            "severity": "Vyžaduje pozornost",
            "summary": f"Chyba AI analýzy: {str(e)[:100]}",
            "is_analyzed_by_ai": False,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "cost_czk": 0.0,
            "model": None,
        })


def analyze_all_pending(client: Client, batch_size: int = 5) -> int:
    """Najde dokumenty bez analýzy a zpracuje je. Omezeno pro Vercel."""
    docs_res = client.table("documents").select("doc_id").eq("is_active", True).execute()
    all_doc_ids = {d["doc_id"] for d in docs_res.data}
    
    analyses_res = client.table("document_analyses").select("doc_id").execute()
    analyzed_doc_ids = {a["doc_id"] for a in analyses_res.data}
    
    pending_ids = list(all_doc_ids - analyzed_doc_ids)
    
    count = 0
    for doc_id in pending_ids[:batch_size]:
        analyze_document(client, doc_id)
        count += 1
        
    return count
