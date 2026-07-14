"""
Flask API server pro webové rozhraní archivačního systému (Vercel Serverless ready).
"""

import os
import sys
from datetime import datetime, timedelta
import json as _json

# Fix sys.path for imports from root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, jsonify, request, send_from_directory
import database as db
import config

# Fix encoding (místní běh Windows)
if os.name == 'nt':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

app = Flask(__name__, static_folder='../web', static_url_path='')

def _parse_czech_date(date_str):
    if not date_str:
        return ''
    try:
        parts = date_str.split('.')
        if len(parts) == 3:
            day, month, year = parts
            return f"{year}-{int(month):02d}-{int(day):02d}"
    except (ValueError, IndexError):
        pass
    return date_str

@app.route('/')
def index():
    return send_from_directory('../web', 'index.html')


@app.route('/api/stats')
def api_stats():
    client = db.get_client()
    try:
        stats = db.get_statistics(client)
        return jsonify(stats)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/categories')
def api_categories():
    client = db.get_client()
    try:
        res = client.table("documents").select("kategorie").neq("kategorie", None).neq("kategorie", "").execute()
        cats = sorted(list(set([r["kategorie"] for r in res.data])))
        return jsonify(cats)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/departments')
def api_departments():
    client = db.get_client()
    try:
        res = client.table("documents").select("zdroj").neq("zdroj", None).neq("zdroj", "").execute()
        depts = sorted(list(set([r["zdroj"] for r in res.data])))
        return jsonify(depts)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/documents')
def api_documents():
    client = db.get_client()
    try:
        search = request.args.get('search', '').strip()
        category = request.args.get('category', '').strip()
        department = request.args.get('department', '').strip()
        status = request.args.get('status', 'all').strip()
        severity = request.args.get('severity', '').strip()
        date_from = request.args.get('date_from', '').strip()
        date_to = request.args.get('date_to', '').strip()
        sort_by = request.args.get('sort', 'first_seen_at').strip()
        sort_dir = request.args.get('dir', 'desc').strip()

        # Build query
        query = client.table("documents").select("*, document_analyses(severity)")

        if status == 'active':
            query = query.eq("is_active", True)
        elif status == 'removed':
            query = query.eq("is_active", False)

        if category:
            query = query.eq("kategorie", category)
        if department:
            query = query.eq("zdroj", department)
        
        # Supabase Python client doesn't support easy joins filtering out top-level, so we filter in python if severity is set
        # For dates, Supabase handles string ISO comparison
        if date_from:
            query = query.gte("first_seen_at", date_from)
        if date_to:
            query = query.lte("first_seen_at", date_to + "T23:59:59Z")
            
        if search:
            # simple text search (Supabase has full-text search, but basic like is fine)
            query = query.or_(f"nazev.ilike.%{search}%,popis.ilike.%{search}%,cj_zn.ilike.%{search}%,doc_id.ilike.%{search}%")

        # Ordering
        is_asc = (sort_dir == 'asc')
        if sort_by == 'first_seen_at':
            query = query.order('first_seen_at', desc=not is_asc)
        elif sort_by == 'last_seen_at':
            query = query.order('last_seen_at', desc=not is_asc)
        elif sort_by == 'nazev':
            query = query.order('nazev', desc=not is_asc)
        
        res = query.execute()
        
        docs = res.data
        
        # Post-filter for severity if requested, since it's nested in supabase query result
        if severity:
            filtered_docs = []
            for d in docs:
                analyses = d.get("document_analyses")
                sev = None
                if isinstance(analyses, list) and len(analyses) > 0:
                    sev = analyses[0].get("severity")
                elif isinstance(analyses, dict):
                    sev = analyses.get("severity")
                
                if sev == severity:
                    filtered_docs.append(d)
            docs = filtered_docs
            
        # Post-sort for vyveseni_dne using python since it's not standard format
        if sort_by == 'vyveseni_dne':
            docs.sort(key=lambda d: _parse_czech_date(d.get("vyveseni_dne")), reverse=not is_asc)

        # Simplify structure for frontend
        for d in docs:
            analyses = d.get("document_analyses")
            if isinstance(analyses, list) and len(analyses) > 0:
                d["severity"] = analyses[0].get("severity")
            elif isinstance(analyses, dict):
                d["severity"] = analyses.get("severity")
            else:
                d["severity"] = None
                
            if "document_analyses" in d:
                del d["document_analyses"]

        if sort_by == 'severity':
            def sev_weight(doc):
                s = doc.get("severity")
                if s == 'Závažné': return 3
                if s == 'Vyžaduje pozornost': return 2
                if s == 'Běžný': return 1
                return 0
            docs.sort(key=sev_weight, reverse=not is_asc)

        return jsonify(docs)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/api/documents/<doc_id>')
