"""
streamlit_app.py
Bulk PDF Comparator — main Streamlit UI
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

import streamlit as st

# Make sure local packages resolve correctly when running from project root
sys.path.insert(0, str(Path(__file__).parent))

from engine.comparator import compare_pair, compare_pairs_parallel, clear_cache, MAX_WORKERS
from engine.matcher import build_file_map, build_pairs

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Bulk PDF Comparator",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="collapsed",
)

logging.basicConfig(level=logging.INFO)

# ---------------------------------------------------------------------------
# Custom CSS — premium dark-mode aesthetics
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    /* ── background ── */
    .stApp {
        background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
        min-height: 100vh;
    }

    /* ── hero header ── */
    .hero {
        text-align: center;
        padding: 2.5rem 1rem 1.5rem;
        animation: fadeIn 0.8s ease;
    }
    .hero h1 {
        font-size: 2.8rem;
        font-weight: 700;
        background: linear-gradient(90deg, #a78bfa, #60a5fa, #34d399);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.4rem;
    }
    .hero p {
        color: #94a3b8;
        font-size: 1.05rem;
    }

    /* ── glass cards ── */
    .glass-card {
        background: rgba(255,255,255,0.05);
        border: 1px solid rgba(255,255,255,0.12);
        border-radius: 16px;
        padding: 1.5rem;
        backdrop-filter: blur(12px);
        margin-bottom: 1.2rem;
    }

    /* ── section labels ── */
    .section-label {
        font-size: 0.78rem;
        font-weight: 600;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: #a78bfa;
        margin-bottom: 0.4rem;
    }

    /* ── status badges ── */
    .badge {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 999px;
        font-size: 0.75rem;
        font-weight: 600;
        letter-spacing: 0.04em;
    }
    .badge-same     { background: #064e3b; color: #34d399; }
    .badge-changed  { background: #451a03; color: #fb923c; }
    .badge-missing  { background: #312e81; color: #818cf8; }
    .badge-unread   { background: #450a0a; color: #f87171; }
    .badge-warn     { background: #422006; color: #fbbf24; }

    /* ── duplicate warning box ── */
    .dup-warning {
        background: rgba(251,191,36,0.12);
        border: 1px solid rgba(251,191,36,0.35);
        border-radius: 10px;
        padding: 0.8rem 1rem;
        color: #fbbf24;
        font-size: 0.88rem;
        margin-bottom: 1rem;
    }

    /* ── stat boxes ── */
    .stat-row {
        display: flex;
        gap: 1rem;
        margin-bottom: 1.2rem;
        flex-wrap: wrap;
    }
    .stat-box {
        flex: 1;
        min-width: 120px;
        background: rgba(255,255,255,0.06);
        border: 1px solid rgba(255,255,255,0.1);
        border-radius: 12px;
        padding: 1rem;
        text-align: center;
    }
    .stat-num {
        font-size: 2rem;
        font-weight: 700;
        line-height: 1;
    }
    .stat-lbl {
        font-size: 0.72rem;
        color: #94a3b8;
        margin-top: 0.3rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
    }

    /* ── download buttons row ── */
    .dl-row { display: flex; gap: 1rem; flex-wrap: wrap; margin-top: 1rem; }

    /* ── progress text ── */
    .prog-text { color: #94a3b8; font-size: 0.82rem; margin-top: 0.25rem; }

    /* ── fun loader ── */
    .fun-loader {
        text-align: center;
        padding: 1.4rem 1rem 1.2rem;
        background: rgba(167,139,250,0.06);
        border: 1px solid rgba(167,139,250,0.22);
        border-radius: 16px;
        margin-bottom: 0.9rem;
        position: relative;
        overflow: hidden;
    }
    .fun-loader::before {
        content: '';
        position: absolute;
        inset: 0;
        background: linear-gradient(
            120deg,
            transparent 0%,
            rgba(167,139,250,0.07) 40%,
            rgba(96,165,250,0.07) 60%,
            transparent 100%
        );
        background-size: 200% 100%;
        animation: shimmer-bg 2.4s linear infinite;
    }
    @keyframes shimmer-bg {
        0%   { background-position: 200% 0; }
        100% { background-position: -200% 0; }
    }

    .fl-icons span {
        display: inline-block;
        font-size: 1.7rem;
        margin: 0 0.25rem;
        animation: fl-bounce 0.75s ease-in-out infinite;
    }
    @keyframes fl-bounce {
        0%, 100% { transform: translateY(0px);   }
        50%       { transform: translateY(-14px); }
    }

    .fl-msg-wrap {
        position: relative;
        height: 1.35rem;
        margin: 0.65rem 0 0.5rem;
    }
    .fl-msg {
        position: absolute;
        left: 0; right: 0;
        opacity: 0;
        font-size: 0.88rem;
        font-style: italic;
        color: #94a3b8;
        animation: fl-msg-cycle 12.5s ease-in-out infinite;
    }
    @keyframes fl-msg-cycle {
        0%          { opacity: 0; transform: translateY(6px);  }
        4%, 16%     { opacity: 1; transform: translateY(0px);  }
        20%, 100%   { opacity: 0; transform: translateY(-6px); }
    }

    .fl-dots span {
        display: inline-block;
        width: 9px; height: 9px;
        border-radius: 50%;
        margin: 0 5px;
        animation: fl-dot-pulse 1.2s ease-in-out infinite;
    }
    @keyframes fl-dot-pulse {
        0%, 80%, 100% { transform: scale(0.55); opacity: 0.35; }
        40%           { transform: scale(1.1);  opacity: 1;    }
    }

    /* ── elapsed timer ── */
    .timer-box {
        display: inline-flex;
        align-items: center;
        gap: 0.45rem;
        border-radius: 999px;
        padding: 0.35rem 1.1rem;
        font-size: 1rem;
        font-weight: 600;
        font-variant-numeric: tabular-nums;
        letter-spacing: 0.03em;
        margin-bottom: 0.75rem;
    }
    .timer-running {
        color: #60a5fa;
        border: 1px solid rgba(96,165,250,0.35);
        background: rgba(96,165,250,0.08);
    }
    .timer-done {
        color: #34d399;
        border: 1px solid rgba(52,211,153,0.35);
        background: rgba(52,211,153,0.08);
    }

    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(-12px); }
        to   { opacity: 1; transform: translateY(0);     }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Hero header
# ---------------------------------------------------------------------------
st.markdown(
    """
    <div class="hero">
        <h1>📄 Bulk PDF Comparator</h1>
        <p>Compare up to 100 PDFs in seconds — matched by filename identifier prefix</p>
        <p style="margin-top:0.5rem; font-size:0.82rem; color:#64748b; letter-spacing:0.05em;">
            Made by <strong style="color:#a78bfa;">Aditya</strong>
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Instructions popover icon (hidden by default, shown on click)
# ---------------------------------------------------------------------------
_, icon_col, _ = st.columns([5, 1, 5])
with icon_col:
    with st.popover("ℹ️ Help", use_container_width=True):
        st.markdown(
            """
            <style>
            /* ── popover instruction panels (light bg — high contrast) ── */
            .inst-section {
                border-radius: 10px;
                padding: 0.85rem 1rem;
                margin-bottom: 0.75rem;
                font-family: 'Inter', sans-serif;
            }
            /* Blue — file naming */
            .inst-blue   { background: #dbeafe; border-left: 4px solid #1d4ed8; }
            .inst-blue   .inst-title { color: #1e3a8a; }
            .inst-blue   .inst-body  { color: #1e3a5f; }
            /* Purple — steps */
            .inst-purple { background: #ede9fe; border-left: 4px solid #6d28d9; }
            .inst-purple .inst-title { color: #4c1d95; }
            .inst-purple .inst-step  { color: #3b1f7a; }
            /* Green — status */
            .inst-green  { background: #d1fae5; border-left: 4px solid #059669; }
            .inst-green  .inst-title { color: #064e3b; }
            /* Yellow — tip */
            .inst-yellow { background: #fef9c3; border-left: 4px solid #ca8a04; }
            .inst-yellow .inst-title { color: #713f12; }
            .inst-yellow .inst-body  { color: #78350f; }

            .inst-title {
                font-size: 0.72rem;
                font-weight: 800;
                letter-spacing: 0.1em;
                text-transform: uppercase;
                margin-bottom: 0.55rem;
            }
            .inst-body { font-size: 0.84rem; line-height: 1.65; }
            .inst-body code, .inst-blue code {
                background: #bfdbfe;
                color: #1e3a8a;
                padding: 1px 5px;
                border-radius: 4px;
                font-size: 0.8rem;
            }

            /* numbered steps */
            .inst-step {
                display: flex;
                gap: 0.55rem;
                align-items: flex-start;
                margin-bottom: 0.35rem;
                font-size: 0.84rem;
            }
            .step-num {
                background: #6d28d9;
                color: #fff;
                border-radius: 50%;
                width: 20px; height: 20px;
                display: flex; align-items: center; justify-content: center;
                font-weight: 700; font-size: 0.7rem;
                flex-shrink: 0; margin-top: 1px;
            }

            /* status pills */
            .badge-row  { display: flex; flex-wrap: wrap; gap: 0.45rem; margin-top: 0.5rem; }
            .spill      { padding: 4px 11px; border-radius: 999px; font-size: 0.75rem;
                          font-weight: 700; white-space: nowrap; }
            .sp-same    { background: #bbf7d0; color: #14532d; }
            .sp-changed { background: #fed7aa; color: #7c2d12; }
            .sp-missing { background: #c7d2fe; color: #312e81; }
            .sp-unread  { background: #fecaca; color: #7f1d1d; }
            </style>

            <!-- Naming convention -->
            <div class="inst-section inst-blue">
                <div class="inst-title">📁 File Naming Convention</div>
                <div class="inst-body">
                    Files are matched on the <strong>prefix before the first <code>_</code></strong>:
                    <br><br>
                    <code>001_invoice_old.pdf &nbsp;↔&nbsp; 001_invoice_new.pdf</code><br>
                    <code>002_report_old.pdf &nbsp;↔&nbsp; 002_report_v2.pdf</code><br>
                    <code>003_policy_old.pdf &nbsp;↔&nbsp; ❌ no match → MISSING_NEW_FILE</code>
                </div>
            </div>

            <!-- Steps -->
            <div class="inst-section inst-purple">
                <div class="inst-title">🚀 How to Run</div>
                <div class="inst-step"><span class="step-num">1</span><span>Enter the <strong>Old PDFs Folder</strong> path</span></div>
                <div class="inst-step"><span class="step-num">2</span><span>Enter the <strong>New PDFs Folder</strong> path</span></div>
                <div class="inst-step"><span class="step-num">3</span><span>Click <strong>⚡ Compare PDFs</strong> — live progress bar tracks each pair</span></div>
                <div class="inst-step"><span class="step-num">4</span><span>Review the results table (Identifier · Similarity · Status)</span></div>
            </div>

            <!-- Status meanings -->
            <div class="inst-section inst-green">
                <div class="inst-title">🏷️ Status Meanings</div>
                <div class="badge-row">
                    <span class="spill sp-same">✅ SAME &mdash; similarity &ge; 0.99</span>
                    <span class="spill sp-changed">🔶 CHANGED &mdash; content differs</span>
                    <span class="spill sp-missing">🔵 MISSING NEW FILE</span>
                    <span class="spill sp-missing">🔵 MISSING OLD FILE</span>
                    <span class="spill sp-unread">🔴 UNREADABLE</span>
                </div>
            </div>

            <!-- Tip -->
            <div class="inst-section inst-yellow">
                <div class="inst-title">💡 Tip</div>
                <div class="inst-body">
                    Scanned or image-only PDFs are automatically processed with
                    <strong>OCR</strong> (Tesseract) — no extra setup needed.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

# ---------------------------------------------------------------------------
# Folder inputs
# ---------------------------------------------------------------------------
col_old, col_new = st.columns(2)

with col_old:
    st.markdown('<p class="section-label">Old PDFs Folder</p>', unsafe_allow_html=True)
    old_folder = st.text_input(
        "old_folder",
        placeholder="e.g. C:\\pdfs\\old  or  /home/user/old",
        label_visibility="collapsed",
        key="old_folder_input",
    )

with col_new:
    st.markdown('<p class="section-label">New PDFs Folder</p>', unsafe_allow_html=True)
    new_folder = st.text_input(
        "new_folder",
        placeholder="e.g. C:\\pdfs\\new  or  /home/user/new",
        label_visibility="collapsed",
        key="new_folder_input",
    )

st.markdown("<br>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Status badge helper
# ---------------------------------------------------------------------------
STATUS_CONFIG = {
    "SAME":              ("badge-same",    "✅ SAME"),
    "CHANGED":           ("badge-changed", "🔶 CHANGED"),
    "MISSING_NEW_FILE":  ("badge-missing", "🔵 MISSING NEW"),
    "MISSING_OLD_FILE":  ("badge-missing", "🔵 MISSING OLD"),
    "UNREADABLE":        ("badge-unread",  "🔴 UNREADABLE"),
    "MISSING_BOTH":      ("badge-unread",  "🔴 MISSING BOTH"),
}


def _badge(status: str) -> str:
    cls, label = STATUS_CONFIG.get(status, ("badge-warn", status))
    return f'<span class="badge {cls}">{label}</span>'


def _fmt_elapsed(seconds: float) -> str:
    mins = int(seconds // 60)
    secs = seconds % 60
    if mins > 0:
        return f"{mins}m {secs:05.2f}s"
    return f"{secs:.2f}s"


# ---------------------------------------------------------------------------
# Compare button
# ---------------------------------------------------------------------------
run_btn = st.button("⚡ Compare PDFs", use_container_width=True, type="primary")

if run_btn:
    # ── validation ────────────────────────────────────────────────────────────
    errors = []
    if not old_folder:
        errors.append("Please enter the **Old PDFs Folder** path.")
    elif not Path(old_folder).is_dir():
        errors.append(f"Old folder not found: `{old_folder}`")

    if not new_folder:
        errors.append("Please enter the **New PDFs Folder** path.")
    elif not Path(new_folder).is_dir():
        errors.append(f"New folder not found: `{new_folder}`")

    if errors:
        for e in errors:
            st.error(e)
        st.stop()

    # ── build file maps ───────────────────────────────────────────────────────
    with st.spinner("Scanning folders …"):
        old_map, old_dups = build_file_map(old_folder)
        new_map, new_dups = build_file_map(new_folder)
        pairs               = build_pairs(old_map, new_map)

    # ── duplicate warnings ────────────────────────────────────────────────────
    all_dups = sorted(set(old_dups + new_dups))
    if all_dups:
        dup_list = ", ".join(f"<code>{d}</code>" for d in all_dups)
        st.markdown(
            f'<div class="dup-warning">⚠️ <strong>Duplicate identifiers detected</strong>'
            f" — only the first file is used per identifier: {dup_list}</div>",
            unsafe_allow_html=True,
        )

    if not pairs:
        st.warning("No PDF files found in one or both folders.")
        st.stop()

    total = len(pairs)

    # ── clear cache for fresh comparison ─────────────────────────────────────
    clear_cache()

    # ── timer + progress bar setup ───────────────────────────────────────────
    start_time = time.time()
    timer_placeholder = st.empty()
    timer_placeholder.markdown(
        '<div class="timer-box timer-running">⏱ 0.00s</div>',
        unsafe_allow_html=True,
    )

    _dot_colors = ["#a78bfa", "#60a5fa", "#34d399"]
    _dot_styles = " ".join(
        f'<span style="background:{c};animation-delay:{i*0.22}s"></span>'
        for i, c in enumerate(_dot_colors)
    )
    _fun_loader_html = f"""
    <div class="fun-loader">
        <div class="fl-icons">
            <span style="animation-delay:0s">🧑‍💻</span>
            <span style="animation-delay:0.15s">🕵️</span>
            <span style="animation-delay:0.3s">🤓</span>
            <span style="animation-delay:0.45s">💪</span>
            <span style="animation-delay:0.6s">🙌</span>
        </div>
        <div class="fl-msg-wrap">
            <span class="fl-msg" style="animation-delay:0s">Your PDFs are in good hands 💪</span>
            <span class="fl-msg" style="animation-delay:2.5s">Good things take a moment ☕</span>
            <span class="fl-msg" style="animation-delay:5s">Leaving no page unturned 🕵️</span>
            <span class="fl-msg" style="animation-delay:7.5s">This is the way 🚀</span>
            <span class="fl-msg" style="animation-delay:10s">Almost done, hang tight! 🎯</span>
        </div>
        <div class="fl-dots">{_dot_styles}</div>
    </div>
    """

    loader_placeholder = st.empty()
    loader_placeholder.markdown(_fun_loader_html, unsafe_allow_html=True)

    progress_bar = st.progress(0, text=f"Starting parallel comparison ({MAX_WORKERS} workers) …")
    status_text  = st.empty()
    progress_container = st.empty()

    completed_count = [0]

    def progress_callback(completed: int, total_count: int) -> None:
        completed_count[0] = completed
        pct = int(completed / total_count * 100)
        progress_bar.progress(pct, text=f"Comparing PDFs: {completed}/{total_count} complete ({pct}%)")
        elapsed = time.time() - start_time
        timer_placeholder.markdown(
            f'<div class="timer-box timer-running">⏱ {_fmt_elapsed(elapsed)}</div>',
            unsafe_allow_html=True,
        )

    results = compare_pairs_parallel(pairs, progress_callback=progress_callback)

    loader_placeholder.empty()
    elapsed_total = time.time() - start_time
    timer_placeholder.markdown(
        f'<div class="timer-box timer-done">Scan completed in - ⏱ {_fmt_elapsed(elapsed_total)} &nbsp;·&nbsp;</div>',
        unsafe_allow_html=True,
    )
    progress_bar.progress(100, text="✅ Comparison complete!")
    status_text.empty()
    progress_container.empty()

    # ── summary statistics ────────────────────────────────────────────────────
    statuses  = [r["status"] for r in results]
    n_same    = statuses.count("SAME")
    n_changed = statuses.count("CHANGED")
    n_missing = sum(1 for s in statuses if "MISSING" in s)
    n_unread  = sum(1 for s in statuses if "UNREAD" in s or s == "MISSING_BOTH")

    st.markdown(
        f"""
        <div class="stat-row">
            <div class="stat-box">
                <div class="stat-num" style="color:#34d399">{n_same}</div>
                <div class="stat-lbl">Same</div>
            </div>
            <div class="stat-box">
                <div class="stat-num" style="color:#fb923c">{n_changed}</div>
                <div class="stat-lbl">Changed</div>
            </div>
            <div class="stat-box">
                <div class="stat-num" style="color:#818cf8">{n_missing}</div>
                <div class="stat-lbl">Missing</div>
            </div>
            <div class="stat-box">
                <div class="stat-num" style="color:#f87171">{n_unread}</div>
                <div class="stat-lbl">Unreadable</div>
            </div>
            <div class="stat-box">
                <div class="stat-num" style="color:#e2e8f0">{total}</div>
                <div class="stat-lbl">Total Pairs</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── results table ─────────────────────────────────────────────────────────
    st.markdown("### 📋 Comparison Results")

    # Build HTML table for badge rendering
    table_rows = ""
    for r in results:
        sim_display = (
            f"{r['similarity']:.4f}" if isinstance(r["similarity"], float) else r["similarity"]
        )
        badge_html = _badge(r["status"])
        table_rows += (
            f"<tr>"
            f"<td><code>{r['identifier']}</code></td>"
            f"<td>{r['old_file']}</td>"
            f"<td>{r['new_file']}</td>"
            f"<td style='text-align:center'>{r['old_pages']}</td>"
            f"<td style='text-align:center'>{r['new_pages']}</td>"
            f"<td style='text-align:center'>{sim_display}</td>"
            f"<td style='text-align:center'>{badge_html}</td>"
            f"<td>{r.get('notes','')}</td>"
            f"</tr>"
        )

    table_html = f"""
    <style>
    .results-table {{
        width: 100%;
        border-collapse: collapse;
        font-size: 0.84rem;
        color: #e2e8f0;
    }}
    .results-table th {{
        background: rgba(167,139,250,0.15);
        color: #a78bfa;
        font-weight: 600;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        font-size: 0.72rem;
        padding: 10px 12px;
        text-align: left;
        border-bottom: 1px solid rgba(255,255,255,0.1);
    }}
    .results-table td {{
        padding: 9px 12px;
        border-bottom: 1px solid rgba(255,255,255,0.06);
        vertical-align: middle;
        word-break: break-word;
    }}
    .results-table tr:hover td {{
        background: rgba(255,255,255,0.04);
    }}
    </style>
    <table class="results-table">
      <thead>
        <tr>
          <th>Identifier</th>
          <th>Old File</th>
          <th>New File</th>
          <th>Old Pages</th>
          <th>New Pages</th>
          <th>Similarity</th>
          <th>Status</th>
          <th>Notes</th>
        </tr>
      </thead>
      <tbody>
        {table_rows}
      </tbody>
    </table>
    """
    st.markdown(table_html, unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.markdown("<br><br>", unsafe_allow_html=True)
st.markdown(
    '<p style="text-align:center; color:#475569; font-size:0.78rem;">'
    "Bulk PDF Comparator &nbsp;·&nbsp; Supports up to 100 PDFs &nbsp;·&nbsp; OCR-enabled"
    "<br><span style='color:#64748b;'>Made with ❤️ by <strong style='color:#a78bfa;'>Aditya</strong></span>"
    "</p>",
    unsafe_allow_html=True,
)
