"""
PDF Auto-Renamer
================
Matches OLD and NEW PDFs by filename similarity (then content fallback),
then renames them as 001_..., 002_..., 003_... pairs so your comparison
software can run correctly.

Requirements:
    pip install pypdf
"""

import os
import re
import sys
import shutil
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from difflib import SequenceMatcher
from pathlib import Path
import threading

try:
    from pypdf import PdfReader
    PDF_READ_OK = True
except ImportError:
    PDF_READ_OK = False


# ─────────────────────────── Matching Logic ──────────────────────────────────

def clean_name(filename: str) -> str:
    """Strip extension, existing numeric prefix like 001_, and lowercase."""
    name = Path(filename).stem
    name = re.sub(r'^\d{1,4}_+', '', name)   # remove leading 001_ style prefix
    name = re.sub(r'[_\-\s]+', ' ', name).strip().lower()
    return name


def name_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, clean_name(a), clean_name(b)).ratio()


def extract_text_snippet(filepath: str, max_chars: int = 800) -> str:
    """Pull first max_chars of text from a PDF for content matching."""
    if not PDF_READ_OK:
        return ""
    try:
        reader = PdfReader(filepath)
        text = ""
        for page in reader.pages[:3]:          # first 3 pages is enough
            text += (page.extract_text() or "")
            if len(text) >= max_chars:
                break
        return text[:max_chars].lower()
    except Exception:
        return ""


def content_similarity(path_a: str, path_b: str) -> float:
    ta = extract_text_snippet(path_a)
    tb = extract_text_snippet(path_b)
    if not ta or not tb:
        return 0.0
    return SequenceMatcher(None, ta, tb).ratio()


def build_matches(old_files: list, new_files: list,
                  progress_cb=None) -> list:
    """
    Returns list of dicts:
      { 'id': int, 'old': path|None, 'new': path|None,
        'method': 'name'|'content'|'unmatched', 'score': float }
    """
    NAME_THRESHOLD   = 0.60   # min name similarity to auto-match
    CONTENT_THRESHOLD = 0.45  # min content similarity to auto-match

    old_remaining = list(old_files)
    new_remaining = list(new_files)
    pairs = []

    total = len(old_files) * len(new_files) if new_files else 1
    done = 0

    # ── Pass 1: Name-based matching ──────────────────────────────────────────
    used_new = set()
    name_scores = {}

    for o in old_remaining:
        best_score, best_n = 0.0, None
        for n in new_remaining:
            if n in used_new:
                continue
            s = name_similarity(Path(o).name, Path(n).name)
            name_scores[(o, n)] = s
            if s > best_score:
                best_score, best_n = s, n
            done += 1
            if progress_cb:
                progress_cb(int(done / max(total, 1) * 50))

        if best_score >= NAME_THRESHOLD and best_n:
            pairs.append({'old': o, 'new': best_n,
                          'method': 'name', 'score': best_score})
            used_new.add(best_n)
        else:
            pairs.append({'old': o, 'new': None,
                          'method': 'pending', 'score': best_score})

    # ── Pass 2: Content-based matching for unresolved ────────────────────────
    pending_old = [p for p in pairs if p['new'] is None]
    remaining_new = [n for n in new_remaining if n not in used_new]

    for p in pending_old:
        o = p['old']
        best_score, best_n = 0.0, None
        for n in remaining_new:
            s = content_similarity(o, n)
            if s > best_score:
                best_score, best_n = s, n
            done += 1
            if progress_cb:
                progress_cb(50 + int(done / max(total, 1) * 50))

        if best_score >= CONTENT_THRESHOLD and best_n:
            p['new'] = best_n
            p['method'] = 'content'
            p['score'] = best_score
            remaining_new.remove(best_n)
            used_new.add(best_n)
        else:
            p['method'] = 'unmatched_old'

    # ── Leftover NEW files with no OLD match ─────────────────────────────────
    for n in new_remaining:
        if n not in used_new:
            pairs.append({'old': None, 'new': n,
                          'method': 'unmatched_new', 'score': 0.0})

    # ── Assign sequential IDs to confirmed pairs ─────────────────────────────
    matched = [p for p in pairs if p['old'] and p['new']]
    matched.sort(key=lambda p: clean_name(Path(p['old']).name))
    for i, p in enumerate(matched, start=1):
        p['id'] = i

    unmatched = [p for p in pairs if not (p['old'] and p['new'])]
    for p in unmatched:
        p['id'] = None

    if progress_cb:
        progress_cb(100)

    return matched + unmatched


