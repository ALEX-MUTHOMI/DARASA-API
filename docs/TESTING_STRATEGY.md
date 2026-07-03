# Darasa-Core Testing Strategy

Darasa uses layered test gates so local work gets fast feedback without
weakening phase closeout or merge confidence.

Patch/Turbo Pass is a developer-feedback gate, not a merge/release gate.

## Gate Modes

### Patch / Turbo Gate

Command:

```bash
bash scripts/run-tests.sh patch
bash scripts/run-tests.sh turbo
```

Use this after small code or documentation patches. It runs Django checks,
migration drift checks, lint, and a tiny critical regression set. It does not
prove production readiness, does not run the full unit suite, and does not run
Docker build, Bandit, or `pip-audit`.

### Domain Gate

Command:

```bash
bash scripts/run-tests.sh domain curriculum
bash scripts/run-tests.sh domain grading
bash scripts/run-tests.sh domain events
bash scripts/run-tests.sh domain core
bash scripts/run-tests.sh domain academics
```

Use this when a domain changes. Domain gates run Django checks, migration drift
checks, the changed domain tests, and dependency regression tests that protect
cross-domain contracts. A Domain Gate is stronger than Patch Gate, but it is
not phase closeout proof.

### Full Gate

Command:

```bash
bash scripts/run-tests.sh full
```

Full Gate is the source of truth for phase closeout and merge confidence. It
runs Django checks, migration checks, migrations, the default unit selection,
lint, Bandit, `pip-audit`, compile checks, and diff whitespace checks. CI still
runs Docker and compose checks separately.

The CI security job must call the same centralized security policy as local
closeout:

```bash
bash scripts/run-tests.sh security
```

Do not add raw `pip-audit` invocations in GitHub Actions unless they use the
same exact policy from `scripts/run-tests.sh`.

### Deep Gate

Command:

```bash
bash scripts/run-tests.sh deep
```

Deep Gate is for security-sensitive closeouts, CCT/grading red-team work,
performance-risk work, and production-readiness milestones. It runs tests
marked `redteam`, `security`, `performance`, or `boundary`, plus security
audits and targeted drift scans. It should not run after every Codex edit.

## Codex Workflow

- Small patch: run Patch Gate.
- CCT/curriculum change: run Patch Gate, then `domain curriculum`.
- CCT full-proofing, upload-security, or governance change: run Patch Gate,
  `domain curriculum`, Full Gate, and Deep Gate before closeout.
- CCT production-readiness change: keep malware/content-readiness, event
  payload, no-crawler, phase-boundary, and non-mutating history tests reachable
  from `domain curriculum` or Deep Gate.
- Grading change: run Patch Gate, then `domain grading`.
- Phase 6D readiness change: during implementation run focused Phase 6D tests
  and Patch Gate after the patch stabilizes; after implementation run
  `domain grading`; at closeout run Full Gate. Run Deep Gate only if
  security-sensitive boundaries changed.
- Phase 6E correction/schema change: during implementation run focused Phase 6E
  correction and school-schema tests plus Patch Gate after the patch
  stabilizes; after implementation run `domain grading`; at closeout run Full
  Gate and Deep Gate because mark alteration, audit, schema interpretation, and
  PII boundaries are security-sensitive.
- Phase 7A report snapshot / analytics change: during implementation run
  focused Phase 7A tests and Patch Gate after the patch stabilizes; do not run
  Full or Deep during normal implementation. At closeout, run Full Gate, and run
  Deep Gate only when security-sensitive analytics boundaries changed.
- Event contract change: run Patch Gate, then `domain events`.
- Security-sensitive change: run the relevant Domain Gate; run Deep Gate if
  red-team or security behavior changed.
- Phase closeout: run Full Gate.
- CCT/grading/security closeout: run Full Gate and Deep Gate.

Codex must not claim a phase is complete after Patch Gate only. Codex should
not run Full Gate after every tiny edit unless explicitly requested.

`PRODUCTION_READINESS_BACKLOG.md` records the remaining quality work before
production: load tests, tenant-scale tests, large roster tests, CCT upload abuse
tests, event replay tests, chaos tests, backup restore drills, permission matrix
tests, nightly Deep Gate, red-team regression, and proof before making parallel
pytest execution the default.

## Changed-File Routing

Use:

```bash
bash scripts/run-tests.sh changed
```

The helper prints changed files and suggests a gate:

- `app/curriculum/**`: `domain curriculum`
- `app/grading/**`: `domain grading`
- `app/events/**`: `domain events`
- `app/core/**` or `app/tenant/**`: `domain core`
- `app/academics/**`: `domain academics`
- `docs/**`: Patch Gate
- migrations: migration check plus the relevant Domain Gate
- `pyproject.toml`, Docker, compose, or CI files: Full Gate

## Markers

Pytest markers are declared in `pyproject.toml`:

`turbo`, `curriculum`, `grading`, `events`, `core`, `tenant`, `security`,
`redteam`, `performance`, `boundary`, `slow`, and `integration`.

The root test configuration tags collected tests by domain and by risk-oriented
filename patterns, so historical tests remain discoverable by Deep Gate without
hand-editing every file.

Do not mark a test `slow` to hide a failure. Security-critical tests must stay
reachable through a Domain Gate or Deep Gate.

`pip-audit` runs with zero ignored vulnerabilities. Any dependency advisory
must fail the gate.

`pip-audit` previously carried one narrow, documented exception —
`PYSEC-2025-183` / `CVE-2025-45768` for PyJWT, a disputed advisory about
application-selected JWT key strength. That exception was removed on
2026-07-03 after a routine dependency-update cycle upgraded PyJWT to 2.13.0
(via `djangorestframework-simplejwt`), which no longer triggers the advisory.
The same cycle also resolved a then-active `cryptography` advisory
(`GHSA-537c-gmf6-5ccf` / `CVE-2026-34180`, vulnerable OpenSSL bundled in
wheels before 48.0.1) by raising the `cryptography` constraint to
`>=48.0.1,<49.0`, plus routine transitive bumps to `django` (5.2.15), 
`msgpack` (1.2.1), and `pip` (26.1.2) that were already permitted by existing
constraints but not yet reflected in the lockfile. Darasa must continue
enforcing strong JWT signing secrets through configuration and
secret-management policy regardless of PyJWT version.

Re-review this section during every dependency-update cycle. If `pip-audit`
starts failing again, either fix the dependency (preferred) or add a new,
narrow, dated exception here and in `scripts/run-tests.sh` with a specific
justification — never a blanket or permanent ignore.

## Performance Safety

`--last-failed` is allowed only for local iterative fixing when explicitly
requested. It is not an authoritative gate. `--nomigrations` is not used by
Patch, Domain, Full, or Deep gates because migration drift must remain visible.
Parallel pytest workers may be added later behind `PYTEST_WORKERS`, but they
are not enabled by default until database isolation is proven.

Do not run multiple independent `docker compose run ... pytest` containers in
parallel against the default local Postgres service. They share the same
`test_darasa_core` database name and can collide while creating or dropping the
test database. Use one gate at a time, or add isolated database names before
attempting parallel local gate execution.
