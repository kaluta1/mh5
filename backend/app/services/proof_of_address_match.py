"""
Heuristic matching of user-declared residential address and name on a proof-of-address document.
No OCR — user copies text from the bill/statement into the submit payload.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional, Tuple


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def normalized_address_key(s: str) -> str:
    """Comparable form for lock checks (same normalization as matching)."""
    return _norm(s or "")


def name_on_document_matches_profile(
    profile_full_name: Optional[str], name_on_document: str
) -> bool:
    """True if tokens from profile name overlap enough with name_on_document."""
    fn = _norm(profile_full_name or "")
    doc = _norm(name_on_document)
    if len(doc) < 2:
        return False
    if not fn:
        return len(doc) >= 3
    ftokens = {t for t in fn.split() if len(t) > 1}
    dtokens = {t for t in doc.split() if len(t) > 1}
    if not dtokens:
        return False
    if not ftokens:
        return doc in fn or fn in doc
    overlap = len(ftokens & dtokens)
    needed = max(1, min(len(ftokens), (len(ftokens) + 1) // 2))
    return overlap >= needed


def address_text_matches_locked(locked_address: str, address_as_on_document: str) -> bool:
    """
    True if enough significant tokens from the locked residential address appear
    in the text the user copied from the document.
    """
    L = _norm(locked_address)
    D = _norm(address_as_on_document)
    if not L or not D or len(D) < 8:
        return False
    ltok = [t for t in L.split() if len(t) > 2]
    if not ltok:
        return L in D or D in L
    hits = sum(1 for t in ltok if t in D)
    need = max(2, min(len(ltok), (len(ltok) + 1) // 2))
    return hits >= need


def evaluate_proof_of_address(
    *,
    locked_residential_address: str,
    profile_full_name: Optional[str],
    name_on_document: str,
    address_as_shown_on_document: str,
) -> Tuple[bool, str]:
    """
    Returns (ok, reason). reason is empty when ok, else a short machine-readable hint.
    """
    if not name_on_document_matches_profile(profile_full_name, name_on_document):
        return False, "name_mismatch"
    if not address_text_matches_locked(locked_residential_address, address_as_shown_on_document):
        return False, "address_mismatch"
    return True, ""
