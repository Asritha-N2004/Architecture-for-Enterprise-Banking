# Vercel deployment

Project: `resum-projects/aegis-secure-mcp-banking`.

Production URL: https://aegis-secure-mcp-banking.vercel.app

The root vercel.json builds the Vite frontend and Python API together. `/api/*` routes to the FastAPI function, `/assets/*` maps to the frontend builder's asset directory, and SPA routes fall back to the frontend. Runtime dependencies are declared in root requirements.txt and backend/requirements-runtime.txt; keep these files synchronized. The Python version is 3.12. The frontend pnpm workspace explicitly includes itself and permits the official esbuild installation step.

Neon resource `aegis-banking-db` uses the `free_v3` plan in `sin1`. The Vercel integration supplies DATABASE_URL. A generated JWT_SECRET is stored as a production secret. No key or database credential is committed. `.vercelignore` excludes local databases, environments, tests, caches and dependencies. The local SQLite database, existing local user account and sample records were not uploaded. Create a separate account on the hosted version and use Create sample records.

The ASGI lifespan runs Alembic migrations under a PostgreSQL advisory lock before serving requests. It does not seed users. Production boot refuses a missing PostgreSQL URL or signing secret. Standard PostgreSQL URL schemes are normalized to psycopg. STDIO server subprocesses receive the runtime dependency search path and narrow server credentials. MCP remains the official protocol, using real initialize/discovery/call operations. All payment behavior remains simulation-only.

Deployment commands, from the linked repository root with the official CLI authenticated:

```text
vercel deploy --prod --scope resum-projects --archive=tgz
python scripts/verify_deployment.py https://aegis-secure-mcp-banking.vercel.app
```

The smoke test creates a dedicated synthetic read-only identity, provisions its isolated sample records, performs a real MCP balance inquiry and revokes its session. Credentials/tokens are generated in memory and are never printed. The synthetic smoke identity and its immutable audit history remain in the demonstration database. Results are saved in evaluation/results/vercel_smoke.json.

This is a cloud-hosted simulation, not production banking readiness. Limits remain: process-local throttles, a serialized audit head, one-process-per-tool MCP overhead, cold-start migration overhead, and no distributed worker. Preview environment database/secret variables were not configured, so only production deployment is supported by this setup. A managed migration pipeline and a separate database runtime role should replace cold-start migration privileges before any sensitive deployment. Keep the database plan within its free limits or obtain explicit authorization before upgrading.
