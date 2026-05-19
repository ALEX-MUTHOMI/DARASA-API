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

## Performance Safety

`--last-failed` is allowed only for local iterative fixing when explicitly
requested. It is not an authoritative gate. `--nomigrations` is not used by
Patch, Domain, Full, or Deep gates because migration drift must remain visible.
Parallel pytest workers may be added later behind `PYTEST_WORKERS`, but they
are not enabled by default until database isolation is proven.
