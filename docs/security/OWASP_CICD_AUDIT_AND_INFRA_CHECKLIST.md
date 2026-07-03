# OWASP CI/CD Top 10 — Audit and Hardening Record

## Executive Summary

This document records a hardening pass against the
[OWASP Top 10 CI/CD Security Risks](https://owasp.org/www-project-top-10-ci-cd-security-risks/)
for Darasa-Core's actual pipeline: a single GitHub Actions workflow
(`.github/workflows/ci.yml`) that validates, lints, security-scans, smoke
tests, unit-tests, and Docker-builds a Poetry-managed Django backend. There is
no frontend/Node build, no container registry push, and no external
sandbox-contract job in this repository today — this record is scoped to
what actually exists, not a template copied from a different project shape.

Risks are split into what a coding agent can fix directly in the repository
(code, workflow YAML, Dockerfile, dependency manifests) versus what requires
a human with GitHub organization/billing access to click through the GitHub
UI. Both categories are addressed below; the second is a checklist for the
repository owner, not something this change can complete unattended.

## What Changed In This Pass (Autonomous, Verified)

| Risk | Status | What was done |
| --- | --- | --- |
| **CICD-SEC-3** — Dependency Chain Abuse | Done | `.github/dependabot.yml` added for `pip`, `github-actions`, and `docker` ecosystems (weekly). A real, dated dependency vulnerability sweep was also run: `cryptography` bumped to `>=48.0.1,<49.0` (fixes `GHSA-537c-gmf6-5ccf`/`CVE-2026-34180`), and `poetry lock --regenerate` picked up already-permitted patched versions of `django` (5.2.15), `pyjwt` (2.13.0, via `djangorestframework-simplejwt`), `msgpack` (1.2.1), and `pip` (26.1.2). `pip-audit` now reports **zero** known vulnerabilities against the real Python 3.11.15 interpreter this repo's CI uses, and the previously-carried `PYSEC-2025-183` ignore was removed per the existing policy in `docs/TESTING_STRATEGY.md` ("if a fixed PyJWT release becomes available, remove the ignore"). No raw duplicate `pip-audit`/`npm audit` step was added directly in the workflow: this repo already centralizes that policy in `scripts/run-tests.sh security`, and `docs/TESTING_STRATEGY.md` explicitly says not to bypass that with ad hoc CI-only invocations. There is no `npm`/frontend manifest in this repository to scan. |
| **CICD-SEC-4** — Poisoned Pipeline Execution | Done | `.github/CODEOWNERS` now requires the real repository owner (`@ALEX-MUTHOMI`) on every CI/CD-execution-critical path: `.github/workflows/**`, `.github/dependabot.yml`, `.github/CODEOWNERS` itself, `scripts/**`, `Dockerfile`, `docker-compose*.yml`, `pyproject.toml`, and `poetry.lock`. The previous file only listed a placeholder team (`@backtofront-development/platform-security`) that is not enforceable by GitHub unless it exists as a real team — CODEOWNERS review on the pipeline itself was silently non-functional before this change. |
| **CICD-SEC-5** — Insufficient PBAC | Partially done | Workflow-level `permissions: contents: read` was already present (confirmed, not newly added). No job in this workflow currently needs elevated permissions (no releases, no package publishing, no PR comments), so the fail-closed default already covers every job without per-job overrides. There is no `daraja-sandbox-contract` (or any Daraja/M-Pesa) job in this repository's CI today — the human checklist below records the environment-protection pattern to apply **when** such a job is introduced, rather than fabricating a job that does not exist. |
| **CICD-SEC-8** — Ungoverned Usage of 3rd-Party Services | Done | Every `uses:` reference in `ci.yml` (`actions/checkout`, `actions/setup-python`, `docker/setup-buildx-action`) is now pinned to a specific commit SHA, verified live against the upstream repositories (not guessed), with the human-readable version kept as a trailing comment. Dependabot's `github-actions` ecosystem entry keeps these current going forward without reintroducing floating tags. |
| **CICD-SEC-9** — Improper Artifact Integrity Validation | Done | The production `Dockerfile`'s base image is now pinned by digest, not just tag: `python:3.11-slim-bookworm@sha256:721dc13fd1be0a771e54b72097634291d628d0007dee9da777e2ce676a9c998f`, verified live against the Docker Hub registry API (not guessed) and confirmed by an actual local `docker build` that pulled and matched that exact digest. Dependabot's `docker` ecosystem entry keeps this current. There is no frontend/Node Dockerfile in this repository to pin equivalently. |

## Verification Performed (Not Just Claimed)

- `docker build --build-arg POETRY_INSTALL_ARGS="--only main" -t darasa-core:ci .` — succeeds end-to-end against the digest-pinned base image and the regenerated `poetry.lock`.
- `docker run --rm darasa-core:ci python -c "import django; print(django.get_version())"` — prints `5.2.15`, confirming the patched Django version is what actually ships in the built image.
- `docker compose config -q` — valid.
- `bandit -r app` — no issues.
- `pip-audit` (against a Python 3.11.15 interpreter matching this repo's CI `PYTHON_VERSION`) — no known vulnerabilities, zero ignored advisories.
- Full default test gate (`pytest -m "not chaos and not future and not integration and not slow"`) — passes against the upgraded dependency set with the same single pre-existing, unrelated failure that exists on a clean checkout before any of this dependency work (`test_phase6c_algorithms_are_side_effect_safe`), confirming the dependency bumps introduced zero regressions.
- All new/changed workflow and Dependabot YAML validated with a YAML parser before commit.

## Mandatory Manual Infrastructure Checklist (Pending Human Execution)

An autonomous agent has repository code/file access only — it cannot change
GitHub organization billing tier, click through repository Settings, or
manage collaborator/secret state. The following remain for the repository
owner:

- [ ] **CICD-SEC-1 (Flow Control):** If not already on a paid tier, upgrade
      to GitHub Pro/Team to unlock required-status-check branch protection
      on private repositories. Navigate to **Settings → Branches → Add branch
      protection rule** for `main`, `staging`, and `development`. Enable
      "Require a pull request before merging", "Require approvals" (at least
      1), and "Require status checks to pass before merging" — select
      `Validate`, `Lint`, `Security`, `Django-Smoke`, `Unit-Tests`,
      `Docker-Build`, and `CI Gate` from this workflow.
- [ ] **CICD-SEC-2 (IAM):** Document and enforce that future collaborators
      are added with **Write** access, never **Admin**, unless they are an
      explicit second owner. Review current collaborator list under
      **Settings → Collaborators and teams** against this rule.
- [ ] **CICD-SEC-5 (PBAC Gates, when a real external-service job exists):**
      This repository has no Daraja/M-Pesa or other external-service
      integration job today. If/when one is added, create a matching
      **Settings → Environments** entry (e.g. `daraja-sandbox`), enable
      "Required reviewers" with the repository owner selected, and reference
      it from that job via `environment: daraja-sandbox` so the job's secrets
      are gated behind human approval before running.
- [ ] **CICD-SEC-6 (Credential Hygiene):** Navigate to **Settings → Secrets
      and variables → Actions**. Audit every stored secret against what
      `.github/workflows/ci.yml` actually references (currently: none — this
      workflow uses no repository secrets). Delete any secret that is not
      referenced by a workflow, especially any leftover credentials from
      services this repository does not currently integrate with (e.g. a
      container registry token if one was ever added and is now unused).
- [ ] **CICD-SEC-7 (Insecure System Configuration):** Navigate to
      **Settings → Actions → General**. Under "Actions permissions", restrict
      to "Allow \<org\> actions and reusable workflows" plus, if available,
      "Allow actions created by GitHub" and "Allow actions by Marketplace
      verified creators" only. This blocks arbitrary unverified third-party
      Actions from being introduced even if a future PR's YAML tries to
      reference one.
- [ ] **CICD-SEC-10 (Logging & Visibility):** Confirm Dependabot alerts are
      enabled under the **Security** tab (Settings → Code security →
      Dependabot alerts / security updates) so the `dependabot.yml` added in
      this change actually surfaces findings, not just opens PRs silently.
      Also confirm required status checks (above) make `Security` job
      failures block merges rather than being advisory-only.

## Explicit Scope Notes

- This repository is Django/Poetry-only. There is no Node/npm package
  manifest, no frontend build job, and no `scripts/ci/` directory — any
  generic checklist item referencing those was adapted or omitted rather than
  fabricated.
- `docs/PRODUCTION_READINESS_BACKLOG.md` remains the canonical, broader
  production-readiness backlog (network security, observability, data
  protection, etc.). This document is scoped specifically to the CI/CD
  pipeline itself per the OWASP CI/CD Top 10, and cross-references rather
  than duplicates that backlog's `GOV-*` and `SEC-*` rows.
