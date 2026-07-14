/* ═══════════════════════════════════════════════
   Archiv úřední desky – Frontend Logic
   ═══════════════════════════════════════════════ */

let currentSort = 'first_seen_at';
let currentDir = 'desc';
let searchTimer = null;
let allDocuments = [];

// ── Init ────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    loadStats();
    loadWeeklySummary();
    loadCategories();
    loadDepartments();
    loadDocuments();
    loadTimeline();
    loadRuns();
});

// ── API Helpers ─────────────────────────────────
async function api(path) {
    const res = await fetch(path);
    if (!res.ok) throw new Error(`API error: ${res.status}`);
    return res.json();
}

// ── Stats ───────────────────────────────────────
async function loadStats() {
    try {
        const s = await api('/api/stats');
        animateNumber('statTotal', s.total_documents);
        animateNumber('statActive', s.active_documents);
        animateNumber('statRemoved', s.removed_documents);
        animateNumber('statAttention', s.severity_attention);
        animateNumber('statSerious', s.severity_serious);
        if (s.last_run && s.last_run.last_run) {
            document.getElementById('lastUpdate').textContent =
                'Poslední aktualizace: ' + formatDateTime(s.last_run.last_run);
        }
    } catch (e) { console.error('Stats error:', e); }
}

// ── Weekly Summary ──────────────────────────────
async function loadWeeklySummary() {
    try {
        const data = await api('/api/weekly-summary');
        const contentEl = document.getElementById('weeklySummaryContent');
        const costEl = document.getElementById('weeklySummaryCost');
        const rangeEl = document.getElementById('weeklySummaryDateRange');

        // Format date range (YYYY-MM-DD → D.M.YYYY)
        const fmtDate = (s) => {
            const [y, m, d] = s.split('-');
            return `${parseInt(d)}.${parseInt(m)}.${y}`;
        };
        rangeEl.textContent = `${fmtDate(data.week_start)} – ${fmtDate(data.week_end)}`;

        // Find any document ID starting with MMOP and make it a clickable link
        let html = esc(data.summary).replace(
            /(MMOP[A-Z0-9]+)/g,
            '<a class="text-primary hover:underline cursor-pointer font-bold" onclick="openDetail(\'$1\')">$1</a>'
        );
        contentEl.innerHTML = html;

        // Cost info
        if (data.cost_czk > 0) {
            costEl.textContent = `Shrnutí stálo ${data.cost_czk.toFixed(4)} Kč · ${data.cached ? 'Uloženo v cache' : 'Vygenerováno nyní'} · Model: ${data.model || '–'}`;
        } else {
            costEl.textContent = `Shrnutí stálo 0.00 Kč · ${data.cached ? 'Uloženo v cache' : 'Vygenerováno nyní'} · Bez API`;
        }
        costEl.classList.remove('hidden');
    } catch (e) {
        console.error('Weekly summary error:', e);
        const contentEl = document.getElementById('weeklySummaryContent');
        if (contentEl) contentEl.innerHTML = '<span class="text-on-surface-variant text-body-sm">Shrnutí se nepodařilo načíst.</span>';
    }
}

