"""VerificationProvider storage contract (always-on; the PostgreSQL proof lives in
tests/integration/test_kyc_provider_enum_postgres.py).

KYCVerification.provider uses the default SQLEnum, which stores enum member NAMES.
Every database label must therefore be a member name; 'KALUTA' is the one canonical
Kaluta label (migration a8b9c0d1e2f3), never the lowercase value 'kaluta'.
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest
from sqlalchemy.dialects import postgresql

from app.models.kyc import KYCVerification, VerificationProvider

pytestmark = pytest.mark.unit

BACKEND = Path(__file__).resolve().parents[2]
VERSIONS = BACKEND / "migrations" / "versions"
MIGRATION = VERSIONS / "a8b9c0d1e2f3_kyc_provider_kaluta_canonical_label.py"


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_column_stores_member_names():
    col_type = KYCVerification.__table__.c.provider.type
    assert col_type.enums == [m.name for m in VerificationProvider]
    bind = col_type.bind_processor(postgresql.dialect())
    written = {m: (bind(m) if bind else m.name) for m in VerificationProvider}
    assert written[VerificationProvider.KALUTA] == "KALUTA"
    assert all(v == m.name for m, v in written.items())


def test_python_enum_is_unchanged():
    assert [(m.name, m.value) for m in VerificationProvider] == [
        ("KALUTA", "kaluta"), ("SHUFTI_PRO", "shufti_pro"), ("JUMIO", "jumio"), ("ONFIDO", "onfido"), ("MANUAL", "manual")]


def test_migration_chains_after_the_shafi_head_and_is_the_only_head():
    mig = _load(MIGRATION)
    assert (mig.revision, mig.down_revision) == ("a8b9c0d1e2f3", "f7a8b9c0d1e2")
    children = [p.name for p in VERSIONS.glob("*.py")
                if re.search(r"down_revision\s*=\s*['\"]f7a8b9c0d1e2['\"]", p.read_text(encoding="utf-8"))]
    assert children == [MIGRATION.name]


def test_migration_renames_in_place_and_never_drops_or_rebuilds():
    src = MIGRATION.read_text(encoding="utf-8")
    code = src.split('"""', 2)[2]
    assert "RENAME VALUE 'kaluta' TO 'KALUTA'" in code
    assert "ADD VALUE 'KALUTA'" in code
    for forbidden in ("DROP ", "CREATE TYPE", "ALTER COLUMN", "DELETE ", "USING "):
        assert forbidden not in code.upper()
    assert "ADD VALUE 'kaluta'" not in code and "ADD VALUE IF NOT EXISTS 'kaluta'" not in code


def test_historical_migration_is_untouched():
    src = (VERSIONS / "s3t4u5v6w7x8_kaluta_kyc_provider.py").read_text(encoding="utf-8")
    assert "ADD VALUE IF NOT EXISTS 'kaluta'" in src  # left exactly as deployed; a8b9c0d1e2f3 converges it


def test_ops_scripts_no_longer_reintroduce_the_lowercase_label():
    ensure = (BACKEND / "scripts" / "ensure_kyc_payment_schema.py").read_text(encoding="utf-8")
    reconcile = (BACKEND / "scripts" / "reconcile_production_schema.py").read_text(encoding="utf-8")
    assert '"verificationprovider": ["KALUTA"]' in ensure and '["kaluta"]' not in ensure
    assert "ADD VALUE IF NOT EXISTS 'kaluta'" not in reconcile and "ADD VALUE 'KALUTA'" in reconcile
