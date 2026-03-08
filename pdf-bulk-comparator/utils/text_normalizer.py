"""
utils/text_normalizer.py
Normalize extracted PDF text for fair comparison.

Handles:
  - Table layouts vs plain text (e.g., "Name | Age" vs "Name: Age")
  - Punctuation and formatting differences
  - Whitespace normalization
  - Token-based comparison for layout independence
"""

import hashlib
import re
import string
from typing import List, Tuple


# Regex patterns for common timestamp / date formats to strip out
_TIMESTAMP_PATTERNS = [
    # HH:MM:SS or HH:MM
    re.compile(r"\b\d{1,2}:\d{2}(:\d{2})?\b"),
    # ISO date  YYYY-MM-DD
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    # dd/mm/yyyy or mm/dd/yyyy
    re.compile(r"\b\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}\b"),
    # Month dd, yyyy  e.g. "March 7, 2026"
    re.compile(
        r"\b(?:january|february|march|april|may|june|july|august|september|"
        r"october|november|december)\s+\d{1,2},?\s+\d{4}\b",
        re.IGNORECASE,
    ),
    # Unix timestamps (10-digit numbers)
    re.compile(r"\b\d{10}\b"),
]

# Characters to remove (table separators, punctuation)
_TABLE_SEPARATORS = re.compile(r"[|│┃┆┇┊┋║\-\+\=\_]+")
_PUNCTUATION_PATTERN = re.compile(r"[" + re.escape(string.punctuation) + r"]+")


def normalize(text: str) -> str:
    """
    Normalise PDF text for comparison:
      - lowercase
      - remove timestamps / dates
      - remove table separators (|, -, etc.)
      - remove punctuation
      - collapse whitespace
    
    This handles layout differences like:
      "Name | Age"  vs  "Name: Age"  →  "name age"
    """
    if not text:
        return ""

    # Convert to lowercase
    text = text.lower()

    # Remove timestamps/dates
    for pattern in _TIMESTAMP_PATTERNS:
        text = pattern.sub(" ", text)

    # Remove table separators
    text = _TABLE_SEPARATORS.sub(" ", text)
    
    # Remove punctuation (but keep numbers and letters)
    text = _PUNCTUATION_PATTERN.sub(" ", text)

    # Collapse all whitespace (spaces, tabs, newlines) to a single space
    text = re.sub(r"\s+", " ", text).strip()

    return text


def normalize_tokens(text: str) -> List[str]:
    """
    Normalize text and return sorted tokens.
    
    This removes all layout dependencies by:
      1. Normalizing the text
      2. Splitting into tokens
      3. Sorting tokens alphabetically
    
    Example:
      "Name | Age\nJohn | 25"  →  ['25', 'age', 'john', 'name']
      "Name: John, Age: 25"    →  ['25', 'age', 'john', 'name']
    """
    normalized = normalize(text)
    if not normalized:
        return []
    
    tokens = normalized.split()
    return sorted(tokens)


def tokens_to_fingerprint(tokens: List[str]) -> str:
    """
    Convert sorted tokens to a fingerprint hash.
    Used for fast comparison of normalized content.
    """
    if not tokens:
        return ""
    content = " ".join(tokens)
    return hashlib.md5(content.encode('utf-8')).hexdigest()


def text_to_fingerprint(text: str) -> str:
    """
    Convert raw text to a normalized fingerprint hash.
    Combines normalization + tokenization + hashing.
    """
    tokens = normalize_tokens(text)
    return tokens_to_fingerprint(tokens)


def compare_tokens(tokens_a: List[str], tokens_b: List[str]) -> float:
    """
    Compare two sorted token lists and return similarity ratio.
    Uses set-based comparison for speed.
    """
    if not tokens_a and not tokens_b:
        return 1.0
    if not tokens_a or not tokens_b:
        return 0.0
    
    set_a = set(tokens_a)
    set_b = set(tokens_b)
    
    # Jaccard similarity
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    
    if union == 0:
        return 1.0
    
    return intersection / union


def normalize_table_text(table_data: List[List[str]]) -> str:
    """
    Convert table data (2D list) to flat normalized text.
    
    Example:
      [["Name", "Age"], ["John", "25"]]  →  "name age john 25"
    """
    if not table_data:
        return ""
    
    # Flatten table to single string
    flat_text = " ".join(
        " ".join(str(cell) for cell in row if cell)
        for row in table_data
        if row
    )
    
    return normalize(flat_text)