def api_document_detail(doc_id):
    client = db.get_client()
    try:
        history = db.get_document_history(client, doc_id)
        if not history:
            return jsonify({"error": "Document not found"}), 404
        analysis = db.get_analysis(client, doc_id)
        history["analysis"] = analysis
        return jsonify(history)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/attachment/<doc_id>/<path:filename>')
def api_attachment(doc_id, filename):
    import urllib.parse
    client = db.get_client()
    try:
        decoded_filename = urllib.parse.unquote(filename)
        # Find attachment
        att_res = client.table("attachments").select("id").eq("doc_id", doc_id).eq("file_name", decoded_filename).execute()
        if not att_res.data:
            return jsonify({"error": "Attachment not found"}), 404
            
        att_id = att_res.data[0]["id"]
        
        # Get latest version
        ver_res = client.table("attachment_versions").select("local_path").eq("attachment_id", att_id).order("version", desc=True).limit(1).execute()
        if not ver_res.data:
            return jsonify({"error": "Attachment version not found"}), 404
            
        storage_path = ver_res.data[0]["local_path"]
        
        # Get public URL
        public_url = client.storage.from_("attachments").get_public_url(storage_path)
        
        from flask import redirect
        return redirect(public_url)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/events')
def api_events():
    client = db.get_client()
    try:
        limit = request.args.get('limit', 50, type=int)
        # Fetch events
        events_res = client.table("scrape_log").select("*").order("created_at", desc=True).limit(limit).execute()
        
        # Need to fetch document names manually to mimic JOIN
        doc_ids = [e["doc_id"] for e in events_res.data if e.get("doc_id")]
        if doc_ids:
            docs_res = client.table("documents").select("doc_id, nazev").in_("doc_id", doc_ids).execute()
            doc_map = {d["doc_id"]: d["nazev"] for d in docs_res.data}
        else:
            doc_map = {}
            
        events = events_res.data
        for e in events:
            e["nazev"] = doc_map.get(e.get("doc_id"))
            
        return jsonify(events)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/runs')
def api_runs():
    client = db.get_client()
    try:
        # Fetching grouped runs in supabase without RPC is tricky, we'll fetch last 1000 events and group in Python
        res = client.table("scrape_log").select("*").order("created_at", desc=True).limit(1000).execute()
        
        runs = {}
        for ev in res.data:
            r_id = ev["run_id"]
            if r_id not in runs:
                runs[r_id] = {
                    "run_id": r_id, "started": ev["created_at"], "finished": ev["created_at"],
                    "event_count": 0, "new_docs": 0, "meta_updates": 0, "file_updates": 0, "removals": 0, "errors": 0
                }
            r = runs[r_id]
            r["started"] = min(r["started"], ev["created_at"])
            r["finished"] = max(r["finished"], ev["created_at"])
            r["event_count"] += 1
            if ev["event_type"] == "NEW_DOC": r["new_docs"] += 1
            if ev["event_type"] == "UPDATED_META": r["meta_updates"] += 1
            if ev["event_type"] == "UPDATED_FILE": r["file_updates"] += 1
            if ev["event_type"] == "REMOVED_DOC": r["removals"] += 1
            if ev["event_type"] == "ERROR": r["errors"] += 1
            
        # Return top 20 runs
        sorted_runs = sorted(list(runs.values()), key=lambda x: x["started"], reverse=True)[:20]
        return jsonify(sorted_runs)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/weekly-summary')