function animateNumber(id, target) {
    const el = document.getElementById(id);
    if (!el) return;
    const duration = 800;
    const start = performance.now();
    const from = 0;
    function step(now) {
        const progress = Math.min((now - start) / duration, 1);
        const ease = 1 - Math.pow(1 - progress, 3);
        el.textContent = Math.round(from + (target - from) * ease);
        if (progress < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
}

// ── Categories & Departments ────────────────────
async function loadCategories() {
    try {
        const cats = await api('/api/categories');
        const sel = document.getElementById('categoryFilter');
        cats.forEach(c => {
            const opt = document.createElement('option');
            opt.value = c; opt.textContent = c;
            sel.appendChild(opt);
        });
    } catch (e) { console.error(e); }
}

async function loadDepartments() {
    try {
        const deps = await api('/api/departments');
        const sel = document.getElementById('departmentFilter');
        deps.forEach(d => {
            const opt = document.createElement('option');
            opt.value = d; opt.textContent = d;
            sel.appendChild(opt);
        });
    } catch (e) { console.error(e); }
}

// ── Documents ───────────────────────────────────
async function loadDocuments() {
    const params = new URLSearchParams();
    const search = document.getElementById('searchInput').value.trim();
    const category = document.getElementById('categoryFilter').value;
    const department = document.getElementById('departmentFilter').value;
    const status = document.getElementById('statusFilter').value;
    const severity = document.getElementById('severityFilter').value;
    const dateFrom = document.getElementById('dateFrom').value;
    const dateTo = document.getElementById('dateTo').value;

    if (search) params.set('search', search);
    if (category) params.set('category', category);
    if (department) params.set('department', department);
    if (status) params.set('status', status);
    if (severity) params.set('severity', severity);
    if (dateFrom) params.set('date_from', dateFrom);
    if (dateTo) params.set('date_to', dateTo);
    params.set('sort', currentSort);
    params.set('dir', currentDir);

    document.getElementById('searchClear').style.display = search ? 'block' : 'none';

    // Sync stat card highlights with current filters
    const sevFilterMap = { 'Vyžaduje pozornost': 'sev-attention', 'Závažné': 'sev-serious' };
    const activeFilter = severity ? (sevFilterMap[severity] || '') : status;
    document.querySelectorAll('.stat-filter').forEach(card => {
        card.classList.toggle('active', card.dataset.filter === activeFilter);
    });

    try {
        allDocuments = await api('/api/documents?' + params.toString());
        renderDocuments(allDocuments);
    } catch (e) { console.error(e); }
}

function renderDocuments(docs) {
    const tbody = document.getElementById('docTableBody');
    const empty = document.getElementById('emptyState');
    document.getElementById('resultCount').textContent = docs.length;

    if (docs.length === 0) {
        tbody.innerHTML = '';
        empty.style.display = 'block';
        return;
    }
    empty.style.display = 'none';

    tbody.innerHTML = docs.map((doc, i) => {
        const sevMap = {'Běžný': 'bg-outline', 'Vyžaduje pozornost': 'bg-tertiary ai-dot-glow', 'Závažné': 'bg-error ai-dot-glow'};
        const sevClass = sevMap[doc.severity] || 'bg-outline';
        const isInactive = !doc.is_active;
        return `
        <tr class="hover:bg-surface-container-high/50 transition-colors cursor-pointer h-row-height bg-surface-container-highest ${isInactive ? 'opacity-60' : ''}" onclick="openDetail('${doc.doc_id}')">
            <td class="px-6">
                <span class="text-body-sm text-on-surface-variant whitespace-nowrap">${esc(doc.kategorie || '–')}</span>
            </td>
            <td class="px-6">
                <div class="font-bold text-on-surface truncate max-w-xs" title="${esc(doc.nazev || '')}">${esc(doc.nazev || '–')}</div>
            </td>
            <td class="px-6">
                <span class="font-data-mono text-data-mono text-on-surface-variant">${esc(doc.cj_zn || '–')}</span>
            </td>
            <td class="px-6">
                <span class="text-body-sm text-on-surface-variant">${esc(doc.vyveseni_dne || '–')}</span>
            </td>
            <td class="px-6 text-center">
                <div class="flex items-center justify-center gap-1 text-on-surface-variant">
                    <span class="material-symbols-outlined text-[16px]">attachment</span>
                    <span class="text-body-sm font-bold">${doc.attachment_count || 0}</span>
                </div>
            </td>
            <td class="px-6 text-center">
                <div class="inline-block w-2.5 h-2.5 rounded-full ${sevClass}"></div>
            </td>
            <td class="px-6">
                ${doc.is_active
                    ? '<div class="flex items-center gap-2"><div class="w-2 h-2 rounded-full bg-secondary active-dot-glow"></div><span class="text-[11px] font-bold text-secondary tracking-widest">AKTIVNÍ</span></div>'
                    : '<div class="flex items-center gap-2"><div class="w-2 h-2 rounded-full bg-outline"></div><span class="text-[11px] font-bold text-on-surface-variant tracking-widest">NEAKTIVNÍ</span></div>'
                }
            </td>
        </tr>`;
    }).join('');

    // Update sort indicators
    document.querySelectorAll('th.sortable').forEach(th => {
        th.classList.remove('asc', 'desc');
        if (th.dataset.sort === currentSort) th.classList.add(currentDir);
    });
}

// ── Sorting ─────────────────────────────────────
function toggleSort(col) {
    if (currentSort === col) {
        currentDir = currentDir === 'asc' ? 'desc' : 'asc';
    } else {
        currentSort = col;
        currentDir = 'asc';
    }
    loadDocuments();
}

// ── Stat Card Quick Filter ─────────────────────
function filterByStat(value) {
    // Determine which dropdown to set
    if (value === 'sev-attention') {
        document.getElementById('statusFilter').value = 'all';
        document.getElementById('severityFilter').value = 'Vyžaduje pozornost';
    } else if (value === 'sev-serious') {
        document.getElementById('statusFilter').value = 'all';
        document.getElementById('severityFilter').value = 'Závažné';
    } else {
        document.getElementById('statusFilter').value = value;
        document.getElementById('severityFilter').value = '';
    }
    // Highlight active card
    document.querySelectorAll('.stat-filter').forEach(card => {
        card.classList.toggle('active', card.dataset.filter === value);
    });
    loadDocuments();
}

// ── Search ──────────────────────────────────────
function debounceSearch() {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(loadDocuments, 300);
}

function clearSearch() {
    document.getElementById('searchInput').value = '';
    loadDocuments();
}

// ── Detail Panel ────────────────────────────────
async function openDetail(docId) {
    const panel = document.getElementById('detailPanel');
    const overlay = document.getElementById('detailOverlay');
    const content = document.getElementById('detailContent');

    panel.classList.add('open');
    overlay.classList.add('open');
    content.innerHTML = '<div class="loading"><div class="spinner"></div></div>';

    try {
        const data = await api('/api/documents/' + docId);
        renderDetail(data);
    } catch (e) {
        content.innerHTML = '<p class="text-error p-4">Chyba při načítání detailu.</p>';
    }
}

function closeDetail() {
    document.getElementById('detailPanel').classList.remove('open');
    document.getElementById('detailOverlay').classList.remove('open');
}

function renderDetail(data) {
    const doc = data.document;
    const content = document.getElementById('detailContent');

    // Update header
    document.getElementById('detailTitle').textContent = doc.doc_id;
    const statusEl = document.getElementById('detailStatus');
    if (doc.is_active) {
        statusEl.className = 'px-3 py-1 text-[10px] font-bold tracking-widest uppercase rounded-full status-active flex items-center gap-1.5';
        statusEl.innerHTML = '<span class="w-1.5 h-1.5 bg-secondary rounded-full animate-pulse"></span> AKTIVNÍ';
    } else {
        statusEl.className = 'px-3 py-1 text-[10px] font-bold tracking-widest uppercase rounded-full status-inactive flex items-center gap-1.5';
        statusEl.innerHTML = '<span class="w-1.5 h-1.5 bg-outline rounded-full"></span> NEAKTIVNÍ';
    }
    document.getElementById('detailSubtitle').textContent = 'Poslední aktualizace: ' + formatDateTime(doc.last_seen_at);

    let html = '<div class="grid grid-cols-12 gap-4 lg:gap-6">';

    // ═══ LEFT COLUMN (8 cols) ═══
    html += '<div class="col-span-12 lg:col-span-8 space-y-4 lg:space-y-6">';

    // ── AI Analysis Card (hero) ──
    if (data.analysis) {
        const a = data.analysis;
        const sevMap = {
            'Běžný': { icon: 'verified', color: 'text-secondary', bannerClass: 'urgent-banner-routine', bannerIcon: 'check_circle', label: 'Běžný dokument' },
            'Vyžaduje pozornost': { icon: 'warning', color: 'text-tertiary', bannerClass: 'urgent-banner-attention', bannerIcon: 'warning', label: 'Vyžaduje pozornost' },
            'Závažné': { icon: 'error', color: 'text-error', bannerClass: 'urgent-banner', bannerIcon: 'warning', label: 'Závažné' },
        };
        const sev = sevMap[a.severity] || sevMap['Běžný'];

        html += `<section class="glass-card rounded-xl p-5 lg:p-6 relative overflow-hidden">
            <div class="absolute top-0 right-0 p-6 opacity-[0.08] pointer-events-none">
                <span class="material-symbols-outlined text-primary text-[64px]">psychology</span>
            </div>
            <div class="flex items-center gap-2 mb-5">
                <span class="material-symbols-outlined text-primary" style="font-variation-settings: 'FILL' 1;">auto_awesome</span>
                <h3 class="text-label-caps font-label-caps text-primary tracking-widest">AI ANALÝZA A SHRNUTÍ</h3>
            </div>
            <div class="${sev.bannerClass} p-4 mb-5 flex items-start gap-4 rounded-lg">
                <span class="material-symbols-outlined ${sev.color} flex-shrink-0" style="font-variation-settings: 'FILL' 1;">${sev.bannerIcon}</span>
                <div>
                    <h4 class="text-on-surface font-bold text-body-md">${esc(sev.label)}</h4>
                    ${a.summary ? `<p class="text-on-surface-variant text-body-sm mt-1">${esc(a.summary)}</p>` : ''}
                </div>
            </div>
            ${doc.nazev ? `<div class="mb-5">
                <h4 class="text-body-sm font-bold text-on-surface-variant mb-2 uppercase tracking-tight">Kontext dokumentu</h4>
                <p class="text-title-sm font-title-sm leading-relaxed text-on-surface">${esc(doc.nazev)}</p>
                ${doc.popis && doc.popis !== doc.nazev ? `<p class="text-body-sm text-on-surface-variant mt-2">${esc(doc.popis)}</p>` : ''}
            </div>` : ''}
        </section>`;
    } else {
        // No AI analysis — show document name as hero
        html += `<section class="glass-card rounded-xl p-5 lg:p-6">
            <div class="flex items-center gap-2 mb-4">
                <span class="material-symbols-outlined text-on-surface-variant">description</span>
                <h3 class="text-label-caps font-label-caps text-on-surface-variant tracking-widest">DOKUMENT</h3>
            </div>
            <p class="text-title-sm font-title-sm text-on-surface">${esc(doc.nazev || '–')}</p>
            ${doc.popis ? `<p class="text-body-sm text-on-surface-variant mt-2">${esc(doc.popis)}</p>` : ''}
        </section>`;
    }

    // ── Metadata Card ──
    html += `<section class="glass-card rounded-xl p-5 lg:p-6">
        <div class="flex items-center gap-2 mb-5">
            <span class="material-symbols-outlined text-on-surface-variant">info</span>
            <h3 class="text-label-caps font-label-caps text-on-surface-variant tracking-widest">METADATA ZÁZNAMU</h3>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-x-12 gap-y-0">
            <div class="detail-meta-row">
                <span class="text-body-sm text-on-surface-variant">ID systému</span>
                <span class="font-data-mono text-data-mono text-on-surface">${esc(doc.doc_id)}</span>
            </div>
            <div class="detail-meta-row">
                <span class="text-body-sm text-on-surface-variant">Kategorie</span>
                <span class="font-bold text-on-surface">${esc(doc.kategorie || '–')}</span>
            </div>
            <div class="detail-meta-row">
                <span class="text-body-sm text-on-surface-variant">Číslo jednací</span>
                <span class="font-data-mono text-data-mono text-on-surface">${esc(doc.cj_zn || '–')}</span>
            </div>
            <div class="detail-meta-row">
                <span class="text-body-sm text-on-surface-variant">Vystavil</span>
                <span class="font-bold text-on-surface">${esc(doc.zdroj || '–')}</span>
            </div>
            <div class="detail-meta-row">
                <span class="text-body-sm text-on-surface-variant">Vyvěšeno</span>
                <span class="font-data-mono text-data-mono text-on-surface">${esc(doc.vyveseni_dne || '–')}</span>
            </div>
            <div class="detail-meta-row">
                <span class="text-body-sm text-on-surface-variant">Svěšeno</span>
                <span class="font-data-mono text-data-mono text-on-surface">${esc(doc.sejmuti_dne || '–')}</span>
            </div>
            <div class="detail-meta-row">
                <span class="text-body-sm text-on-surface-variant">Poprvé viděn</span>
                <span class="font-data-mono text-data-mono text-on-surface">${formatDateTime(doc.first_seen_at)}</span>
            </div>
            <div class="detail-meta-row">
                <span class="text-body-sm text-on-surface-variant">Naposledy viděn</span>
                <span class="font-data-mono text-data-mono text-on-surface">${formatDateTime(doc.last_seen_at)}</span>
            </div>
            ${doc.removed_at ? `<div class="detail-meta-row">
                <span class="text-body-sm text-on-surface-variant">Odstraněn</span>
                <span class="font-data-mono text-data-mono text-error">${formatDateTime(doc.removed_at)}</span>
            </div>` : ''}
            ${doc.poznamka ? `<div class="detail-meta-row">
                <span class="text-body-sm text-on-surface-variant">Poznámka</span>
                <span class="text-on-surface">${esc(doc.poznamka)}</span>
            </div>` : ''}
        </div>
    </section>`;

    html += '</div>'; // end left column

    // ═══ RIGHT COLUMN (4 cols) ═══
    html += '<div class="col-span-12 lg:col-span-4 space-y-4 lg:space-y-6">';

    // ── Timeline / Events Card ──
    if (data.events && data.events.length > 0) {
        html += `<section class="glass-card rounded-xl p-5 lg:p-6">
            <div class="flex items-center gap-2 mb-5">
                <span class="material-symbols-outlined text-on-surface-variant">history</span>
                <h3 class="text-label-caps font-label-caps text-on-surface-variant tracking-widest">HISTORIE AKTIVITY</h3>
            </div>
            <div class="relative space-y-5 before:content-[''] before:absolute before:left-[11px] before:top-2 before:bottom-0 before:w-px before:bg-outline-variant">`;
        const evtColors = {
            'NEW_DOC': { bg: 'bg-secondary-container', ring: 'ring-secondary', label: 'text-secondary' },
            'UPDATED_META': { bg: 'bg-primary', ring: 'ring-primary/40', label: 'text-on-surface-variant' },
            'UPDATED_FILE': { bg: 'bg-tertiary', ring: 'ring-tertiary/40', label: 'text-on-surface-variant' },
            'REMOVED_DOC': { bg: 'bg-error', ring: 'ring-error/40', label: 'text-on-surface-variant' },
            'ERROR': { bg: 'bg-error', ring: 'ring-error/40', label: 'text-on-surface-variant' },
            'RUN_COMPLETE': { bg: 'bg-surface-container-highest', ring: 'ring-outline-variant', label: 'text-on-surface-variant' },
        };
        data.events.slice().reverse().forEach((e, i) => {
            const ec = evtColors[e.event_type] || evtColors['RUN_COMPLETE'];
            html += `<div class="relative pl-8">
                <div class="absolute left-0 top-1.5 w-[23px] h-[23px] ${ec.bg} rounded-full border-4 border-surface ring-1 ${ec.ring}"></div>
                <div class="flex flex-col">
                    <span class="text-label-caps font-label-caps ${i === 0 ? 'text-secondary' : ec.label}">${formatDateTime(e.created_at)}</span>
                    <span class="text-body-md font-bold text-on-surface">${esc(e.message || e.event_type)}</span>
                </div>
            </div>`;
        });
        html += '</div></section>';
    }

    // ── Metadata Versions Card ──
    if (data.metadata_versions && data.metadata_versions.length > 0) {
        html += `<section class="glass-card rounded-xl p-5 lg:p-6">
            <div class="flex items-center gap-2 mb-5">
                <span class="material-symbols-outlined text-on-surface-variant">schedule</span>
                <h3 class="text-label-caps font-label-caps text-on-surface-variant tracking-widest">VERZE METADAT (${data.metadata_versions.length})</h3>
            </div>
            <div class="space-y-2">`;
        data.metadata_versions.slice().reverse().forEach((v, i) => {
            const isCurrent = i === 0;
            html += `<div class="p-3 rounded-lg border ${isCurrent ? 'border-primary/30 bg-primary/5' : 'border-outline-variant/20 bg-surface-container-lowest/50'}">
                <div class="flex justify-between items-center">
                    <span class="text-body-md font-bold text-on-surface">Verze ${v.version}</span>
                    ${isCurrent ? '<span class="text-[10px] font-bold text-primary bg-primary/10 px-2 py-0.5 rounded">AKTUÁLNÍ</span>' : ''}
                </div>
                <span class="text-label-caps font-label-caps text-on-surface-variant block mt-1">${formatDateTime(v.created_at)}</span>
                <span class="font-data-mono text-[11px] text-outline mt-1 block">${v.metadata_hash.substring(0, 16)}…</span>
            </div>`;
        });
        html += '</div></section>';
    }

    // ── Attachments Card ──
    if (data.attachments && data.attachments.length > 0) {
        html += `<section class="glass-card rounded-xl p-5 lg:p-6">
            <div class="flex items-center gap-2 mb-5">
                <span class="material-symbols-outlined text-on-surface-variant">attachment</span>
                <h3 class="text-label-caps font-label-caps text-on-surface-variant tracking-widest">PŘÍLOHY (${data.attachments.length})</h3>
            </div>
            <div class="space-y-3">`;
        data.attachments.forEach(att => {
            const ext = (att.file_name || '').split('.').pop().toUpperCase() || '?';
            const isPDF = ext === 'PDF';
            html += `<div class="flex items-center gap-4 p-3 bg-surface-container-lowest rounded border border-outline-variant/30 hover:border-primary/50 transition-colors group cursor-pointer">
                <div class="w-10 h-10 ${isPDF ? 'bg-error/20' : 'bg-primary/20'} flex items-center justify-center rounded flex-shrink-0">
                    <span class="material-symbols-outlined ${isPDF ? 'text-error' : 'text-primary'}">picture_as_pdf</span>
                </div>
                <div class="flex-1 min-w-0">
                    <p class="text-body-md font-bold text-on-surface truncate">${esc(att.file_name)}</p>
                    <p class="text-label-caps font-label-caps text-on-surface-variant">Verze: v${att.current_version}${att.file_size ? ' · ' + esc(att.file_size) : ''} · ${ext}</p>
                </div>`;
            // Download links
            if (att.versions && att.versions.length > 0) {
                const latest = att.versions[att.versions.length - 1];
                const fname = latest.local_path.split(/[\\/]/).pop();
                html += `<a href="/api/attachment/${encodeURIComponent(att.doc_id)}/${encodeURIComponent(fname)}" target="_blank" class="flex-shrink-0" onclick="event.stopPropagation()">
                    <span class="material-symbols-outlined text-on-surface-variant group-hover:text-primary transition-colors">download</span>
                </a>`;
            }
            html += '</div>';
        });
        html += '</div></section>';
    }

    // ── Cost Widget ──
    if (data.analysis) {
        const a = data.analysis;
        const costText = a.is_analyzed_by_ai
            ? `${a.cost_czk.toFixed(4)} Kč`
            : '0.00 Kč';
        const costNote = a.is_analyzed_by_ai
            ? `Model: ${esc(a.model || 'Gemini')}, Vstup: ${a.prompt_tokens} tok., Výstup: ${a.completion_tokens} tok.`
            : 'Zpracováno lokálním filtrem bez použití placeného API.';
        html += `<div class="p-4 bg-gradient-to-br from-[#171f33] to-[#0b1326] rounded-xl border border-outline-variant/30 shadow-2xl">
            <div class="flex justify-between items-center mb-2">
                <span class="text-label-caps font-label-caps text-on-surface-variant">ANALÝZA STÁLA</span>
                <span class="text-body-sm font-data-mono text-secondary">${costText}</span>
            </div>
            <div class="w-full bg-surface-container-highest h-1 rounded-full overflow-hidden">
                <div class="bg-secondary h-full transition-all duration-1000" style="width: ${a.is_analyzed_by_ai ? '100%' : '15%'}"></div>
            </div>
            <p class="text-[10px] mt-2 text-on-surface-variant italic">${costNote}</p>
        </div>`;
    }

    html += '</div>'; // end right column
    html += '</div>'; // end grid

    content.innerHTML = html;
}


// ── Timeline Tab ────────────────────────────────
async function loadTimeline() {
    try {
        const events = await api('/api/events?limit=100');
        const container = document.getElementById('timelineList');
        if (events.length === 0) {
            container.innerHTML = '<div class="empty-state"><p>Žádné události</p></div>';
            return;
        }
        container.innerHTML = events.map(e => {
            let extra = '';
            if (e.doc_id && e.nazev) {
                extra = `<div class="event-doc" onclick="openDetail('${e.doc_id}')">${esc(e.nazev)}</div>`;
            }
            return `<div class="event-item">${renderEventInner(e)}${extra}</div>`;
        }).join('');
    } catch (e) { console.error(e); }
}

function renderEvent(e) {
    return `<div class="event-item">${renderEventInner(e)}</div>`;
}

function renderEventInner(e) {
    const iconMap = {
        'NEW_DOC': ['add_circle', 'new'], 'UPDATED_META': ['edit_note', 'update'],
        'UPDATED_FILE': ['sync', 'update'], 'REMOVED_DOC': ['delete', 'remove'],
        'ERROR': ['warning', 'error'], 'RUN_COMPLETE': ['check_circle', 'complete']
    };
    const [icon, cls] = iconMap[e.event_type] || ['circle', ''];
    return `
        <div class="event-icon ${cls}"><span class="material-symbols-outlined text-[18px]">${icon}</span></div>
        <div class="event-body">
            <div class="event-msg">${esc(e.message || e.event_type)}</div>
            <div class="event-time">${formatDateTime(e.created_at)}</div>
        </div>`;
}

// ── Runs Tab ────────────────────────────────────
async function loadRuns() {
    try {
        const runs = await api('/api/runs');
        const container = document.getElementById('runsList');
        if (runs.length === 0) {
            container.innerHTML = '<div class="empty-state"><p>Žádné záznamy o bězích</p></div>';
            return;
        }
        container.innerHTML = runs.map(r => `
            <div class="run-card">
                <div class="run-header">
                    <span class="run-id">#${esc(r.run_id)}</span>
                    <span class="run-time">${formatDateTime(r.started)}</span>
                </div>
                <div class="run-stats">
                    <div class="run-stat"><span class="run-stat-dot new"></span> ${r.new_docs} nových</div>
                    <div class="run-stat"><span class="run-stat-dot meta"></span> ${r.meta_updates} meta změn</div>
                    <div class="run-stat"><span class="run-stat-dot file"></span> ${r.file_updates} souborů</div>
                    <div class="run-stat"><span class="run-stat-dot removed"></span> ${r.removals} odstraněno</div>
                    <div class="run-stat"><span class="run-stat-dot error"></span> ${r.errors} chyb</div>
                </div>
            </div>
        `).join('');
    } catch (e) { console.error(e); }
}

// ── Tab switching ───────────────────────────────
function switchTab(name) {
    // Update sidebar nav
    document.querySelectorAll('#sidebar nav a').forEach(a => {
        const tab = a.dataset.tab;
        if (tab === name) {
            a.className = 'flex items-center gap-3 px-4 py-3 bg-secondary-container text-on-secondary-container font-bold rounded-lg transition-transform translate-x-1';
        } else {
            a.className = 'flex items-center gap-3 px-4 py-3 text-on-surface-variant hover:bg-surface-container-high transition-all rounded-lg group';
        }
    });
    // Update tab content
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    const tabEl = document.getElementById(name + 'Tab');
    if (tabEl) tabEl.classList.add('active');
    // Show/hide filters (only for documents tab)
    const filters = document.getElementById('filtersSection');
    const stats = document.getElementById('statsSection');
    if (filters) filters.style.display = name === 'documents' ? '' : 'none';
    if (stats) stats.style.display = name === 'documents' ? '' : 'none';
    // Close mobile sidebar
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebarOverlay');
    if (sidebar) sidebar.classList.remove('open');
    if (overlay) overlay.classList.remove('open');
}

// ── Export ───────────────────────────────────────
async function exportJSON() {
    try {
        const docs = await api('/api/documents?status=all');
        const blob = new Blob([JSON.stringify(docs, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = 'uredni_deska_export.json';
        a.click(); URL.revokeObjectURL(url);
    } catch (e) { alert('Export selhal: ' + e.message); }
}

// ── Utilities ───────────────────────────────────
function esc(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function formatDateTime(dt) {
    if (!dt) return '–';
    try {
        const d = new Date(dt);
        if (isNaN(d.getTime())) return dt;
        return d.toLocaleDateString('cs-CZ') + ' ' +
            d.toLocaleTimeString('cs-CZ', { hour: '2-digit', minute: '2-digit' });
    } catch { return dt; }
}

// Keyboard: Escape closes detail
document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeDetail();
});
