"""Marketplace seller registration and verification: new tables only, plus a permission held by nobody.

Revision ID: f3b5d7e9a1c2
Revises: e2a4c6e8f0b1
Create Date: 2026-10-31

Additive: no existing table, row or constraint is changed. Enforcement stays off until
MARKETPLACE_SELLER_VERIFICATION_ENABLED is set. The jurisdiction rule catalogue is NOT seeded here; an
administrator adds it (legal rules as DRAFT) from the admin panel. Downgrade refuses while any seller
application or profile exists, so no seller record is ever dropped by accident.
"""
import sqlalchemy as sa
from alembic import op


revision = "f3b5d7e9a1c2"
down_revision = "e2a4c6e8f0b1"
branch_labels = None
depends_on = None

_STATUSES = ("'DRAFT', 'SUBMITTED', 'CHECKS_IN_PROGRESS', 'ACTION_REQUIRED', 'MANUAL_REVIEW_REQUIRED', 'APPROVED', "
             "'REJECTED', 'RESTRICTED', 'REVERIFICATION_REQUIRED', 'SUPERSEDED'")


def _base():
    return [sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now())]


def _users(name, nullable=True):
    return sa.Column(name, sa.Integer, sa.ForeignKey("users.id"), nullable=nullable)


def upgrade() -> None:
    op.create_table(
        "seller_jurisdiction_rules", *_base(),
        sa.Column("rule_code", sa.String(80), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("jurisdiction", sa.String(10), nullable=False),
        sa.Column("subdivision", sa.String(20)),
        sa.Column("scope", sa.String(40), nullable=False),
        sa.Column("rule_kind", sa.String(10), nullable=False),
        sa.Column("seller_categories", sa.JSON), sa.Column("business_structures", sa.JSON),
        sa.Column("product_categories", sa.JSON),
        sa.Column("applies_by_customer_market", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("requirement", sa.String(60), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("official_source_url", sa.String(500)),
        sa.Column("effective_from", sa.Date), sa.Column("last_reviewed_on", sa.Date),
        sa.Column("status", sa.String(10), nullable=False, server_default="DRAFT"),
        _users("activated_by_user_id"), sa.Column("activated_at", sa.DateTime), sa.Column("review_note", sa.Text),
        sa.CheckConstraint("rule_kind IN ('LEGAL', 'PLATFORM')", name="ck_seller_rule_kind"),
        sa.CheckConstraint("status IN ('DRAFT', 'ACTIVE', 'RETIRED')", name="ck_seller_rule_status"),
        sa.UniqueConstraint("rule_code", "version", name="uq_seller_rule_code_version"),
    )
    op.create_index("ix_seller_jurisdiction_rules_jurisdiction", "seller_jurisdiction_rules", ["jurisdiction"])

    op.create_table(
        "seller_profiles", *_base(),
        _users("user_id", nullable=False),
        sa.Column("seller_category", sa.String(20)),
        sa.Column("status", sa.String(30), nullable=False, server_default="NONE"),
        sa.Column("public_label", sa.String(80)), sa.Column("public_trading_name", sa.String(160)),
        sa.Column("approved_application_id", sa.Integer), sa.Column("approved_at", sa.DateTime),
        sa.Column("restricted_at", sa.DateTime), sa.Column("reverify_due_at", sa.DateTime),
        sa.Column("beneficiary_fingerprint", sa.String(64)),
        sa.CheckConstraint(f"status IN ('NONE', {_STATUSES})", name="ck_seller_profile_status"),
        sa.UniqueConstraint("user_id", name="uq_seller_profiles_user_id"),
    )

    op.create_table(
        "seller_applications", *_base(),
        _users("user_id", nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="DRAFT"),
        sa.Column("seller_category", sa.String(20), nullable=False),
        sa.Column("business_structure", sa.String(30)),
        sa.Column("legal_name", sa.String(200)), sa.Column("trading_name", sa.String(160)),
        sa.Column("residence_country", sa.String(2)), sa.Column("establishment_country", sa.String(2)),
        sa.Column("establishment_subdivision", sa.String(20)), sa.Column("customer_markets", sa.JSON),
        sa.Column("business_address", sa.Text), sa.Column("contact_phone", sa.String(30)),
        sa.Column("product_categories", sa.JSON), sa.Column("products_description", sa.Text),
        sa.Column("commercial_indicators", sa.JSON),
        sa.Column("registration_authority", sa.String(160)), sa.Column("registration_number", sa.String(60)),
        sa.Column("exemption_basis", sa.Text), sa.Column("tax_registered", sa.Boolean),
        sa.Column("tax_identifier_encrypted", sa.Text), sa.Column("tax_identifier_last4", sa.String(4)),
        sa.Column("licences", sa.JSON), sa.Column("representative", sa.JSON), sa.Column("ownership", sa.JSON),
        sa.Column("declaration_version", sa.String(40)), sa.Column("declaration_accepted_at", sa.DateTime),
        sa.Column("applicable_rules", sa.JSON), sa.Column("review_reasons", sa.JSON),
        sa.Column("correction_request", sa.Text), sa.Column("appeal_text", sa.Text),
        sa.Column("submitted_at", sa.DateTime), sa.Column("decided_at", sa.DateTime),
        _users("decided_by_user_id"), sa.Column("decision_reason", sa.Text),
        sa.Column("supersedes_application_id", sa.Integer),
        sa.CheckConstraint(f"status IN ({_STATUSES})", name="ck_seller_application_status"),
        sa.CheckConstraint("seller_category IN ('PRIVATE', 'SOLE_TRADER', 'ORGANISATION')",
                           name="ck_seller_application_category"),
    )
    op.create_index("ix_seller_applications_user_id", "seller_applications", ["user_id"])
    op.create_index("ix_seller_applications_user_status", "seller_applications", ["user_id", "status"])

    op.create_table(
        "seller_application_events", *_base(),
        sa.Column("application_id", sa.Integer, sa.ForeignKey("seller_applications.id"), nullable=False),
        sa.Column("from_status", sa.String(30)), sa.Column("to_status", sa.String(30), nullable=False),
        _users("actor_user_id"), sa.Column("actor_role", sa.String(20), nullable=False),
        sa.Column("reason", sa.Text), sa.Column("seller_message", sa.Text), sa.Column("changes", sa.JSON),
    )
    op.create_index("ix_seller_application_events_application_id", "seller_application_events", ["application_id"])

    op.create_table(
        "seller_verification_checks", *_base(),
        sa.Column("application_id", sa.Integer, sa.ForeignKey("seller_applications.id"), nullable=False),
        sa.Column("check_type", sa.String(30), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("status", sa.String(15), nullable=False, server_default="PENDING"),
        sa.Column("external_reference", sa.String(160)),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("result_code", sa.String(60)), sa.Column("last_error", sa.String(200)),
        sa.Column("checked_at", sa.DateTime),
        sa.CheckConstraint("status IN ('PENDING', 'PASSED', 'FAILED', 'UNAVAILABLE', 'MANUAL')",
                           name="ck_seller_check_status"),
        sa.UniqueConstraint("application_id", "check_type", name="uq_seller_check_application_type"),
    )
    op.create_index("ix_seller_verification_checks_application_id", "seller_verification_checks", ["application_id"])

    op.create_table(
        "seller_provider_events", *_base(),
        sa.Column("provider", sa.String(40), nullable=False), sa.Column("event_id", sa.String(160), nullable=False),
        sa.Column("check_id", sa.Integer, sa.ForeignKey("seller_verification_checks.id")),
        sa.Column("outcome", sa.String(15), nullable=False),
        sa.UniqueConstraint("provider", "event_id", name="uq_seller_provider_event"),
    )

    op.create_table(
        "seller_documents", *_base(),
        sa.Column("application_id", sa.Integer, sa.ForeignKey("seller_applications.id"), nullable=False),
        sa.Column("doc_type", sa.String(30), nullable=False),
        sa.Column("storage_key", sa.String(80), nullable=False, unique=True),
        sa.Column("file_name", sa.String(200), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("size", sa.BigInteger, nullable=False), sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("expires_on", sa.Date), _users("uploaded_by_user_id", nullable=False),
        sa.Column("erased_at", sa.DateTime),
    )
    op.create_index("ix_seller_documents_application_id", "seller_documents", ["application_id"])

    op.create_table(
        "seller_classification_reviews", *_base(),
        _users("user_id", nullable=False),
        sa.Column("trigger", sa.String(30), nullable=False),
        sa.Column("idempotency_key", sa.String(120), nullable=False),
        sa.Column("window_start", sa.DateTime, nullable=False), sa.Column("window_end", sa.DateTime, nullable=False),
        sa.Column("qualifying_sales_usd", sa.Numeric(15, 2), nullable=False),
        sa.Column("qualifying_order_count", sa.Integer, nullable=False),
        sa.Column("fx_rates_used", sa.JSON), sa.Column("detail", sa.JSON),
        sa.Column("status", sa.String(10), nullable=False, server_default="OPEN"),
        sa.Column("resolution", sa.String(40)), sa.Column("resolution_note", sa.Text),
        _users("resolved_by_user_id"), sa.Column("resolved_at", sa.DateTime),
        sa.CheckConstraint("status IN ('OPEN', 'RESOLVED')", name="ck_seller_classification_status"),
        sa.UniqueConstraint("idempotency_key", name="uq_seller_classification_key"),
    )
    op.create_index("ix_seller_classification_reviews_user_id", "seller_classification_reviews", ["user_id"])

    op.create_table(
        "seller_fx_rates", *_base(),
        sa.Column("currency", sa.String(10), nullable=False), sa.Column("as_of", sa.Date, nullable=False),
        sa.Column("usd_per_unit", sa.Numeric(20, 8), nullable=False), sa.Column("source", sa.String(200), nullable=False),
        sa.UniqueConstraint("currency", "as_of", name="uq_seller_fx_currency_date"),
    )

    # The permission exists but is held by nobody until an Admin grants it (Super Admins always have it).
    op.execute("""
        DO $$
        BEGIN
            IF to_regclass('public.permissions') IS NOT NULL THEN
                INSERT INTO permissions (name, description, category, created_at, updated_at)
                SELECT 'review_seller_verification',
                       'Review marketplace seller applications, documents and jurisdiction rules',
                       'admin', now(), now()
                WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE name = 'review_seller_verification');
            END IF;
        END $$""")


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM seller_applications) OR EXISTS (SELECT 1 FROM seller_profiles) THEN
                RAISE EXCEPTION 'Seller applications or profiles exist: export them before downgrading f3b5d7e9a1c2';
            END IF;
        END $$;
    """)
    for table in ("seller_fx_rates", "seller_classification_reviews", "seller_documents", "seller_provider_events",
                  "seller_verification_checks", "seller_application_events", "seller_applications", "seller_profiles",
                  "seller_jurisdiction_rules"):
        op.drop_table(table)
    op.execute("""
        DO $$
        BEGIN
            IF to_regclass('public.permissions') IS NOT NULL
               AND to_regclass('public.role_permissions') IS NOT NULL THEN
                DELETE FROM permissions p
                WHERE p.name = 'review_seller_verification'
                  AND NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.permission_id = p.id);
            END IF;
        END $$""")
