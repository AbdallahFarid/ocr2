from __future__ import annotations

# Bank-specific cheque number validation patterns
# For now we use simple digit-length regex per bank. This can be extended per product line.
CHEQUE_NUMBER_PATTERNS = {
    "QNB": {"regex": r"^\d{8,12}$"},
    "FABMISR": {"regex": r"^\d{8,12}$"},
    "BANQUE_MISR": {"regex": r"^\d{6,}$"},
    "CIB": {"regex": r"^\d{12}$"},
    "AAIB": {"regex": r"^\d{9,10}$"},
    "NBE": {"regex": r"^\d{14}$"},
}
