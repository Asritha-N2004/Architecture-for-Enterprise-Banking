# Implementation status — 9 November 2026

## Vercel cloud deployment

Live simulation: **https://aegis-secure-mcp-banking.vercel.app** in `resum-projects/aegis-secure-mcp-banking`. React and FastAPI are deployed together; Neon `aegis-banking-db` is provisioned on the free_v3 plan in sin1 and connected to production. JWT_SECRET is generated and stored as a Vercel secret. Local SQLite data and local identities were not uploaded. Create an account separately on the hosted app.

Observed cloud checks passed: HTTPS dashboard and API/database health, read-only registration/authentication, isolated synthetic sample provisioning and idempotency, real SDK STDIO/LangGraph balance inquiry returning INR 50,000, logout and session revocation. Evidence: evaluation/results/vercel_smoke.json. The predeployment backend suite passed **34 tests**. The migration-connection/MCP targeted suite then passed **7 tests**, including the added shared-transaction migration check. The serverless migration bootstrap uses a transaction-scoped PostgreSQL advisory lock with a shared Alembic connection so it is compatible with transaction pooling. Browser inspection confirmed the rendered live sign-in/Create account page after correcting the frontend asset mapping; screenshot: evaluation/results/vercel-dashboard.png.

Final production deployment: `dpl_DsdquVDU5VQyVouePwiMamA95PYE`, status READY, stable production alias above.

See docs/vercel_deployment.md for architecture, setup, verification and limits. Docker engine testing and the original outstanding enterprise features remain pending; successful Vercel deployment does not imply production banking readiness.

## Delivery boundary

The original checkout contained only `.git`, with no commits, code, dependencies or repository instructions. Implemented a runnable local customer/account/payment simulation slice. **The full requested enterprise platform is unfinished and is not production-ready.** Missing functionality is listed below, rather than represented by empty modules or fabricated results.

## Follow-up: Create account

Added a sign-in/Create account switch, password confirmation, readable validation errors, and automatic authenticated dashboard entry after successful registration. POST /api/v1/auth/register enforces normalized unique usernames, reserved demo identities, 12-character minimum passwords, Argon2 hashing, fixed read-only permissions, a new isolated organization, and no banking-data grants. Extra role/organization fields are rejected. Registration has a five-attempt/minute/address process-local limit and records an audit event. Tests cover registration/login, isolation, duplicate names, schema rejection and throttling. Enterprise enrollment/email verification remain pending.

Follow-up verification: **30 backend tests passed in 40.12 seconds**; TypeScript and Vite production build passed. Local backend restarted with registration enabled.

## Follow-up: inquiry access errors

Diagnosed a real customer inquiry failure: MCP connected and logged a scoped DENY for a registered account with no customer grants. The client surfaced it as a generic 502. Inquiry workflows now preflight role and resource access and return an actionable 404 without exposing cross-organization record existence. Added a scoped customer-list API. The assistant offers assigned records only, shows an empty-workspace explanation, and disables inquiry submission when no record is assigned. Registration still grants no automatic banking access.

Follow-up sample selection: added an explicit Create sample records action for empty workspaces. An authenticated read-only user can provision a synthetic customer/account in their own organization and obtain a grant to those newly created records. A serialized allocation lock and idempotent grant lookup avoid duplicate provisioning; reserved sample identifiers start at 1000. No caller-supplied organization/customer identifier or elevated role is accepted. Sample provisioning is audited and remains simulation-only.

## Phase accounting

