"""
Supabase (PostgreSQL) databázový modul – CRUD operace.
"""

import hashlib
import json
import logging
from datetime import datetime
from typing import Optional

from supabase import create_client, Client
import config

logger = logging.getLogger(__name__)


def get_client() -> Client:
    """Vrací instanci Supabase klienta."""
    return create_client(config.SUPABASE_URL, config.SUPABASE_KEY)


# Note: init_db is no longer needed via script, as it will be run manually via SQL editor,
# but we keep a dummy function so main.py doesn't crash if we haven't deleted it yet.
def init_db() -> None:
    pass


def compute_metadata_hash(metadata: dict) -> str:
    normalized = json.dumps(metadata, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now().isoformat()


def get_document(client: Client, doc_id: str) -> Optional[dict]:
    res = client.table("documents").select("*").eq("doc_id", doc_id).execute()
    return res.data[0] if res.data else None


def get_all_active_doc_ids(client: Client) -> set:
    res = client.table("documents").select("doc_id").eq("is_active", True).execute()
    return {row["doc_id"] for row in res.data}


def insert_document(client: Client, doc_data: dict):
    client.table("documents").insert({
        "doc_id": doc_data["doc_id"],
        "kategorie": doc_data.get("kategorie"),
        "nazev": doc_data.get("nazev"),
        "cj_zn": doc_data.get("cj_zn"),
        "vyveseni_dne": doc_data.get("vyveseni_dne"),
        "sejmuti_dne": doc_data.get("sejmuti_dne"),
        "popis": doc_data.get("popis"),
        "poznamka": doc_data.get("poznamka"),
        "zdroj": doc_data.get("zdroj"),
        "is_active": True
    }).execute()


def update_document_last_seen(client: Client, doc_id: str):
    client.table("documents").update({
        "last_seen_at": _now(),
        "is_active": True,
        "removed_at": None
    }).eq("doc_id", doc_id).execute()


def update_document_metadata(client: Client, doc_id: str, doc_data: dict):
    client.table("documents").update({
        "kategorie": doc_data.get("kategorie"),
        "nazev": doc_data.get("nazev"),
        "cj_zn": doc_data.get("cj_zn"),
        "vyveseni_dne": doc_data.get("vyveseni_dne"),
        "sejmuti_dne": doc_data.get("sejmuti_dne"),
        "popis": doc_data.get("popis"),
        "poznamka": doc_data.get("poznamka"),
        "zdroj": doc_data.get("zdroj"),
        "last_seen_at": _now()
    }).eq("doc_id", doc_id).execute()


def mark_document_removed(client: Client, doc_id: str):
    client.table("documents").update({
        "is_active": False,
        "removed_at": _now()
    }).eq("doc_id", doc_id).execute()


def get_latest_document_version(client: Client, doc_id: str) -> Optional[dict]:
    res = client.table("document_versions").select("*").eq("doc_id", doc_id).order("version", desc=True).limit(1).execute()
    return res.data[0] if res.data else None


def insert_document_version(client: Client, doc_id: str, doc_data: dict, metadata_hash: str, version: int):
    client.table("document_versions").insert({
        "doc_id": doc_id,
        "version": version,
        "kategorie": doc_data.get("kategorie"),
        "nazev": doc_data.get("nazev"),
        "cj_zn": doc_data.get("cj_zn"),
        "vyveseni_dne": doc_data.get("vyveseni_dne"),
        "sejmuti_dne": doc_data.get("sejmuti_dne"),
        "popis": doc_data.get("popis"),
        "poznamka": doc_data.get("poznamka"),
        "zdroj": doc_data.get("zdroj"),
        "metadata_hash": metadata_hash
    }).execute()


def get_attachment(client: Client, doc_id: str, file_name: str) -> Optional[dict]:
    res = client.table("attachments").select("*").eq("doc_id", doc_id).eq("file_name", file_name).execute()
    return res.data[0] if res.data else None


def get_attachments_for_doc(client: Client, doc_id: str) -> list:
    res = client.table("attachments").select("*").eq("doc_id", doc_id).execute()
    return res.data


def insert_attachment(client: Client, att_data: dict) -> int:
    res = client.table("attachments").insert({
        "doc_id": att_data["doc_id"],
        "file_id": att_data.get("file_id"),
        "file_name": att_data["file_name"],
        "file_size": att_data.get("file_size"),
        "file_description": att_data.get("file_description"),
        "download_url": att_data.get("download_url"),
        "current_version": 1
    }).execute()
    return res.data[0]["id"]


def update_attachment_version(client: Client, attachment_id: int, version: int):
    client.table("attachments").update({"current_version": version}).eq("id", attachment_id).execute()


def get_latest_attachment_version(client: Client, attachment_id: int) -> Optional[dict]:
    res = client.table("attachment_versions").select("*").eq("attachment_id", attachment_id).order("version", desc=True).limit(1).execute()
    return res.data[0] if res.data else None


def insert_attachment_version(client: Client, attachment_id: int, version: int, file_hash: str, local_path: str):
    client.table("attachment_versions").insert({
        "attachment_id": attachment_id,
        "version": version,
        "file_hash": file_hash,
        "local_path": local_path
    }).execute()


def log_event(client: Client, run_id: str, event_type: str, doc_id: str=None, message: str=None):
    client.table("scrape_log").insert({
        "run_id": run_id,
        "event_type": event_type,
        "doc_id": doc_id,
        "message": message
    }).execute()


def get_document_history(client: Client, doc_id: str) -> dict:
    doc = get_document(client, doc_id)
    if not doc:
        return {}
    
    versions = client.table("document_versions").select("*").eq("doc_id", doc_id).order("version").execute().data
    attachments = client.table("attachments").select("*").eq("doc_id", doc_id).execute().data
    
    for att in attachments:
        av = client.table("attachment_versions").select("*").eq("attachment_id", att["id"]).order("version").execute().data
        att["versions"] = av
        
    events = client.table("scrape_log").select("*").eq("doc_id", doc_id).order("created_at").execute().data
    
    return {
        "document": doc,
        "metadata_versions": versions,
        "attachments": attachments,
        "events": events,
    }


def get_statistics(client: Client) -> dict:
    total = client.table("documents").select("id", count="exact").execute().count
    active = client.table("documents").select("id", count="exact").eq("is_active", True).execute().count
    removed = client.table("documents").select("id", count="exact").eq("is_active", False).execute().count
    
    total_att = client.table("attachments").select("id", count="exact").execute().count
    total_att_v = client.table("attachment_versions").select("id", count="exact").execute().count
    total_doc_v = client.table("document_versions").select("id", count="exact").execute().count
    total_ev = client.table("scrape_log").select("id", count="exact").execute().count
    
    last_run_res = client.table("scrape_log").select("run_id, created_at").order("created_at", desc=True).limit(1).execute()
    last_run = last_run_res.data[0] if last_run_res.data else None
    
    # We can't group by nicely in simple supabase queries without RPC, so we fetch and group in python
    # or use a rpc call. For simplicity, we fetch all active categories
    docs_cats = client.table("documents").select("kategorie").execute().data
    cat_counts = {}
    for dc in docs_cats:
        k = dc["kategorie"]
        cat_counts[k] = cat_counts.get(k, 0) + 1
    categories = [{"kategorie": k, "c": v} for k, v in sorted(cat_counts.items(), key=lambda item: item[1], reverse=True)]

    sev_attention = client.table("document_analyses").select("id", count="exact").eq("severity", "Vyžaduje pozornost").execute().count
    sev_serious = client.table("document_analyses").select("id", count="exact").eq("severity", "Závažné").execute().count
    
    return {
        "total_documents": total, "active_documents": active, "removed_documents": removed,
        "total_attachments": total_att, "total_attachment_versions": total_att_v,
        "total_metadata_versions": total_doc_v, "total_events": total_ev,
        "severity_attention": sev_attention, "severity_serious": sev_serious,
        "last_run": {"last_run": last_run["created_at"], "run_id": last_run["run_id"]} if last_run else None,
        "categories": categories,
    }


def get_analysis(client: Client, doc_id: str) -> Optional[dict]:
    res = client.table("document_analyses").select("*").eq("doc_id", doc_id).execute()
    return res.data[0] if res.data else None


def upsert_analysis(client: Client, data: dict):
    client.table("document_analyses").upsert({
        "doc_id": data["doc_id"],
        "severity": data["severity"],
        "summary": data.get("summary"),
        "is_analyzed_by_ai": data.get("is_analyzed_by_ai", False),
        "prompt_tokens": data.get("prompt_tokens", 0),
        "completion_tokens": data.get("completion_tokens", 0),
        "cost_czk": data.get("cost_czk", 0.0),
        "model": data.get("model")
    }, on_conflict="doc_id").execute()
