# Local and container operation

The README contains Windows setup, environment provisioning, migrations, seed and startup commands. Run all backend commands from the repository root with `PYTHONPATH=backend`; relative SQLite paths resolve from that working directory. MCP subprocesses inherit that working directory and receive an absolute backend module path.

Alembic owns schema initialization; the API does not silently create tables. Seed is explicit and idempotently exits if users already exist. Back up databases before migrations. Destructive downgrade is intentionally refused because it would remove the audit record. For a new demo dataset, use a new SQLite DATABASE_URL and run migration/seed; do not reset an existing financial/audit database in place.

Docker Compose provisions PostgreSQL, a one-shot migrator, one API process and the Nginx static portal/reverse proxy. MCP servers are fixed subprocesses of that API container. Redis is optional and unused; background workers are not implemented. Both API and frontend bind host ports to 127.0.0.1. Containers have no live banking integrations. The backend image runs as an unprivileged user. PostgreSQL retains a named volume.

The compose database URL interpolates POSTGRES_PASSWORD; use a URL-safe generated password. JWT_SECRET is mandatory in Compose and must match all signing/verifying workers. Local auto-generated keys are development convenience only. Do not log `docker compose config` with production secrets or commit .env. SQL migrations use the same credentials as the app for this demo; separate least-privilege migration/runtime credentials are required for production.

Before broader deployment: add TLS, managed secrets, OIDC/JWKS, separate DB roles, PostgreSQL integration/concurrency tests, signed checkpoints, backups and restore testing, distributed limits, remote server identity controls, dependency review, full UI/end-to-end testing, observability and security review. Container configuration alone does not verify Docker startup; see implementation status for actual checks performed.
