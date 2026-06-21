# Contributing

Thank you for helping improve Candidate Selection Board.

By submitting a pull request, issue, or other contribution, you agree that your contribution is provided under the same license as the project: the Business Source License 1.1, including the Additional Use Grant and Change License described in `LICENSE`.

Please do not submit:

- secrets, API keys, credentials, private certificates, or real personnel data,
- code copied from another project unless its license allows inclusion here,
- vulnerability details in a public issue.

For security reports, follow `SECURITY.md`.

Before opening a pull request:

1. Run backend lint: `cd services/backend && ruff check . && ruff format --check .`
2. Run backend tests: `cd services/backend && pytest`
3. Run frontend type check: `cd services/frontend && npx tsc --noEmit`
4. Run frontend build: `cd services/frontend && npm run build`
5. Run dependency audits: `npm audit --audit-level=moderate` in `services/frontend` and `pip-audit` in `services/backend`. For dependency or security changes, verify these are clean before submitting.
6. Update `docs/INSTALLATION.md`, `docs/USER_GUIDE.md`, `docs/PRODUCTION.md`, or `SECURITY.md` when behavior, deployment configuration, or security guidance changes.
7. Regenerate the SBOM when you add, remove, or upgrade a dependency: `bash scripts/generate-sbom.sh` (requires Docker). CI also regenerates it, but committing the refresh keeps `sbom/` accurate in the tree.
8. Keep changes focused and explain any security impact in the PR description.

Security-relevant changes include authentication, authorization, MFA, session and token handling, audit logging, role management, Docker port exposure, security headers, dependency updates, AI provider connectivity, and any text operators may use to make deployment decisions.
