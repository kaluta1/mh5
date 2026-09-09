"""Prompt 10 release-gate regressions discovered by the combined route audit."""


def test_round_setup_mutation_is_not_public(client):
    response = client.post("/api/v1/rounds/ensure-january")
    assert response.status_code == 401


def test_round_setup_mutation_rejects_normal_user(client, auth_headers):
    response = client.post("/api/v1/rounds/ensure-january", headers=auth_headers)
    assert response.status_code == 403


def test_scheduler_inventory_is_admin_only(client, auth_headers):
    assert client.get("/api/v1/scheduler/tasks").status_code == 401
    assert client.get("/api/v1/scheduler/tasks", headers=auth_headers).status_code == 403


def test_scheduler_trigger_rejects_missing_or_wrong_secret(client):
    assert client.post("/api/v1/scheduler/run/monthly_rounds").status_code in {401, 500}
    assert (
        client.post(
            "/api/v1/scheduler/run/monthly_rounds",
            headers={"x-cron-secret": "not-the-secret"},
        ).status_code
        in {401, 500}
    )


def test_schema_diagnostics_are_not_public(client):
    assert client.get("/api/v1/health/db-schema").status_code == 401


def test_production_accounting_backfill_is_fail_closed(monkeypatch):
    import pytest
    from fastapi import HTTPException
    from app.api.api_v1.endpoints.admin import _block_production_accounting_maintenance

    monkeypatch.setenv("ENVIRONMENT", "production")
    with pytest.raises(HTTPException) as exc:
        _block_production_accounting_maintenance(dry_run=False)
    assert exc.value.status_code == 409
    _block_production_accounting_maintenance(dry_run=True)


def test_monthly_scheduler_alias_does_not_start_a_second_loop():
    from app.services.scheduler_manager import scheduler_manager

    assert "monthly-ops" in scheduler_manager._schedulers
    assert "monthly-round" not in scheduler_manager._schedulers
    assert "monthly-round" in scheduler_manager.list_tasks()


def test_registered_request_handlers_do_not_run_schema_ddl():
    from pathlib import Path

    endpoints = Path(__file__).parents[1] / "app" / "api" / "api_v1" / "endpoints"
    source = "\n".join(path.read_text(encoding="utf-8") for path in endpoints.glob("*.py"))
    assert "__table__.create(" not in source
    assert "ALTER TABLE" not in source