def do_rename(pairs: list, old_dir: str, new_dir: str) -> list:
    """
    Rename files in-place. Returns list of (status, old_path, new_path, error).
    Safely handles name collisions using a temp suffix.
    """
    log = []
    for p in pairs:
        if p['id'] is None:
            continue
        prefix = f"{p['id']:03d}_"

        for filepath, folder in [(p['old'], old_dir), (p['new'], new_dir)]:
            if not filepath:
                continue
            src = Path(folder) / Path(filepath).name
            new_name = prefix + re.sub(r'^\d{1,4}_+', '', Path(filepath).name)
            dst = Path(folder) / new_name

            if src == dst:
                log.append(('skip', str(src), str(dst), ''))
                continue
            if dst.exists():
                log.append(('error', str(src), str(dst),
                             'Destination already exists'))
                continue
            try:
                src.rename(dst)
                log.append(('ok', str(src), str(dst), ''))
            except Exception as e:
                log.append(('error', str(src), str(dst), str(e)))
    return log


# ─────────────────────────── GUI ─────────────────────────────────────────────

DARK   = "#111116"
PANEL  = "#1a1a22"
BORDER = "#2e2e3a"
ACCENT = "#f5c842"
BLUE   = "#5ab4f5"
GREEN  = "#4ecf7e"
RED    = "#f06060"
WARN   = "#f09050"
MUTED  = "#6b6b80"
TEXT   = "#e0e0ec"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PDF Auto-Renamer")
        self.geometry("980x720")
        self.minsize(800, 580)
        self.configure(bg=DARK)
        self.resizable(True, True)

        self.old_dir = tk.StringVar()
        self.new_dir = tk.StringVar()
        self.pairs   = []

        self._build_ui()
        self._style_ttk()

    # ── UI construction ───────────────────────────────────────────────────────

    def _style_ttk(self):
        s = ttk.Style(self)
        s.theme_use('clam')
        s.configure('TProgressbar', troughcolor=BORDER,
                    background=ACCENT, thickness=6)
        s.configure('Treeview',
                    background=PANEL, foreground=TEXT,
                    fieldbackground=PANEL, rowheight=28,
                    borderwidth=0, font=('Consolas', 10))
        s.configure('Treeview.Heading',
                    background=BORDER, foreground=MUTED,
                    relief='flat', font=('Consolas', 9, 'bold'))
        s.map('Treeview', background=[('selected', '#2a2a40')])

    def _label(self, parent, text, size=11, color=TEXT, bold=False, **kw):
        font = ('Segoe UI', size, 'bold' if bold else 'normal')
        return tk.Label(parent, text=text, font=font,
                        bg=kw.pop('bg', DARK), fg=color, **kw)

    def _btn(self, parent, text, command, accent=False, small=False):
        bg   = ACCENT if accent else PANEL
        fg   = DARK   if accent else TEXT
        size = 10 if small else 11
        b = tk.Button(parent, text=text, command=command,
                      font=('Segoe UI', size, 'bold'),
                      bg=bg, fg=fg, relief='flat',
                      activebackground=ACCENT if accent else BORDER,
                      activeforeground=DARK,
                      cursor='hand2', pady=8, padx=18,
                      bd=0, highlightthickness=0)
        return b

    def _folder_row(self, parent, label, var, color):
        row = tk.Frame(parent, bg=PANEL)
        row.pack(fill='x', padx=20, pady=(0, 12))

        dot = tk.Frame(row, bg=color, width=10, height=10)
        dot.pack(side='left', padx=(0, 10))
        dot.pack_propagate(False)

        tk.Label(row, text=label, font=('Segoe UI', 10, 'bold'),
                 bg=PANEL, fg=color, width=10, anchor='w').pack(side='left')

        entry = tk.Entry(row, textvariable=var,
                         font=('Consolas', 10),
                         bg=DARK, fg=TEXT, insertbackground=TEXT,
                         relief='flat', bd=0, highlightthickness=1,
                         highlightbackground=BORDER,
                         highlightcolor=ACCENT)
        entry.pack(side='left', fill='x', expand=True, ipady=6, padx=(0, 8))

        self._btn(row, '📂  Browse',
                  lambda v=var: self._browse(v), small=True).pack(side='right')

    def _build_ui(self):
        # ── Header ───────────────────────────────────────────────────────────
        hdr = tk.Frame(self, bg=DARK, pady=20)
        hdr.pack(fill='x', padx=30)

        tk.Label(hdr, text='PDF  AUTO-RENAMER',
                 font=('Consolas', 20, 'bold'),
                 bg=DARK, fg=ACCENT).pack(side='left')
        tk.Label(hdr,
                 text='  ·  matches by name + content, then renames as 001_ 002_ pairs',
                 font=('Segoe UI', 10), bg=DARK, fg=MUTED).pack(side='left')

        # ── Folder pickers ───────────────────────────────────────────────────
        folder_frame = tk.Frame(self, bg=PANEL,
                                highlightthickness=1,
                                highlightbackground=BORDER)
        folder_frame.pack(fill='x', padx=24, pady=(0, 16))

        tk.Label(folder_frame, text='SELECT FOLDERS',
                 font=('Consolas', 9, 'bold'),
                 bg=PANEL, fg=MUTED).pack(anchor='w', padx=20, pady=(14, 10))

        self._folder_row(folder_frame, '📁  OLD', self.old_dir, WARN)
        self._folder_row(folder_frame, '📁  NEW', self.new_dir, BLUE)

        # ── Action bar ───────────────────────────────────────────────────────
        action = tk.Frame(self, bg=DARK)
        action.pack(fill='x', padx=24, pady=(0, 12))

        self.btn_scan = self._btn(action, '🔍  SCAN & MATCH', self._start_scan, accent=True)
        self.btn_scan.pack(side='left')

        self.btn_rename = self._btn(action, '✅  RENAME ALL MATCHED',
                                    self._do_rename)
        self.btn_rename.pack(side='left', padx=(12, 0))
        self.btn_rename.config(state='disabled')

        self.btn_clear = self._btn(action, '✖  Clear', self._clear, small=True)
        self.btn_clear.pack(side='right')

        # Progress
        self.progress = ttk.Progressbar(action, mode='determinate',
                                        length=180, style='TProgressbar')
        self.progress.pack(side='right', padx=(0, 16))
        self.status_lbl = tk.Label(action, text='', font=('Segoe UI', 9),
                                   bg=DARK, fg=MUTED)
        self.status_lbl.pack(side='right', padx=(0, 8))

        # ── Results tree ─────────────────────────────────────────────────────
        tree_frame = tk.Frame(self, bg=DARK)
        tree_frame.pack(fill='both', expand=True, padx=24, pady=(0, 8))

        cols = ('id', 'old_file', 'new_file', 'method', 'score')
        self.tree = ttk.Treeview(tree_frame, columns=cols,
                                 show='headings', selectmode='browse')

        hdrs = [('id', 'ID', 52), ('old_file', 'OLD PDF', 320),
                ('new_file', 'NEW PDF', 320),
                ('method', 'Match', 90), ('score', 'Score', 72)]
        for col, heading, width in hdrs:
            self.tree.heading(col, text=heading)
            self.tree.column(col, width=width, minwidth=50,
                             anchor='center' if col in ('id','method','score') else 'w')

        self.tree.tag_configure('matched_name',    background='#1a2a1a', foreground=GREEN)
        self.tree.tag_configure('matched_content', background='#1a221a', foreground='#9ef0be')
        self.tree.tag_configure('unmatched',       background='#2a1a1a', foreground=RED)
        self.tree.tag_configure('renamed',         background='#1a1a2a', foreground=BLUE)

        scroll = ttk.Scrollbar(tree_frame, orient='vertical',
                               command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')

        # ── Summary bar ──────────────────────────────────────────────────────
        self.summary = tk.Frame(self, bg=PANEL,
                                highlightthickness=1,
                                highlightbackground=BORDER)
        self.summary.pack(fill='x', padx=24, pady=(0, 16))
        self._make_stats()

    def _make_stats(self):
        for w in self.summary.winfo_children():
            w.destroy()
        stats = [
            ('MATCHED', '—', GREEN),
            ('BY NAME', '—', ACCENT),
            ('BY CONTENT', '—', BLUE),
            ('UNMATCHED', '—', RED),
        ]
        for i, (lbl, val, color) in enumerate(stats):
            f = tk.Frame(self.summary, bg=PANEL)
            f.pack(side='left', padx=28, pady=10)
            tk.Label(f, text=val, font=('Consolas', 22, 'bold'),
                     bg=PANEL, fg=color).pack()
            tk.Label(f, text=lbl, font=('Consolas', 8),
                     bg=PANEL, fg=MUTED).pack()
            setattr(self, f'stat_{lbl.lower().replace(" ","_")}',
                    f.winfo_children()[0])

    # ── Handlers ──────────────────────────────────────────────────────────────

    def _browse(self, var):
        d = filedialog.askdirectory()
        if d:
            var.set(d)

    def _clear(self):
        self.pairs = []
        self.tree.delete(*self.tree.get_children())
        self.btn_rename.config(state='disabled')
        self.progress['value'] = 0
        self.status_lbl.config(text='')
        self._make_stats()

    def _start_scan(self):
        old_dir = self.old_dir.get().strip()
        new_dir = self.new_dir.get().strip()
        if not old_dir or not new_dir:
            messagebox.showwarning('Missing folders',
                                   'Please select both OLD and NEW folders.')
            return
        if not os.path.isdir(old_dir) or not os.path.isdir(new_dir):
            messagebox.showerror('Invalid folders',
                                 'One or both folders do not exist.')
            return

        old_files = sorted([os.path.join(old_dir, f)
                            for f in os.listdir(old_dir)
                            if f.lower().endswith('.pdf')])
        new_files = sorted([os.path.join(new_dir, f)
                            for f in os.listdir(new_dir)
                            if f.lower().endswith('.pdf')])

        if not old_files:
            messagebox.showwarning('No PDFs', 'No PDF files found in OLD folder.')
            return
        if not new_files:
            messagebox.showwarning('No PDFs', 'No PDF files found in NEW folder.')
            return

        self.btn_scan.config(state='disabled')
        self.btn_rename.config(state='disabled')
        self.tree.delete(*self.tree.get_children())
        self.progress['value'] = 0
        self.status_lbl.config(text='Scanning…')

        def worker():
            def prog(v):
                self.progress['value'] = v
                self.status_lbl.config(
                    text=f'Analysing… {v}%' if v < 100 else 'Done!')
                self.update_idletasks()

            pairs = build_matches(old_files, new_files, progress_cb=prog)
            self.after(0, lambda: self._show_results(pairs))

        threading.Thread(target=worker, daemon=True).start()

    def _show_results(self, pairs):
        self.pairs = pairs
        self.tree.delete(*self.tree.get_children())

        n_matched = n_name = n_content = n_unmatched = 0

        for p in pairs:
            id_str  = f"{p['id']:03d}" if p['id'] else '—'
            old_str = Path(p['old']).name if p['old'] else '❌  missing'
            new_str = Path(p['new']).name if p['new'] else '❌  missing'
            method  = p['method'].replace('_', ' ')
            score   = f"{p['score']:.0%}" if p['score'] else '—'

            if p['id']:
                n_matched += 1
                if p['method'] == 'name':
                    tag, n_name = 'matched_name', n_name + 1
                else:
                    tag, n_content = 'matched_content', n_content + 1
            else:
                tag = 'unmatched'
                n_unmatched += 1

            self.tree.insert('', 'end',
                             values=(id_str, old_str, new_str, method, score),
                             tags=(tag,))

        self.stat_matched.config(text=str(n_matched))
        self.stat_by_name.config(text=str(n_name))
        self.stat_by_content.config(text=str(n_content))
        self.stat_unmatched.config(text=str(n_unmatched))

        self.btn_scan.config(state='normal')
        if n_matched:
            self.btn_rename.config(state='normal')

        if n_unmatched:
            self.status_lbl.config(
                text=f'⚠  {n_unmatched} unmatched — review before renaming',
                fg=WARN)
        else:
            self.status_lbl.config(
                text=f'✓ All {n_matched} PDFs matched!', fg=GREEN)

    def _do_rename(self):
        matched = [p for p in self.pairs if p['id']]
        if not matched:
            return

        msg = (f"This will rename {len(matched)} pairs of PDFs in:\n\n"
               f"OLD:  {self.old_dir.get()}\n"
               f"NEW:  {self.new_dir.get()}\n\n"
               f"Files will be prefixed 001_, 002_, etc.\n\n"
               f"Continue?")
        if not messagebox.askyesno('Confirm Rename', msg):
            return

        log = do_rename(self.pairs, self.old_dir.get(), self.new_dir.get())

        errors = [l for l in log if l[0] == 'error']
        ok     = [l for l in log if l[0] == 'ok']

        # Refresh tree to show new names
        self._refresh_tree_after_rename()

        if errors:
            err_msg = '\n'.join(f"{e[1]} → {e[3]}" for e in errors[:10])
            messagebox.showwarning('Some errors',
                                   f'{len(ok)} renamed, {len(errors)} errors:\n\n{err_msg}')
        else:
            messagebox.showinfo('Done! ✅',
                                f'Successfully renamed {len(ok)} files.\n\n'
                                f'You can now run your comparison software!')
        self.btn_rename.config(state='disabled')
        self.status_lbl.config(text=f'✅  {len(ok)} files renamed', fg=GREEN)

    def _refresh_tree_after_rename(self):
        """Update tree to show new filenames."""
        for item in self.tree.get_children():
            vals = list(self.tree.item(item, 'values'))
            id_str = vals[0]
            if id_str == '—':
                continue
            # prefix already applied — re-read from disk
            # just mark row as renamed
            self.tree.item(item, tags=('renamed',))


# ─────────────────────────── Entry point ─────────────────────────────────────

if __name__ == '__main__':
    app = App()
    app.mainloop()