def api_weekly_summary():
    client = db.get_client()
    try:
        now = datetime.now()
        days_since_monday = now.weekday()
        week_end = (now - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = week_end - timedelta(days=7)
        ws_str = week_start.strftime('%Y-%m-%d')
        we_str = week_end.strftime('%Y-%m-%d')

        # Check cache
        cached_res = client.table("weekly_summaries").select("*").eq("week_start", ws_str).execute()
        if cached_res.data:
            cached = cached_res.data[0]
            return jsonify({
                "summary": cached["summary_text"],
                "doc_ids": cached.get("doc_ids", []),
                "week_start": ws_str,
                "week_end": we_str,
                "cost_czk": float(cached["cost_czk"]),
                "prompt_tokens": cached["prompt_tokens"],
                "completion_tokens": cached["completion_tokens"],
                "model": cached["model"],
                "generated_at": cached["created_at"],
                "cached": True,
            })

        # Generate (For Vercel this should technically be moved to cron, but we keep it here for fallback)
        notable_res = client.table("document_analyses").select("doc_id, severity, summary, documents!inner(first_seen_at, nazev, kategorie)").neq("severity", "Běžný").gte("documents.first_seen_at", ws_str).lt("documents.first_seen_at", we_str).execute()
        notable_docs = notable_res.data
        
        if not notable_docs:
            summary_text = "Tento týden nebyly zaznamenány žádné dokumenty vyžadující zvláštní pozornost."
            client.table("weekly_summaries").insert({
                "week_start": ws_str, "week_end": we_str, "summary_text": summary_text,
                "doc_ids": [], "prompt_tokens": 0, "completion_tokens": 0, "cost_czk": 0.0, "model": None
            }).execute()
            return jsonify({
                "summary": summary_text, "doc_ids": [], "week_start": ws_str, "week_end": we_str,
                "cost_czk": 0.0, "prompt_tokens": 0, "completion_tokens": 0, "model": None, "generated_at": now.isoformat(), "cached": False,
            })

        # Gemini prompt...
        doc_list_text = ""
        doc_ids = []
        for d in notable_docs[:30]:
            doc_id = d["doc_id"]
            doc_ids.append(doc_id)
            doc_name = d["documents"]["nazev"] if d.get("documents") else "(bez názvu)"
            cat = d["documents"]["kategorie"] if d.get("documents") else "?"
            doc_list_text += (
                f"- [{doc_id}] {doc_name} | Kategorie: {cat} | Závažnost: {d['severity']} | AI shrnutí: {d['summary'] or '-'}\n"
            )

        prompt = f"""Jsi analytik úřední desky města Opavy. Na základě seznamu pozoruhodných dokumentů z tohoto týdne napiš stručné shrnutí (max 3-5 vět) o tom, co se událo. Zaměř se na nejdůležitější věci pro občany.

Dokumenty tohoto týdne:
{doc_list_text}

Pravidla:
1. Piš česky, jasně a srozumitelně pro běžného občana
2. Zmiň jen to nejpodstatnější (1-3 body)
3. U každého zmíněného dokumentu uveď jeho ID v hranatých závorkách, např. [MMOP0B54BR1Q]
4. Pokud jsou tam stavební záměry, prodeje majetku nebo krizová opatření, zdůrazni je
5. Max 100 slov
6. Nepoužívej markdown formátování, jen čistý text s ID v hranatých závorkách"""

        from google import genai
        from google.genai import types
        
        genai_client = genai.Client(api_key=config.GEMINI_API_KEY)
        response = genai_client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(max_output_tokens=300, temperature=0.3),
        )

        usage = response.usage_metadata
        pt = usage.prompt_token_count
        ct = usage.candidates_token_count
        cost_usd = (pt * config.AI_INPUT_PRICE_PER_TOKEN + ct * config.AI_OUTPUT_PRICE_PER_TOKEN)
        cost_czk = round(cost_usd * config.AI_USD_TO_CZK, 6)
        summary_text = response.text.strip()

        client.table("weekly_summaries").insert({
            "week_start": ws_str, "week_end": we_str, "summary_text": summary_text,
            "doc_ids": doc_ids, "prompt_tokens": pt, "completion_tokens": ct, "cost_czk": cost_czk, "model": config.GEMINI_MODEL
        }).execute()

        return jsonify({
            "summary": summary_text, "doc_ids": doc_ids, "week_start": ws_str, "week_end": we_str,
            "cost_czk": cost_czk, "prompt_tokens": pt, "completion_tokens": ct, "model": config.GEMINI_MODEL,
            "generated_at": now.isoformat(), "cached": False,
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# API pro Vercel export
# Není potřeba spouštět app.run() v serverless prostředí, Vercel si vezme app automaticky
