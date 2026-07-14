"""
Cron endpoint pro Vercel. Spouští scraper a analyzátor.
"""

import os
import sys
import uuid
import logging
import asyncio

# Fix sys.path for imports from root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, jsonify, request
import database as db
import scraper
from downloader import download_file, compute_file_hash
from analyzer import analyze_document

app = Flask(__name__)
logger = logging.getLogger(__name__)

# Basic authentication pro cron endpoint
CRON_SECRET = os.environ.get("CRON_SECRET", "dev-secret-key")

import asyncio

@app.route('/api/cron/scrape', methods=['GET', 'POST'])
def run_scrape():
    """
    Tento endpoint zavolá Vercel Cron.
    """
    auth_header = request.headers.get("Authorization")
    if auth_header != f"Bearer {CRON_SECRET}" and request.args.get("key") != CRON_SECRET:
        return jsonify({"error": "Unauthorized"}), 401
        
    run_id = str(uuid.uuid4())[:8]
    logger.info("ARCHIVAČNÍ CYKLUS ZAHÁJEN [run_id=%s]", run_id)
    
    client = db.get_client()
    stats = {"new": 0, "updated_meta": 0, "updated_file": 0, "removed": 0, "unchanged": 0, "errors": 0}
    
    try:
        existing_active_ids = db.get_all_active_doc_ids(client)
        # 1. Scrapuj aktuální dokumenty
        current_docs = asyncio.run(scraper.scrape_all_documents(known_ids=existing_active_ids, limit_new=15))
        current_doc_ids = {doc.doc_id for doc in current_docs}
        
        # 2. Zpracuj každý dokument
        for doc_data in current_docs:
            if not doc_data.nazev:
                continue # Skip dummy docs that were not fetched
                
            try:
                # Ořezaná logika process_document...
                # Pro ukázku zkontrolujeme existenci
                existing_doc = db.get_document(client, doc_data.doc_id)
                new_meta_hash = db.compute_metadata_hash(doc_data.to_metadata_dict())
                
                if not existing_doc:
                    # Nový dokument
                    db.insert_document(client, doc_data.to_metadata_dict())
                    db.insert_document_version(client, doc_data.doc_id, doc_data.to_metadata_dict(), new_meta_hash, 1)
                    db.log_event(client, run_id, "NEW_DOC", doc_data.doc_id, f"Nový dokument: {doc_data.nazev}")
                    stats["new"] += 1
                else:
                    db.update_document_last_seen(client, doc_data.doc_id)
                    latest_v = db.get_latest_document_version(client, doc_data.doc_id)
                    
                    if not latest_v or latest_v["metadata_hash"] != new_meta_hash:
                        next_v = (latest_v["version"] + 1) if latest_v else 1
                        db.update_document_metadata(client, doc_data.doc_id, doc_data.to_metadata_dict())
                        db.insert_document_version(client, doc_data.doc_id, doc_data.to_metadata_dict(), new_meta_hash, next_v)
                        db.log_event(client, run_id, "UPDATED_META", doc_data.doc_id, "Změna metadat")
                        stats["updated_meta"] += 1
                    else:
                        stats["unchanged"] += 1
                        
                # Přílohy
                for att in doc_data.attachments:
                    if not att.download_url: continue
                    existing_att = db.get_attachment(client, doc_data.doc_id, att.file_name)
                    
                    needs_download = False
                    att_id = None
                    
                    if not existing_att:
                        # Insert attachment if missing
                        att_dict = {
                            "doc_id": doc_data.doc_id, 
                            "file_id": att.file_id, 
                            "file_name": att.file_name, 
                            "file_size": att.file_size, 
                            "file_description": att.file_description, 
                            "download_url": att.download_url
                        }
                        att_id = db.insert_attachment(client, att_dict)
                        needs_download = True
                    else:
                        att_id = existing_att["id"]
                        ver_res = client.table("attachment_versions").select("id").eq("attachment_id", att_id).execute()
                        if not ver_res.data:
                            needs_download = True
                            
                    if needs_download:
                        storage_path = asyncio.run(download_file(att.download_url, doc_data.doc_id, att.file_name, 1))
                        if storage_path:
                            db.insert_attachment_version(client, att_id, 1, "n/a", storage_path)
                    else:
                        pass # Vercel serverless nesmí běžet moc dlouho, verzování příloh zde zjednodušíme

            except Exception as e:
                logger.error("Chyba při zpracování %s: %s", doc_data.doc_id, e)
                stats["errors"] += 1

        # 3. Odstraněné dokumenty
        removed_ids = existing_active_ids - current_doc_ids
        for r_id in removed_ids:
            db.mark_document_removed(client, r_id)
            db.log_event(client, run_id, "REMOVED_DOC", r_id, "Dokument byl odstraněn")
            stats["removed"] += 1
            
        # 4. Spustit analýzu novinek
        from analyzer import analyze_all_pending
        analyze_all_pending(client)

        return jsonify({"status": "ok", "run_id": run_id, "stats": stats})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/cron/daily-emails', methods=['GET', 'POST'])
