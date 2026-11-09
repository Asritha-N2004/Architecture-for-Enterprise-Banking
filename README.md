# Aegis — Secure MCP Banking Simulation

Working local research foundation for **A Secure Model Context Protocol-Based Multi-Agent Architecture for Enterprise Banking Workflow Automation**. This repository began empty. This delivery implements a customer/account/payment vertical slice; the full 18-phase specification is **not complete**. See [implementation status](IMPLEMENTATION_STATUS.md).

All data and execution are synthetic. Setting `SIMULATION_ONLY=false` prevents startup. No real-bank adapter or paid LLM is needed. The deterministic mock provider routes structured requests through LangGraph and the official MCP Python SDK 1.x. No model can authorize a payment.

Hosted simulation: **https://aegis-secure-mcp-banking.vercel.app**. Create an account on the hosted app, then use Create sample records in Workflow assistant. Local accounts/data were not migrated. [Vercel deployment details](docs/vercel_deployment.md).

## Run locally (PowerShell, repository root)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
Copy-Item .env.example .env
# Set JWT_SECRET in .env to a private random value, at least 32 characters.
$env:PYTHONPATH = "$PWD/backend"
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini upgrade head
$env:DEMO_PASSWORD = Read-Host 'Choose a demonstration password (12+ characters)'
.\.venv\Scripts\python.exe -m app.seed
.\scripts\start-backend.ps1
```

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. API documentation: `http://127.0.0.1:8000/docs`. If venv `ensurepip` fails, `python -m pip --python .venv install -r backend/requirements.txt` installs into that environment using the host pip. Bundled pnpm may also install/build the frontend.

The sign-in page also offers **Create account**. Choose a unique username and a password of at least 12 characters, confirm it, and submit to enter the dashboard. Registration creates a separate personal simulation organization and a READ_ONLY_USER identity with no customer grants. Users cannot select roles or join existing organizations through registration. An explicit access grant is needed to retrieve banking records. This is local demonstration registration without email verification or enterprise enrollment.

In Workflow assistant, an empty workspace offers **Create sample records**. This simulation-only action creates a synthetic customer and INR 50,000 account inside your organization, grants access only to your user, and selects the new record. It is idempotent and grants no payment permissions. Other organizations' records remain inaccessible.

Seeded users: `maker`, `checker`, `controller`, `reader`, `auditor`, `outsider`, with the password you supplied. Those names are reserved from registration. The demo assigns one role per user and explicit customer grants. Maker can prepare and simulate; checker and controller independently approve; reader can inquire; auditor can inspect same-organization audit metadata. Outsider belongs to another organization. These users are for isolated local use only. Seed provisioning remains available after a personal account has been registered.

## Demonstration

1. Sign in as maker. Run an account inquiry for `ACC-0001` in Workflow assistant. It uses actual MCP initialization, discovery, invocation, typed output validation, and LangGraph routing.
2. Prepare a payment from `ACC-0001` to `BEN-0001`. Preparation does not debit the account.
3. Sign out and sign in as checker. Review and approve the instruction in Approval center. At INR 100,000 or above, controller must also approve independently.
4. Sign in as maker and simulate the approved instruction. The balance changes once, including the INR 5 fee. Repeating execution returns the same receipt.
5. Open Audit explorer and verify the hash chain. Changes to the approved instruction or policy, expiry, missing current approver rights, and insufficient funds block execution.

The portal keeps the access token in memory; reload requires sign-in. Sessions last 15 minutes by default. Refresh/logout endpoints rotate/revoke server-side sessions. No password or token enters workflow state.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.test-tmp-local
cd frontend
npm run build
```

Use a writable, unique `--basetemp` inside the checkout when the system temporary folder is restricted. Tests create isolated migrated SQLite databases, use synthetic passwords, and never contact a bank or LLM. See [testing](docs/testing.md) for scope and evidence.

## Container deployment

Populate `JWT_SECRET` and `POSTGRES_PASSWORD` in `.env`. Passwords used in the database URL must be URL-safe.

```powershell
docker compose up --build -d
docker compose exec -e DEMO_PASSWORD backend python -m app.seed
```

Export `DEMO_PASSWORD` in your shell before the seed command. Open `http://127.0.0.1:8080`. Compose migrates before starting the API and publishes ports only on loopback. See [deployment](docs/deployment.md). Container configuration is a local simulation target, not a production deployment certificate.

## Structure

`backend/app`: API, SQLAlchemy data model, authentication, deterministic authorization, payments, audit, official MCP servers/client, LangGraph orchestration.

`backend/alembic`: frozen initial schema and append-only audit triggers. `backend/tests`: security, banking, concurrency, SDK and STDIO integration tests.

`frontend`: React/TypeScript/Vite/Tailwind portal with React Router, TanStack Query, Axios, Recharts and Lucide. `docs`: design and limitations. `evaluation`: reproducible control test runner. `scripts`: local startup and explicit seed provisioning.

Official sources: [MCP SDK maintained 1.x](https://github.com/modelcontextprotocol/python-sdk/tree/v1.x), [SDK testing](https://py.sdk.modelcontextprotocol.io/v1/), [LangGraph](https://docs.langchain.com/oss/python/langgraph/overview). The SDK is bounded below version 2 deliberately; a v2 migration remains separate work.
