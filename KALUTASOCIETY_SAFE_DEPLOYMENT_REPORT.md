# KalutaSociety Safe CLI Deployment Report

Date: 2026-09-10 (VPS UTC observation: 2026-09-09)  
Status: **BLOCKED BEFORE MIGRATION/CANDIDATE/CUTOVER**

No production database, schema, service, environment, route, or credential was changed. No provider action occurred.

## Mandatory-gate blocker

The verified runtime contradicts the supplied deployment premises in two independent ways:

1. Public Apache traffic for `kalutasociety.com` routes to a systemd backend on `127.0.0.1:8010` and a PM2/Next frontend on `127.0.0.1:3010`. It does not route to the running `kalutafoundation` Docker containers on ports 8001/3000.
2. The public systemd backend uses local PostgreSQL `kalutasociety_db`, not Neon and not `mh5`. Meanwhile the non-public `kalutafoundation_backend` container uses Neon `neondb`.

Because the instruction identifies the “current running backend”/Neon as the authoritative live source, but the domain actually serves a different backend/database, none of these datasets can safely be selected for production cutover without an owner decision. To preserve evidence, all three states were backed up separately and Neon was restored only to a uniquely named isolated staging database. No migration or cutover was attempted.

## Verified runtime

- VPS hostname: `kalutasociety`.
- Proxy: Apache; Nginx is not installed.
- Apache configuration: syntax valid.
- HTTP redirects to HTTPS for `kalutasociety.com` and `www.kalutasociety.com`.
- TLS certificate paths reference the matching Let's Encrypt domain.
- Public API/media/websocket upstream: `127.0.0.1:8010`.
- Public frontend upstream: `127.0.0.1:3010`.
- Public backend: `kalutasociety-backend.service`, one Uvicorn worker, healthy response, working directory `/root/kalutasociety/backend`.
- Public frontend: PM2-managed Next 14.2.35, working directory `/root/kalutasociety/frontend`.
- Non-public Docker stack: `kalutafoundation_backend`, `kalutafoundation_frontend`, `kalutafoundation_redis`, Compose project `kalutafoundation` under `/opt/projects/kalutafoundation/app/deploy/hostinger`.
- Additional standalone Redis: `kalutasociety_redis`, bound to loopback 6379.

## Database identities

### Public systemd backend database

- Location: VPS PostgreSQL 17.11, localhost:5432.
- Database: `kalutasociety_db`.
- Role: `kalutasociety_user`.
- Public tables: 128.
- Size: approximately 22 MB.
- Alembic rows: `c9d0e1f2a3b4`, `s3t4u5v6w7x8`, `u4v5w6x7y8z9`.
- Counts: users 240; contest 212; contestants 1,073; contest_seasons 41; contest_stages 25; votes 0; categories 124; affiliate_commissions 19; journal_entries 21; journal_lines 50; plural `wallets` absent.

### Non-public Docker backend database

- Location: remote Neon PostgreSQL.
- Database: `neondb`.
- Container: `kalutafoundation_backend`.
- This container is healthy but is not the upstream selected by the active Apache domain configuration.

### Proposed target database

- Location: VPS PostgreSQL 17.11, localhost:5432.
- Database: `mh5`.
- Size: 156 MB.
- Public tables: 167.
- Alembic revision: `f3merge01`.
- Counts: users 239; contest 196; contestants 578; contest_seasons 42; contest_stages 11; votes 86,345; categories 118; affiliate_commissions 14; journal_entries 38; journal_lines 90; wallets 5.

## Source state

`/root/kalutasociety` is not the asserted audited Prompt 2–10 source:

- Branch: `main`.
- HEAD: `a134b6c93f95a3c71f81ad2c1bc743f2dd8d6fc0` dated 2026-08-18.
- Final readiness report: absent.
- Uncommitted state exists in deployment scripts/frontend environment plus local media/disabled environment artifacts.
- The tree was not reset, pulled, overwritten, or cleaned.

The audited local Prompt 2–10 workspace was packaged without `.env` files, checksum-verified, uploaded, and extracted to the new isolated directory `/root/kalutasociety-candidate-20260909T194034Z`. The existing public tree was not overwritten. The candidate contains `FINAL_REGRESSION_PRODUCTION_READINESS_REPORT.md`.

## Verified backups and isolated staging

Backup root: `/root/deployment-backups/20260909T194034Z` (mode-restricted).

Verified custom-format dumps:

- `database/kalutasociety-db-public-predeploy.dump`: actual public systemd backend database.
- `database/live-neon-pre-cutover.dump`: Neon database used by the non-public Docker backend.
- `database/mh5-before-production-sync.dump`: existing VPS target database.

`pg_restore --list` and stored SHA-256 validation pass for all three. The deployment archive also contains the current dirty source Git bundle/patch/tree, environment files with mode 600, Docker image/container metadata, Compose, systemd, PM2, and dereferenced Apache site configuration. Secret values were not displayed.

Isolated database: `mh5_staging_20260909_194034`, restored exclusively from the fresh Neon dump. It is not connected to the public application.

- PostgreSQL: 17.11.
- Tables: 167.
- Alembic: `f3merge01`.
- Counts: users 239; contest 196; contestants 578; contest_seasons 43; contest_stages 11; votes 86,345; categories 118; affiliate_commissions 14; journal_entries 38; journal_lines 90; wallets 5.
- Final pre-migration vote recheck: 86,345.

## Alembic gate

Searches covered the local audited repository and Git history plus `/root/migration`, `/root/old_kalutasociety_backup`, `/opt/projects/kalutafoundation`, `/root/kalutasociety`, their migration directories, and both available VPS Git histories. No `f3merge01` revision file, `down_revision` reference, content reference, or Git commit was recovered.

The restored staging database reports `f3merge01`; the audited repository reports three heads: `c9d0e1f2a3b4`, `s3t4u5v6w7x8`, and `u4v5w6x7y8z9`. The actual public local database already carries all three repository heads, but has a materially different 128-table dataset with zero votes. That does not prove equivalence to the 167-table `f3merge01` schema.

Therefore Gate F is blocked. No Alembic stamp, upgrade, downgrade, generated merge, schema mutation, or migration SQL was run. The safe next technical work is a reviewed production-equivalent baseline/reconciliation package built and proven on disposable databases; it cannot be improvised during cutover.

## Final health state

- Public backend health: PASS.
- Public frontend: PASS/HTTP 200.
- HTTPS through local TLS virtual host: PASS/HTTP 200.
- Apache configuration: PASS; Nginx is absent.
- Redis on loopback: PASS/PONG.
- PostgreSQL service: active.
- No service was restarted or reloaded.

## Release-gate result

Gates passed: **5/14**—A (Neon dump), B (`mh5` dump), C (Neon restored to isolated staging), D (critical staging counts), and E (86,345 votes). Gates F–M are blocked/not run. Gate N was preserved operationally—no provider action occurred—but is not counted because no candidate runtime was started.

## Required operator decision

Before resuming, identify which dataset is legally/business-authoritative:

1. Public `kalutasociety_db` currently serving the domain;
2. Neon `neondb` used only by the non-public Docker stack; or
3. VPS `mh5` containing the 167-table/86,345-vote dataset.

Also place the actual audited Prompt 2–10 source in a new immutable candidate directory or explicitly authorize a safe transfer from the audited workspace. Do not overwrite `/root/kalutasociety` until its dirty state is archived.

Only after both decisions can fresh backups be named correctly, a staging database be restored, and the 14 release gates begin.
