#!/usr/bin/env python3
"""Emit a deterministic, non-mutating inventory of registered FastAPI routes."""
from __future__ import annotations

import inspect
import io
import json
import os
import sys
from contextlib import redirect_stdout
from collections import Counter
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Prevent startup schedulers and force non-production import validation. No DB is opened.
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("USE_CELERY", "true")
os.environ.setdefault("SECRET_KEY", "route-audit-secret-key-minimum-32-characters")
os.environ.setdefault("MASTER_ENCRYPTION_KEY", "route-audit-master-encryption-key")
os.environ.setdefault("ENCRYPTION_KEY_DERIVATION_SALT", "route-audit-salt")

from fastapi.routing import APIRoute  # noqa: E402
with redirect_stdout(io.StringIO()):
    from main import app  # noqa: E402


def _dependency_names(route: APIRoute) -> list[str]:
    found: set[str] = set()

    def visit(node):
        call = getattr(node, "call", None)
        if call is not None:
            found.add(getattr(call, "__name__", call.__class__.__name__))
        for child in getattr(node, "dependencies", ()):
            visit(child)

    visit(route.dependant)
    found.discard(getattr(route.endpoint, "__name__", ""))
    return sorted(found)


def main() -> int:
    rows = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        module = inspect.getmodule(route.endpoint)
        rows.append(
            {
                "path": route.path,
                "methods": sorted(route.methods or ()),
                "name": route.name,
                "module": getattr(module, "__name__", "unknown"),
                "dependencies": _dependency_names(route),
            }
        )
    rows.sort(key=lambda item: (item["path"], item["methods"], item["name"]))
    signatures = Counter(
        (method, row["path"])
        for row in rows
        for method in row["methods"]
        if method not in {"HEAD", "OPTIONS"}
    )
    duplicates = [
        {"method": method, "path": path, "registrations": count}
        for (method, path), count in sorted(signatures.items())
        if count > 1
    ]
    suspicious_get_terms = (
        "approve", "reject", "delete", "create", "update", "grant", "pay", "refund",
        "withdraw", "activate", "deactivate", "suspend", "migrate", "assign", "reset",
    )
    suspicious_gets = [
        row
        for row in rows
        if "GET" in row["methods"]
        and any(term in f'{row["path"]} {row["name"]}'.lower() for term in suspicious_get_terms)
    ]
    unauthenticated_non_get = [
        row
        for row in rows
        if any(method not in {"GET", "HEAD", "OPTIONS"} for method in row["methods"])
        and not any(
            name.startswith("get_current_") or name in {"require_permission", "get_optional_user"}
            for name in row["dependencies"]
        )
    ]
    payload = {
        "environment": os.getenv("ENVIRONMENT", ""),
        "route_count": len(rows),
        "duplicates": duplicates,
        "suspicious_gets": suspicious_gets,
        "unauthenticated_non_get_review": unauthenticated_non_get,
        "routes": rows,
    }
    if "--summary" in sys.argv:
        payload.pop("routes")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
