from __future__ import annotations

import re
import unicodedata


# ---------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------
ZERO_WIDTH_CHARS = [
    "\u200b",  # zero-width space
    "\u200c",
    "\u200d",
    "\ufeff",
]

BULLET_CHARS = {
    "•": "- ",
    "●": "- ",
    "▪": "- ",
    "◦": "- ",
    "–": "- ",
}

COMMON_PDF_ARTIFACT_PATTERNS = [
    r"Water Neutrality\s*-\s*Standardization of definition and approach for industry\s*\d*",
]


# ---------------------------------------------------------------------
# Cleaning helpers
# ---------------------------------------------------------------------
def _normalize_unicode(text: str) -> str:
    """
    Normalize Unicode so PDF text behaves consistently.
    """
    text = unicodedata.normalize("NFKC", text)

    for char in ZERO_WIDTH_CHARS:
        text = text.replace(char, "")

    return text


def _normalize_bullets(text: str) -> str:
    """
    Convert different bullet symbols into a simple markdown-style bullet.
    """
    for old, new in BULLET_CHARS.items():
        text = text.replace(old, f"\n{new}")

    return text


def _remove_pdf_artifacts(text: str) -> str:
    """
    Remove repeated headers/footers that appear on many pages.
    Keep this conservative to avoid deleting useful technical content.
    """
    for pattern in COMMON_PDF_ARTIFACT_PATTERNS:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)

    return text


def _fix_hyphenated_line_breaks(text: str) -> str:
    """
    Join words broken by line wrapping.

    Example:
        treat-
        ment

    becomes:
        treatment
    """
    return re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)


def _normalize_newlines(text: str) -> str:
    """
    Preserve paragraph breaks but remove unnecessary line breaks inside paragraphs.
    """
    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")

    # Convert tabs and multiple spaces to single spaces.
    text = re.sub(r"[ \t]+", " ", text)

    # Remove spaces around newlines.
    text = re.sub(r" *\n *", "\n", text)

    # Convert single line breaks into spaces.
    # Keep paragraph breaks as double newlines.
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)

    # Collapse too many paragraph breaks.
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text


def _normalize_spacing(text: str) -> str:
    """
    Final whitespace cleanup.
    """
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r" +([,.;:!?])", r"\1", text)
    text = re.sub(r"([({\[])\s+", r"\1", text)
    text = re.sub(r"\s+([)}\]])", r"\1", text)

    return text.strip()


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------
def clean_text(text: str) -> str:
    """
    Clean PDF/text content before chunking.

    This function is intentionally conservative:
    - It removes PDF noise.
    - It keeps technical terms, units, formulas, acronyms, and numbers.
    - It preserves paragraph boundaries for better semantic chunking.
    """

    if not text:
        return ""

    text = str(text)

    # Remove null/control-like characters that often appear in PDFs.
    text = text.replace("\x00", " ")

    text = _normalize_unicode(text)
    text = _remove_pdf_artifacts(text)
    text = _fix_hyphenated_line_breaks(text)
    text = _normalize_bullets(text)
    text = _normalize_newlines(text)
    text = _normalize_spacing(text)

    return text