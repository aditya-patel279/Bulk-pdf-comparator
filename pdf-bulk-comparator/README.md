# Bulk PDF Comparator

A Streamlit-powered Python tool that compares two sets of PDF files in bulk, matched by a **numeric identifier prefix** in the filename.

---

## Features

- 📂 Compare up to **100 PDFs** (50 old + 50 new) in one run
- 🔍 Smart text extraction: **pdfplumber → PyMuPDF → Tesseract OCR** fallback chain
- 📊 Similarity scoring via `difflib.SequenceMatcher`
- 🏷️ Status labels: `SAME`, `CHANGED`, `MISSING_NEW_FILE`, `MISSING_OLD_FILE`, `UNREADABLE`
- ⚠️ Flags duplicate identifiers and page-count differences
- 💾 Export results as **Excel (.xlsx)** or **CSV**

---

## File Naming Convention

Files are matched using the prefix before the **first underscore (`_`)**.

```
Old folder:           New folder:
001_invoice_old.pdf   001_invoice_new.pdf
002_report_old.pdf    002_report_v2.pdf
003_policy_old.pdf    (missing)
```

Resulting pairs:
| Identifier | Old File | New File |
|---|---|---|
| 001 | 001_invoice_old.pdf | 001_invoice_new.pdf |
| 002 | 002_report_old.pdf | 002_report_v2.pdf |
| 003 | 003_policy_old.pdf | — (MISSING_NEW_FILE) |

---

## Installation

### Prerequisites

- Python 3.9+
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) installed and on your PATH (only required for scanned PDFs)

### Install

```bash
cd pdf-bulk-comparator
pip install -r requirements.txt
```

---

## Usage

```bash
streamlit run streamlit_app.py
```

1. Enter the **Old PDFs Folder** path in the UI.
2. Enter the **New PDFs Folder** path.
3. Click **⚡ Compare PDFs**.
4. Review the results table.
5. Download the report as **Excel** or **CSV**.

---

## Project Structure

```
pdf-bulk-comparator/
├── streamlit_app.py          # Main Streamlit UI
├── requirements.txt
├── README.md
├── engine/
│   ├── pdf_reader.py         # Text extraction + OCR fallback
│   ├── matcher.py            # Identifier-based file pairing
│   └── comparator.py        # Similarity comparison logic
├── utils/
│   └── text_normalizer.py   # Lowercase, timestamp removal
├── reports/
│   └── report_generator.py  # DataFrame + Excel/CSV export
└── sample_data/
    ├── old/                  # Place old PDFs here
    └── new/                  # Place new PDFs here
```

---

## Similarity Threshold

| Ratio | Status |
|---|---|
| ≥ 0.99 | **SAME** |
| < 0.99 | **CHANGED** |

---

## Edge Cases Handled

| Scenario | Status |
|---|---|
| File missing in new folder | `MISSING_NEW_FILE` |
| File missing in old folder | `MISSING_OLD_FILE` |
| Corrupted / unreadable PDF | `UNREADABLE` |
| Scanned / image-only PDF | Auto-OCR via Tesseract |
| Page count differs | Noted in the **Notes** column |
| Duplicate identifier prefix | Warning shown; first file used |
