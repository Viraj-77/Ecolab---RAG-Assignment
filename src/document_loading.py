from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pypdf

from src.text_cleaning import clean_text


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "Data"
DATA_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------
# Supported document types
# ---------------------------------------------------------------------
SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md"}

MAX_FILE_SIZE_MB = 100


# ---------------------------------------------------------------------
# Custom error
# ---------------------------------------------------------------------
class DocumentLoadingError(RuntimeError):
    """Raised when a document cannot be loaded."""


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def _file_size_mb(path: Path) -> float:
    return path.stat().st_size / (1024 * 1024)


def _is_supported_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS


def _validate_file(path: Path) -> None:
    if not path.exists():
        raise DocumentLoadingError(f"File does not exist: {path}")

    if not path.is_file():
        raise DocumentLoadingError(f"Path is not a file: {path}")

    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise DocumentLoadingError(f"Unsupported file type: {path.suffix}")

    size_mb = _file_size_mb(path)

    if size_mb > MAX_FILE_SIZE_MB:
        raise DocumentLoadingError(
            f"File too large: {path.name} is {size_mb:.2f} MB. "
            f"Maximum allowed size is {MAX_FILE_SIZE_MB} MB."
        )


def _make_document(
    source: str,
    page: int,
    text: str,
    file_type: str,
) -> dict[str, Any]:
    return {
        "source": source,
        "page": page,
        "text": text,
        "file_type": file_type,
    }


# ---------------------------------------------------------------------
# PDF loading
# ---------------------------------------------------------------------
def read_pdf_pages(path: Path) -> list[dict[str, Any]]:
    """
    Extract text from a PDF page by page.

    Page-level extraction is important because the final RAG answer can cite
    source file + page number.
    """
    _validate_file(path)

    try:
        reader = pypdf.PdfReader(str(path))
    except Exception as exc:
        raise DocumentLoadingError(f"Could not open PDF: {path.name}") from exc

    pages: list[dict[str, Any]] = []

    for page_no, page in enumerate(reader.pages, start=1):
        try:
            raw_text = page.extract_text() or ""
            text = clean_text(raw_text)

            if text:
                pages.append(
                    _make_document(
                        source=path.name,
                        page=page_no,
                        text=text,
                        file_type="pdf",
                    )
                )

        except Exception as exc:
            logger.warning(
                "Failed to extract page %s from %s: %s",
                page_no,
                path.name,
                exc,
            )

    if not pages:
        logger.warning(
            "No extractable text found in PDF: %s. "
            "If this PDF is scanned/image-based, OCR is required.",
            path.name,
        )

    return pages


# ---------------------------------------------------------------------
# Text / Markdown loading
# ---------------------------------------------------------------------
def read_text_file(path: Path) -> list[dict[str, Any]]:
    """
    Read .txt or .md files.

    This is useful for:
    - glossary.md
    - acronym expansions
    - manually added domain notes
    - extracted text from images/tables
    """
    _validate_file(path)

    try:
        raw_text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:
        raise DocumentLoadingError(f"Could not read text file: {path.name}") from exc

    text = clean_text(raw_text)

    if not text:
        return []

    return [
        _make_document(
            source=path.name,
            page=1,
            text=text,
            file_type=path.suffix.lower().lstrip("."),
        )
    ]


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------
def load_document(path: Path) -> list[dict[str, Any]]:
    """
    Load one supported document.
    """
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return read_pdf_pages(path)

    if suffix in {".txt", ".md"}:
        return read_text_file(path)

    raise DocumentLoadingError(f"Unsupported file type: {suffix}")


def load_all_documents(data_dir: Path = DATA_DIR) -> list[dict[str, Any]]:
    """
    Load all supported files from Data/.

    Returns a list of page/text records:
    {
        "source": file name,
        "page": page number,
        "text": cleaned text,
        "file_type": pdf/txt/md
    }
    """
    data_dir.mkdir(exist_ok=True)

    documents: list[dict[str, Any]] = []

    supported_files = [
        path for path in sorted(data_dir.iterdir())
        if _is_supported_file(path)
    ]

    if not supported_files:
        logger.warning("No supported documents found in %s", data_dir)
        return []

    for path in supported_files:
        try:
            loaded_pages = load_document(path)
            documents.extend(loaded_pages)

            logger.info(
                "Loaded %s | type=%s | records=%s | size=%.2f MB",
                path.name,
                path.suffix.lower(),
                len(loaded_pages),
                _file_size_mb(path),
            )

            print(f"Loaded {path.name}: {len(loaded_pages)} text records")

        except Exception as exc:
            logger.exception("Skipping document due to loading error: %s", path.name)
            print(f"Skipping {path.name}: {exc}")

    return documents