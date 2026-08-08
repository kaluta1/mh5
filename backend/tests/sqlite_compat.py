"""
Make PostgreSQL-specific SQLAlchemy types work with in-memory SQLite tests.

Import this module before Base.metadata.create_all().
"""
from __future__ import annotations

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.schema import MetaData


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_element, compiler, **_kw):  # noqa: ARG001
    return "JSON"


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(_element, compiler, **_kw):  # noqa: ARG001
    return "JSON"


def patch_metadata_for_sqlite(metadata: MetaData) -> None:
    """Replace JSONB/ARRAY column types with JSON so SQLite DDL always succeeds."""
    for table in metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()
            elif isinstance(column.type, ARRAY):
                column.type = JSON()
