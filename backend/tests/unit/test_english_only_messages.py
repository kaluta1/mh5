"""The site is English-only: messages the API returns to members and administrators are English.

A source check over every endpoint (error details and response messages) plus API checks of KYC
messages. Logs, docstrings, localised email dictionaries and data (place names, moderation word
lists) are out of scope and not checked here."""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from tests.unit.test_age_gate_registration import auth
from tests.unit.test_kyc_initiation_dispatch import adult, no_real_network  # noqa: F401

pytestmark = pytest.mark.unit

ENDPOINTS = Path(__file__).resolve().parents[2] / "app" / "api" / "api_v1" / "endpoints"
FRENCH = re.compile(r"[éèêëàâçùûüôîïœ]|\b(vous|votre|veuillez|erreur|aucun|aucune|réussi|échec|non trouvé|"
                    r"avec succès|lors de|impossible de|introuvable|invalide|requis|requise|inactif|"
                    r"utilisateur|cotisation|concours)\b", re.I)
APP = ENDPOINTS.parents[2]
# Messages also come from the dependencies, the CRUD layer (ValueError texts shown as 400s) and the
# services. The email dictionaries hold the other languages on purpose and are not checked.
MORE = [APP / "api" / "deps.py", *sorted((APP / "crud").glob("*.py")),
        *[p for p in sorted((APP / "services").glob("*.py"))
          if p.name not in ("email_templates.py", "email_event_texts.py")]]


def _text(node: ast.AST) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value for v in node.values if isinstance(v, ast.Constant) and isinstance(v.value, str))
    return ""


def _messages(tree: ast.AST):
    """(line, text) of every error detail and response message literal, and of ValueError texts."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg in ("detail", "message"):
                    yield node.lineno, _text(kw.value)
            if isinstance(node.func, ast.Name) and node.func.id == "ValueError" and node.args:
                yield node.lineno, _text(node.args[0])
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and key.value in ("message", "detail", "error"):
                    yield node.lineno, _text(value)


def test_no_endpoint_returns_a_french_message():
    french = []
    for path in sorted(ENDPOINTS.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        french += [f"{path.name}:{line}: {text[:80]}" for line, text in _messages(tree) if text and FRENCH.search(text)]
    assert french == []


def test_dependencies_crud_and_services_return_no_french_message():
    french = []
    for path in MORE:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        french += [f"{path.name}:{line}: {text[:80]}" for line, text in _messages(tree) if text and FRENCH.search(text)]
    assert french == []


def test_kyc_status_without_a_verification_answers_in_english(client, db, no_real_network):  # noqa: F811
    user = adult(db)
    body = client.get("/api/v1/kyc/status-detailed", headers=auth(user)).json()
    text = str(body)
    assert not FRENCH.search(text), text
