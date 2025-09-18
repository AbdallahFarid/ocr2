from __future__ import annotations

import unicodedata
import re
from typing import Optional

try:
    import arabic_reshaper  # type: ignore
    from bidi.algorithm import get_display  # type: ignore
except Exception:
    arabic_reshaper = None  # type: ignore
    get_display = None  # type: ignore

# Basic Arabic normalization and digit normalization helpers
# These are intentionally lightweight. We can expand with diacritics removal
# and presentation form handling as needed.

_ARABIC_INDIC_DIGITS = {
    ord("٠"): "0",
    ord("١"): "1",
    ord("٢"): "2",
    ord("٣"): "3",
    ord("٤"): "4",
    ord("٥"): "5",
    ord("٦"): "6",
    ord("٧"): "7",
    ord("٨"): "8",
    ord("٩"): "9",
}


def normalize_digits(text: str) -> str:
    if not text:
        return text
    return text.translate(_ARABIC_INDIC_DIGITS)


def strip_diacritics(text: str) -> str:
    # Remove combining marks
    return "".join(ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn")


def _normalize_arabic_letters(text: str) -> str:
    """Normalize Arabic letters to canonical forms (e.g., alef variants).

    This reduces OCR variability across similar glyphs.
    """
    if not text:
        return text
    s = text
    # Normalize Alef variants and other common forms
    s = s.replace("إ", "ا").replace("أ", "ا").replace("آ", "ا")
    s = s.replace("ٱ", "ا").replace("ى", "ي").replace("ئ", "ي").replace("ؤ", "و")
    # Heh goal vs Teh Marbuta normalization: keep ة as is for names; avoid converting ه/ة
    return s


def fix_arabic_text(text: str, *, for_display: bool = True) -> str:
    if not text:
        return text
    # Unicode normalization
    s = unicodedata.normalize("NFKC", text)
    # Normalize specific Arabic letters
    s = _normalize_arabic_letters(s)
    # Normalize digits
    s = normalize_digits(s)
    # Optionally remove tatweel and diacritics
    s = s.replace("ـ", "")  # tatweel
    s = strip_diacritics(s)
    # Remove zero-width and bidi control characters that can break joining
    ZW_CHARS = {
        "\u200B",  # ZERO WIDTH SPACE
        "\u200C",  # ZERO WIDTH NON-JOINER
        "\u200E",  # LEFT-TO-RIGHT MARK
        "\u200F",  # RIGHT-TO-LEFT MARK
        "\u202A",  # LRE
        "\u202B",  # RLE
        "\u202C",  # PDF
        "\u202D",  # LRO
        "\u202E",  # RLO
        "\u2066",  # LRI
        "\u2067",  # RLI
        "\u2068",  # FSI
        "\u2069",  # PDI
    }
    for ch in ZW_CHARS:
        s = s.replace(ch, "")
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    if for_display and arabic_reshaper and get_display:
        try:
            # Reshape characters into presentation forms and apply bidi algorithm
            reshaped = arabic_reshaper.reshape(s)
            visual = get_display(reshaped)
            return visual
        except Exception:
            return s
    return s
