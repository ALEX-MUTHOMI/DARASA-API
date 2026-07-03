# OWASP ZAP Dynamic Testing Strategy

## What ZAP Actually Tests (And Why "CCT Is Not A Crawler" Is A Different Concern)

OWASP ZAP is a **DAST** (Dynamic Application Security Testing) tool: it
sends real HTTP requests at a **running** target and inspects the real HTTP
responses — passively (reading headers/content ZAP observes while crawling)
and, in active-scan mode, by injecting attack payloads into every
parameter it finds and watching how the target reacts.

This is a different concern from "CCT is not a web crawler." That statement
is about Darasa's own code: `app/curriculum` never makes outbound HTTP
requests to fetch official government/regulatory sites — evidence
submission is metadata-only, `ssrf_guard.py`/`source_url_validator.py`
validate but never fetch source URLs, and this is enforced by dedicated
red-team tests (`test_cct_redteam_urls.py`,
`test_cct_redteam_purity_performance.py`). Running ZAP against Darasa does
**not** change or risk that boundary: ZAP crawls and attacks **Darasa's own
HTTP endpoints**, never URLs a client happens to submit inside a JSON
payload's `claimed_source_url` field. Those are two unrelated meanings of
"crawl," and neither is compromised by the other.

## What Blocked Any DAST Testing Until Now (A Real, Fixed Gap)

Darasa uses schema-per-tenant multi-tenancy (`django-tenants`). Every
request is resolved by `TenantMainMiddleware` against the `Domain` table
before any view runs; with zero domains provisioned (the default state of a
fresh checkout, and the default state in CI), **every URL 404s regardless of
correctness** — including for ZAP, which needs a real host to attack. This
is why, before this change, there was no way to run any dynamic scan against
this codebase at all, and why every existing unit test invokes views
directly via `APIRequestFactory` instead of through real URL routing (see
[ADR 0002](../adr/0002-schema-per-tenant-isolation.md)).

`core/management/commands/provision_local_tenant.py` fixes this: a
management command that provisions a disposable school tenant + domain +
admin account for local development or DAST scanning, and refuses to run
outside `DEBUG`/`TESTING` so it can never touch a real deployment.

## What Is Real And Verified Today

`.github/workflows/dast.yml` runs a ZAP baseline (passive) scan on a weekly
schedule and on manual dispatch: it starts Postgres/Redis, applies
shared-schema migrations, provisions a scan tenant via the command above,
starts the Django dev server, and points `zaproxy/action-baseline` at it.

