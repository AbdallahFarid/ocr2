from __future__ import annotations

from enum import Enum


class ErrorCode(str, Enum):
    OK = "OK"

    # Date
    DATE_EMPTY = "DATE_EMPTY"
    DATE_RANGE = "DATE_RANGE"
    DATE_INVALID = "DATE_INVALID"

    # Amount
    AMOUNT_EMPTY = "AMOUNT_EMPTY"
    AMOUNT_NONPOS = "AMOUNT_NONPOS"
    AMOUNT_RANGE = "AMOUNT_RANGE"

    # Cheque number
    CHEQUE_EMPTY = "CHEQUE_EMPTY"
    CHEQUE_PATTERN = "CHEQUE_PATTERN"

    # Payee
    PAYEE_EMPTY = "PAYEE_EMPTY"
    PAYEE_TOO_SHORT = "PAYEE_TOO_SHORT"
    PAYEE_NOT_IN_MASTER = "PAYEE_NOT_IN_MASTER"

    # Currency
    CURRENCY_INVALID = "CURRENCY_INVALID"
