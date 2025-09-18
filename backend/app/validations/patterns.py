from __future__ import annotations

# Bank-specific cheque number validation patterns
# For now we use simple digit-length regex per bank. This can be extended per product line.
CHEQUE_NUMBER_PATTERNS = {
    "QNB": {"regex": r"^\d{8,12}$"},
    "FABMISR": {"regex": r"^\d{8,12}$"},
}