This was not just written — it was run for real against the actual
running application (Postgres 16, Redis 7, the same Python 3.11.15
interpreter this repo's CI uses) while building this change, and it found
real, fixable issues in `core/middleware.py`'s `SecurityHeadersMiddleware`:

| Finding (ZAP rule) | Severity | Root cause | Fix |
| --- | --- | --- | --- |
| CSP Header Not Set (10038) | Medium | Headers were only applied under `/api/`, missing the site root and any other path entirely. | `SecurityHeadersMiddleware` now applies to every path except `/admin/`, `/static/`, `/media/`. |
| Permissions Policy Header Not Set (10063) | Low | Same root cause as above. | Same fix. |
| Server Leaks Version Information (10036) | Low | Django's dev server (`WSGIServer/0.2 CPython/3.11.15`) and gunicorn both advertise implementation details by default. | Middleware now overwrites the `Server` header to a fixed, generic value on every response. |
| Storable and Cacheable Content (10049) | Informational | No explicit cache policy on dynamic responses. | Middleware now sets `Cache-Control: no-store` by default. |
| CSP: Failure to Define Directive with No Fallback (10055) | Informational | `form-action` does not inherit from `default-src` per the CSP spec and must be listed explicitly. | Added `form-action 'none'` to the default CSP. |

A separate, manual check while investigating these results (not itself a ZAP
finding) also caught that the original blanket `default-src 'none'` CSP
would have silently broken the Swagger UI docs page (`/api/docs/`), which
loads its JS/CSS from a CDN (`cdn.jsdelivr.net`) because no
`drf-spectacular-sidecar` package is installed. Fixed by giving that one
path a CDN-scoped CSP instead of exempting it from CSP entirely.

After these fixes, a rescan went from 5 `WARN-NEW` findings to 1: `Non-Storable
Content` (informational, IGNOREd in `.zap/rules.tsv` with a dated
justification — it's a confirmation that `Cache-Control: no-store` is
working as intended, not a real issue) and `Sec-Fetch-Dest Header is
Missing` (deferred as `SEC-P2-014` in
`docs/PRODUCTION_READINESS_BACKLOG.md` — low priority today because the
current surface has no session/cookie-relevant state-changing endpoint for
Fetch Metadata validation to protect).

All 5 regressions are also covered by new unit tests in
`app/core/tests/test_observability_middleware.py` so they cannot silently
reappear.

## What Is NOT Yet Testable: CCT Itself

CCT (`app/curriculum`) has **zero HTTP endpoints**. Evidence submission,
verification, governance approval, and publication are service-layer Python
functions, exercised only by pytest and Django management commands — see
`docs/API_DOCUMENTATION.md`. ZAP cannot dynamically attack code that isn't
reachable over HTTP; there is currently nothing CCT-specific for it to scan.

This is not a gap in the DAST setup — it's the same finding
`docs/PRODUCT_VISION.md` and `docs/API_DOCUMENTATION.md` already make: the
HTTP/API layer (Phase 10, "API / Integration Contract Suite" per
`docs/EVENT_BACKBONE.md`) has to exist before CCT can be dynamically
security-tested at all, static/unit red-team testing being the only option
until then.

### The Plan For When CCT Gets HTTP Endpoints

When Phase 10 exposes CCT evidence-submission and governance endpoints over
HTTP, dynamic testing should specifically target the attack classes CCT's
existing static red-team test suite already enumerates, so ZAP becomes a
second, independent confirmation of those same guarantees rather than a
duplicate of them:

| Existing static red-team coverage | ZAP dynamic equivalent once HTTP endpoints exist |
| --- | --- |
| `test_cct_redteam_xss_events.py` — executable HTML/script patterns rejected in evidence metadata | Active scan XSS injection (ZAP's built-in XSS rules) against every evidence submission text field |
| `test_cct_redteam_idor_policy_state.py` — cross-tenant evidence/governance access denied | Authenticated active scan with two distinct tenant sessions, confirming ZAP (as an attacker with valid credentials for tenant A) cannot reach tenant B's evidence via ID manipulation |
| `test_cct_redteam_urls.py` — malicious/SSRF-shaped source URLs rejected | Active scan SSRF-payload injection into the `claimed_source_url` field specifically (ZAP will not itself fetch attacker-supplied URLs on Darasa's behalf; it confirms the API rejects them, the same property the unit test proves statically) |
| `test_cct_redteam_purity_performance.py` — mass assignment / unexpected field rejection | Fuzzed/extra-parameter requests against the evidence submission endpoint, confirming reviewer/publisher/status fields cannot be client-set |

Practically, this means: once the API layer exists, import the generated
OpenAPI schema (`/api/schema/`, already live — see `docs/OBSERVABILITY.md`)
into a ZAP **API scan** (not just baseline) so every CCT parameter gets
attacked automatically, authenticated as a real provisioned tenant/role via
`provision_local_tenant`, and add a CCT-specific job to `.github/workflows/dast.yml`
gated the same way (`workflow_dispatch` + weekly schedule, not per-push).

## Running It Yourself

```bash
# 1. Bring up the stack and apply shared migrations (see Makefile).
make up
make migrate

# 2. Provision a disposable scan tenant (refuses to run outside DEBUG/TESTING).
docker compose run --rm django python manage.py provision_local_tenant \
  --domain scan.localhost --admin-email scan@darasa.local --skip-if-exists

# 3. Point scan.localhost at the running server and scan it.
echo "127.0.0.1 scan.localhost" | sudo tee -a /etc/hosts
mkdir -p /tmp/zap-report
docker run --rm --network=host \
  -v "$(pwd)/.zap:/zap/.zap-rules:ro" \
  -v /tmp/zap-report:/zap/wrk/:rw \
  ghcr.io/zaproxy/zaproxy:stable \
  zap-baseline.py -t http://scan.localhost:8000 \
  -J report_json.json -w report_md.md -r report_html.html \
  -c /zap/.zap-rules/rules.tsv -a
```

(This is the exact command sequence used to produce the verified results
in the table above.)

The same sequence runs automatically in `.github/workflows/dast.yml`.
