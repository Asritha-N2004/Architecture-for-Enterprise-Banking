# Verification scope

Tests migrate a fresh isolated SQLite database for each case and explicitly seed synthetic users. No test uses a bank or a paid LLM. Run `python -m pytest -q --basetemp=.test-tmp-local` from the repository root with backend dependencies installed.

Covered: JWT issuer/audience/expiry/signature rejection; session logout and refresh revocation; cross-organization account rejection; missing permissions; positive/finite decimal constraints; independent maker-checker decisions; dual distinct approvals; exact-instruction binding; current approver revocation; idempotency keys; repeated execution; append-only audit triggers; audit chain verification; official SDK negotiation/tool/resource/prompt discovery; unauthorized and malformed tools; closed server/tool registries; STDIO account inquiry through LangGraph. Additional tests cover concurrent execution and MCP payment preparation.

These tests are control evidence for a local slice, not proof of full enterprise security. PostgreSQL, Docker runtime, browser interaction, distributed deployment, real IdP, malformed remote responses, disconnect recovery, full ten-agent orchestration, loan/fraud/compliance services and E1–E6 comparisons remain outside current verified coverage.

Current test execution evidence is maintained in IMPLEMENTATION_STATUS.md. The evaluation runner writes fresh JUnit evidence, durations and aggregate pass/fail counts. It does not invent comparative results.

`python scripts/verify_http.py` starts Uvicorn against a fresh migrated SQLite database and a Vite preview of an existing production build, checks HTTP 200 readiness, saves evidence, and terminates its owned processes. It does not seed identities, inspect a browser, or test the reverse-proxy path; use the workflow and payment integration tests plus manual portal exercise for those paths.