| Phase | Status | Delivered / outstanding |
| --- | --- | --- |
| 1 Inspect and initialize | Complete | Empty checkout inspected, modular backend/frontend, project instructions and ignored runtime data |
| 2 Backend/database | Partial | FastAPI, SQLAlchemy, SQLite migration, PostgreSQL-compatible schema; 14 tables of requested larger schema |
| 3 Authentication | Partial | Local Argon2 login, signed required JWT claims, sessions, revocation, rotation; enterprise OIDC/OAuth pending |
| 4 RBAC/policies | Partial | Nine code-owned role definitions, permissions, org/customer grants, deterministic payment policy; policy persistence/ABAC configuration pending |
| 5 MCP infrastructure | Partial | Official SDK 1.30, real STDIO client/server, negotiation, allowlists, schemas, timeout/concurrency/rate controls; remote HTTP identity/session management pending |
| 6 Banking servers | Partial | Customer/account/payment servers; compliance, fraud, loan, reporting servers pending |
| 7 Tool authorization | Partial | Four fixed tools, scoped signed delegation, independent server permission checks; complete requested registry/management/audit coverage pending |
| 8 LangGraph agents | Partial | Deterministic classify/specialist/explain graph for three workflow types; ten specialized agents, persistence/resumption and OpenAI provider pending |
| 9 Banking workflows | Partial | Customer inquiry, balance, payment preparation; full remaining workflows pending |
| 10 Human approvals | Partial | Independent maker-checker, dual approvals, rejection, expiry, exact-instruction binding and live approver revalidation; generic approvals/cancellation pending |
| 11 Payment safeguards | Partial | Synthetic debit/receipt, Decimal, limits, atomic conditional debit, lock/uniqueness idempotency; real settlement and double-entry ledger absent |
| 12 Audit/security | Partial | Serialized hash chain, append-only DB triggers, same-org explorer, exception logging; comprehensive security event monitoring/external retention pending |
| 13 Frontend | Partial | Six working pages: overview, structured assistant, payments, approvals, MCP infrastructure, audit; six other pages/configuration/browser E2E pending |
| 14 Synthetic datasets | Partial | Explicit reproducible tiny fixture: 2 customers/accounts, 1 beneficiary, 6 identities; large configurable dataset generator pending |
| 15 Tests | Partial | Backend control, SDK, STDIO and concurrency tests; frontend tests, browser E2E, PostgreSQL and wider adversarial matrix pending |
| 16 Research evaluation | Partial | Actual control-suite runner and saved evidence; E1–E6 and ablations not implemented |
| 17 Docker/deployment | Partial | Backend/frontend images, Compose PostgreSQL/migrator/health checks/optional unused Redis, CI; runtime verification and workers pending |
| 18 Documentation/verification | Partial | Startup, architecture, schema, identity, policy, MCP design, threat model, testing, deployment and limits documented; full requested guides and acceptance matrix pending |

The later-phase slice is included to keep the implemented foundation reviewable end-to-end. This is not a claim that incomplete earlier phases or all acceptance criteria have been satisfied.

## Verification evidence

- Initial backend suite: **24 passed** against migrated isolated SQLite databases, with real SDK memory sessions and a real STDIO MCP account invocation through LangGraph.
- Expanded suite: **27 passed in 35.03 seconds**, adding concurrent once-only execution, MCP payment preparation, and structured instruction-injection rejection.
- Final rerun after audit-head migration initialization: see evaluation/results/controls.json and controls.xml for observed results. These files are generated by execution, not hardcoded metrics.
- Frontend strict TypeScript check and Vite production build passed: 2,079 modules transformed. Build reports a 737.72 kB JavaScript chunk (228.24 kB gzip), so code splitting remains a performance improvement.
- Real Uvicorn database-health and Vite preview startup both returned **HTTP 200**. Owned smoke servers were stopped afterward. Evidence: evaluation/results/http_smoke.json. This is readiness verification, not browser interaction testing.
- Docker CLI is present, but the Docker engine named pipe is absent. **No containers were built or started.** PostgreSQL runtime behavior is unverified.
- Browser interaction and screenshot review have not been performed. Build success is not UI/end-to-end verification.
- Sandbox default temporary paths and process permissions prevented an initial test run. Successful runs used workspace-local test directories and normal local subprocess permissions.
- Dependencies downloaded from package registries. Frontend pnpm reported esbuild's install script blocked; the installed platform binary was sufficient and the actual build passed. frontend/pnpm-lock.yaml records resolved packages; backend/requirements.lock.txt is a Windows environment snapshot (including pywin32), not a portable Linux lockfile. Docker/CI install the portable backend/requirements.txt ranges.

## Exact continuation order

1. Run the current checks: install backend requirements, run pytest with a writable unique basetemp, build frontend, then start and exercise the portal using README commands. On a Docker-enabled host, run Compose and repeat the integration/concurrency suite against PostgreSQL. Add a PostgreSQL CI job before relying on its locking guarantees.
2. Finish phases 2–4: extend migrations for the remaining entities; add configurable versioned policy decisions and grants; integrate real OIDC authorization-code + PKCE/JWKS, revocation and secure sessions. Keep local login explicitly isolated.
3. Finish phases 5–7: separate server workload identities and secrets; add authenticated approved Streamable HTTP endpoints, manifest/schema pinning, structured per-tool outputs, connection lifecycle, negative/disconnect/timeout tests and complete persisted MCP/security events. Preserve deny-by-default registration.
4. Finish phases 8–9: typed persistent workflow state, resumable background execution, ten structured specialists, minimized OpenAI provider with mock parity, full compliance/fraud/loan/reconciliation workflows. Never turn model output into authorization.
5. Extend phases 10–12 with generic approval lifecycle, cancellation/policy invalidation, append-only ledger entries, external audit checkpoints, security monitoring and isolated DB credentials.
6. Complete remaining portal pages, accessible browser tests, the configurable fixed-seed large dataset generator and explicit safe new-database reset command.
7. Implement isolated E1–E6/ablation runners and real metric collection with reproducible workloads; do not weaken deployed controls or manufacture comparative findings.
8. Verify Docker, workers, migrations, backup/restore, TLS, production secrets and observability; complete documentation and every requested acceptance criterion before any readiness claim.
