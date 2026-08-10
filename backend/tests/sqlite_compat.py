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


def _is_jsonb(type_obj) -> bool:
    return isinstance(type_obj, JSONB) or type(type_obj).__name__ == "JSONB"


def _is_array(type_obj) -> bool:
    return isinstance(type_obj, ARRAY) or type(type_obj).__name__ == "ARRAY"


def patch_metadata_for_sqlite(metadata: MetaData) -> None:
    """Replace JSONB/ARRAY column types with JSON so SQLite DDL always succeeds."""
    for table in metadata.tables.values():
        for column in table.columns:
            if _is_jsonb(column.type):
                column.type = JSON()
            elif _is_array(column.type):
                column.type = JSON()
