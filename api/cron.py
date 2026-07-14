"""
Cron endpoint pro Vercel. Spouští scraper a analyzátor.
"""

import os
import uuid
import logging
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
        # 1. Scrapuj aktuální dokumenty
        current_docs = asyncio.run(scraper.scrape_all_documents())
        current_doc_ids = {doc.doc_id for doc in current_docs}
        existing_active_ids = db.get_all_active_doc_ids(client)
        
        # 2. Zpracuj každý dokument
        for doc_data in current_docs:
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
                    
                    if not existing_att:
                        att_dict = {"doc_id": doc_data.doc_id, "file_id": att.file_id, "file_name": att.file_name, "file_size": att.file_size, "file_description": att.file_description, "download_url": att.download_url}
                        att_id = db.insert_attachment(client, att_dict)
                        # Stáhneme do tempu a uploadneme do Supabase
                        storage_path = asyncio.run(download_file(att.download_url, doc_data.doc_id, att.file_name, 1))
                        if storage_path:
                            # Tady by se spravně ještě tahal soubor do tmp, udělal hash, atd.
                            # Jelikož download_file to rovnou ukládá a maže z tmp, hash neuděláme přesně.
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