def run_daily_emails():
    """
    Cron pro rozesílání e-mailů pomocí Resend API.
    """
    auth_header = request.headers.get("Authorization")
    if auth_header != f"Bearer {CRON_SECRET}" and request.args.get("key") != CRON_SECRET:
        return jsonify({"error": "Unauthorized"}), 401
        
    resend_key = os.environ.get("RESEND_API_KEY")
    if not resend_key:
        return jsonify({"error": "RESEND_API_KEY not set"}), 500
        
    client = db.get_client()
    try:
        from datetime import datetime, timedelta
        import requests
        
        now = datetime.now()
        yesterday = now - timedelta(days=1)
        ws_str = yesterday.isoformat()
        
        # Get docs from last 24h
        new_docs_res = client.table("document_analyses").select("doc_id, severity, summary, documents!inner(nazev, kategorie, cj_zn)").gte("documents.first_seen_at", ws_str).execute()
        docs = new_docs_res.data
        if not docs:
            return jsonify({"status": "ok", "message": "No new documents in the last 24 hours."})
            
        subs_res = client.table("email_subscriptions").select("*").eq("is_active", True).execute()
        subs = subs_res.data
        if not subs:
            return jsonify({"status": "ok", "message": "No active subscribers."})
            
        emails_sent = 0
        for sub in subs:
            filtered_docs = []
            for d in docs:
                doc = d.get("documents", {})
                cat = doc.get("kategorie")
                sev = d.get("severity")
                
                # Check category
                cat_match = (not sub["categories"]) or ("all" in sub["categories"]) or (cat in sub["categories"])
                # Check severity
                sev_match = (not sub["severities"]) or ("all" in sub["severities"]) or (sev in sub["severities"])
                
                if cat_match and sev_match:
                    filtered_docs.append(d)
                    
            if filtered_docs:
                # Compose email
                html = "<h2>Denní přehled - Úřední deska Opava</h2><ul>"
                for fd in filtered_docs:
                    doc = fd.get("documents", {})
                    html += f"<li><b>{doc.get('nazev')}</b> ({doc.get('kategorie')})<br><i>AI: {fd.get('summary')}</i><br><a href='https://uredni-deska-five.vercel.app/?doc={fd.get('doc_id')}'>Detail dokumentu</a></li><br>"
                html += "</ul>"
                html += f"<hr><p><a href='https://uredni-deska-five.vercel.app/api/unsubscribe?token={sub['unsubscribe_token']}'>Odhlásit se z odběru</a></p>"
                
                payload = {
                    "from": "onboarding@resend.dev",
                    "to": sub["email"],
                    "subject": "Novinky na Úřední desce",
                    "html": html
                }
                
                r = requests.post(
                    "https://api.resend.com/emails",
                    headers={"Authorization": f"Bearer {resend_key}", "Content-Type": "application/json"},
                    json=payload
                )
                if r.status_code < 300:
                    emails_sent += 1
                else:
                    logger.error("Failed to send email to %s: %s", sub["email"], r.text)
                    
        return jsonify({"status": "ok", "sent": emails_sent})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
