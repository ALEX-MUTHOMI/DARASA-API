# Darasa-Core Production Readiness Backlog

This backlog records the remaining work before Darasa-Core can be considered
production-ready at national scale.

CCT is application-architecture stable. CCT public upload production deployment
is blocked until infrastructure is wired. Darasa-Core is not production-ready
yet.

The backlog is intentional technical governance, not a failure. It keeps
production blockers visible while product development continues.

## 1. Current Production Readiness Status

Darasa-Core has strong application contracts for tenant isolation, CCT
governance, evidence quarantine, grading submission, compilation, event safety,
and layered test gates.

Darasa-Core still needs production infrastructure, operations, observability,
security controls, data-retention controls, and national-scale performance
proof before production rollout.

## 2. What Is Stable Now

- CCT evidence submission is metadata-only and quarantined.
- CCT document verification is deterministic and does not auto-approve.
- CCT governance approval is separate from school evidence submission.
- CCT publication is separate from school adoption.
- CCT rollback and withdrawal workflows do not mutate academic history.
- Grading stores assessment CBE/CCT context and compilation preserves it.
- Events are versioned, producer-allowlisted, and reference-only.
- Patch, Domain, Full, and Deep test gates are defined.
- Structured JSON logging, request correlation, HTTP-request Prometheus
  metrics, and a fail-closed metrics endpoint are wired at the application
  layer (see `docs/OBSERVABILITY.md`). Distributed tracing is implemented but
  stays disabled until an operator points it at a real collector.
- The one real public, unauthenticated HTTP endpoint (`parent/login/`) is
  rate-limited and its attempts/rate-limit hits are structured-logged with a
  PII-minimized fingerprint instead of the raw admission number.
- API responses on `/api/` carry defense-in-depth headers (CSP,
  Permissions-Policy, Cross-Origin-Resource-Policy) beyond Django's built-in
  `SecurityMiddleware` defaults.

## 3. What Is Not Production-Ready Yet

- CCT public uploads are not production-ready.
- Real private object storage is not attached.
- Malware scanning and content-sniffing workers are not implemented.
- Public upload rate limiting, WAF/DDoS protection, and step-up confirmation
  are not wired.
- Dedicated curriculum governance roles are not modeled.
- Notice delivery workers, dead-letter operations, and monitoring dashboards are
  not production infrastructure yet.
- Grading needs Phase 6D readiness dashboards and report-ready projection work.
- Whole-app observability, incident response, backup/restore, HA, and national
  load testing remain pending. Log aggregation, dashboards, alerting, and
  domain-specific metrics remain open even though application-layer
  structured logging and HTTP metrics are now wired
  (see `docs/OBSERVABILITY.md`).
- Grading, curriculum/CCT, academics, and the event backbone have no HTTP API
  surface at all yet — they are service-layer only. Rate limiting, security
  headers, and the metrics endpoint currently apply only to the small HTTP
  surface that exists today (health check, parent-login stub, docs/metrics).
  Introducing real domain HTTP endpoints will need its own rate-limit,
  throttle-scope, and audit-logging coverage, not an assumption that today's
  coverage already applies.

## 4. CCT Production Backlog

| ID | Title | Area | Priority | Risk if not done | Dependency | Owner role | Suggested phase | Acceptance criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CCT-P0-001 | Private Object Storage | CCT | P0 — production blocker | Evidence files may leak or be directly reachable. | Storage provider and tenant ownership design | Platform Architect | CCT Upload Infrastructure | No public direct file URLs; storage references are internal/private; tenant ownership enforced; checksum verified; file metadata stored separately from raw file. |
| CCT-P0-002 | Malware Scanner Worker | CCT | P0 — production blocker | Malicious uploaded files could enter governance review. | Private storage and worker runtime | Security Engineer | CCT Upload Infrastructure | `malware_scan_status` updated by trusted worker only; infected/suspicious/unavailable evidence cannot advance; scan results audit logged; scanner failure does not publish curriculum. |
| CCT-P0-003 | Content Sniffing / File Verification Worker | CCT | P0 — production blocker | File type spoofing could bypass metadata checks. | Private storage and scanner pipeline | Security Engineer | CCT Upload Infrastructure | `content_verification_status` updated by trusted worker only; MIME mismatch rejected; unsupported files cannot publish; no unsafe parsing in request path. |
| CCT-P0-004 | Step-Up Confirmation for Evidence Submission | CCT | P0 — production blocker | Compromised sessions could submit high-impact evidence. | Identity step-up service | Identity/Security Engineer | CCT Upload Infrastructure | Actor-bound confirmation; tenant-bound confirmation; expiration enforced; raw password/PIN not stored; required before public upload endpoint. |
| CCT-P0-005 | Upload Rate Limiting and Abuse Protection | CCT | P0 — production blocker | Upload endpoint can be abused for storage or review amplification. | Rate limit layer and request body controls | Platform/Security Engineer | CCT Upload Infrastructure | Per-user limit; per-tenant limit; request body limit; duplicate replay safe; abuse logging. |
| CCT-P0-006 | Dedicated Curriculum Governance Roles | CCT | P0 — production blocker | Temporary school-admin governance authority is too broad for production. | Role model expansion and policy review | CCT Architect | CCT Governance Production | `curriculum_reviewer`, `curriculum_publisher`, and `curriculum_governance_admin`; `school_admin` no longer final production governance authority; `is_staff` remains irrelevant. |
| CCT-P0-007 | Production Notice Delivery Workers | CCT | P0 — production blocker | Notice batches may not reach schools reliably or safely. | Worker runtime and event/queue operations | Platform Engineer | CCT Notice Infrastructure | Resumable delivery; idempotent batches; bounded retries; dead-letter handling; delivery failure does not roll back curriculum truth. |
| CCT-P0-008 | CCT Monitoring and Alerting | CCT | P0 — production blocker | Curriculum-control failures may go undetected. | Metrics/logging platform | SRE | CCT Observability | Evidence queue depth; verification SLA breaches; malware failures; content verification failures; governance pending queue; rollback candidates; withdrawn versions; notice delivery failures; event dispatch failures. |
| CCT-P1-009 | Governance Decision Runbooks | CCT | P1 — required before national rollout | Reviewers may approve/reject inconsistently. | Dedicated roles | Academic Governance Lead | CCT Governance Production | Documented approval, rejection, escalation, withdrawal, and rollback runbooks; reviewer training checklist; audit evidence requirements. |
| CCT-P1-010 | County/Regional Rollout Controls | CCT | P1 — required before national rollout | Scoped circulars may be rolled out too broadly. | Scope model validation | CCT Architect | CCT Rollout Production | Tenant selection honors national, region, county, pathway, grade, learning area, and unknown scopes; unknown scope blocks automatic national rollout. |
| CCT-P1-011 | Notice Batch Resume UI/Operator Workflow | CCT | P1 — required before national rollout | Operators cannot safely resume or audit failed notice batches. | Notice delivery workers | Operations Lead | CCT Notice Infrastructure | Operator workflow for pause, resume, retry, and closeout; no manual database edits required. |

## 5. Grading Production Backlog

| ID | Title | Area | Priority | Risk if not done | Dependency | Owner role | Suggested phase | Acceptance criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GRD-P0-001 | Phase 6D Readiness Dashboards / Report-Ready Projections | Grading | P0 — production blocker | Schools cannot determine report readiness safely. | Phase 6C canonical snapshots | Grading Architect | Phase 6D | Dashboard/projection layer consumes compiled facts; no report generation; missing marks and stale compilation visible. |
| GRD-P0-002 | Report Readiness Gates | Grading | P0 — production blocker | Reports may be generated from incomplete or stale facts later. | Phase 6D | Grading Architect | Phase 6D/6E | Explicit readiness state per assessment/cohort; incomplete learners flagged; stale compilation blocks report-ready status. |
| GRD-P1-003 | Large-Roster Performance Profiling | Grading | P1 — required before national rollout | Large schools may see slow grading or compilation. | Representative fixtures | Performance Engineer | Phase 6D | Measured query counts and runtime for large rosters, components, batches, and compilation. |
| GRD-P1-004 | Correction Workflow Hardening | Grading | P1 — required before national rollout | Corrections may lack sufficient audit and policy controls. | Existing correction request model | Academic Records Integrity Engineer | Phase 6D/6E | Reviewer policy, old/new state hashes, reason requirements, event safety, and recompile triggers defined. |
| GRD-P1-005 | Grade Compilation Stale-State Handling | Grading | P1 — required before national rollout | Dashboards may show outdated compiled facts. | CompilationRun metadata | Data Compilation Engineer | Phase 6D | New submissions/corrections mark compiled state stale; recompile path is explicit and auditable. |
| GRD-P1-006 | Teacher Workload Stress Testing | Grading | P1 — required before national rollout | Concurrent teacher submissions may create contention. | Load test harness | Performance Engineer | Phase 6D | Concurrent draft save, submit, idempotency, and compilation stress scenarios pass. |
| GRD-P1-007 | Step-Up Confirmation Production Integration | Grading | P1 — required before national rollout | Final grade submission could rely on a test-only confirmation path. | Identity step-up service | Security Engineer | Phase 6D | Actor-bound, tenant-bound, expiring step-up integrated for grade submission. |
| GRD-P2-008 | Offline Draft Strategy | Grading | P2 — required before scale optimization | Teachers with poor connectivity may lose draft work. | Frontend/client roadmap | Product/Grading Lead | Later grading UX phase | Offline draft conflict, retry, and sync semantics documented and tested. |
| GRD-P2-009 | Frontend Retry/Idempotency Behavior | Grading | P2 — required before scale optimization | Client retries could confuse users or duplicate attempts. | Frontend implementation | Frontend/Grading Lead | Later grading UX phase | Idempotency keys, stale draft errors, retry messaging, and conflict resolution tested. |
| GRD-P2-010 | Audit Trail Expansion | Grading | P2 — required before scale optimization | Operational disputes may lack enough context. | Event/audit policy | Academic Records Integrity Engineer | Phase 6E | Submission, correction, review, compile, and readiness audit trails queryable by tenant and actor. |

Phase 6D comes next after this backlog. Reports are later. NLP is later. Parent
analytics depends on approved compiled and report-ready data.

## 6. Event Backbone Production Backlog

| ID | Title | Area | Priority | Risk if not done | Dependency | Owner role | Suggested phase | Acceptance criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| EVT-P0-001 | Outbox Production Hardening | Events | P0 — production blocker | Events may backlog or fail silently. | Dispatcher operations | Platform Engineer | Event Production | Bounded dispatch batches; lock visibility; retry metrics; stuck-event alerting. |
| EVT-P0-002 | Dead-Letter Queue Operations | Events | P0 — production blocker | Poison events may retry indefinitely or be lost. | Event monitor | SRE | Event Production | Dead-letter records visible; replay/close process documented; bounded retry policy enforced. |
| EVT-P1-003 | External Broker Adapter | Events | P1 — required before national rollout | Local-only event flow may not scale across workers/services. | Broker selection | Platform Architect | Event Production | Adapter keeps outbox as source of truth; supports Kafka/Kinesis/SQS migration plan later. |
| EVT-P1-004 | Event Replay Policy | Events | P1 — required before national rollout | Replay may duplicate side effects or violate tenant boundaries. | Consumer idempotency | Platform Engineer | Event Production | Replay scope, idempotency, authorization, and audit rules documented and tested. |
| EVT-P1-005 | Event Retention Policy | Events | P1 — required before national rollout | Event tables may grow unbounded or delete needed audit facts. | Data retention policy | Data Protection Lead | Event Production | Retention periods by event type; archive/delete process; legal hold behavior. |
| EVT-P1-006 | Idempotent Consumer Certification | Events | P1 — required before national rollout | Consumers may duplicate effects during retries. | Consumer registry | Platform Engineer | Event Production | Each consumer proves idempotency, tenant validation, poison handling, and replay safety. |
| EVT-P1-007 | Event Schema Registry Hardening | Events | P1 — required before national rollout | Schema drift may break consumers. | Contract review process | Platform Architect | Event Production | Versioned schema review, compatibility rules, producer allowlist checks, payload examples. |
| EVT-P1-008 | Payload PII Scanner | Events | P1 — required before national rollout | Events may carry sensitive learner or document data. | Payload safety guard | Security Engineer | Event Production | Automated scan for learner data, grade marks, raw documents, guardian contacts, report text, and NLP output. |
| EVT-P2-009 | Operational Dashboards | Events | P2 — required before scale optimization | Dispatch health may not be visible. | Metrics platform | SRE | Observability | Dashboards for backlog, age, dispatch rate, failures, dead letters, replay actions. |

The current event backbone is application-level. External broker integration is
future production infrastructure. Events are facts, not commands.

## 7. Security and Compliance Backlog

| ID | Title | Area | Priority | Risk if not done | Dependency | Owner role | Suggested phase | Acceptance criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SEC-P0-001 | WAF / DDoS Protection | Security | P0 — production blocker | Public endpoints can be flooded or abused. | Edge platform | Security/Platform Engineer | Production Platform | WAF rules, DDoS protection, request body limits, bot controls, and alerting enabled. |
| SEC-P0-002 | Global and Tenant-Aware Rate Limits | Security | P0 — production blocker | One tenant or actor can degrade shared service. | Rate limit middleware/edge | Security Engineer | Production Platform | Per-IP, per-user, per-tenant, upload-specific, and grading-submit limits. **Partial**: the one existing public endpoint (`parent/login/`) has an IP-scoped DRF throttle (`core/throttling.py`). No tenant-aware, per-user, or edge-level rate limiting exists yet, and no grading/upload endpoints exist yet to limit. |
| SEC-P0-003 | Secret Rotation and Secrets Manager | Security | P0 — production blocker | Leaked or stale secrets may persist. | Secrets manager | Platform Engineer | Production Platform | Central secrets manager; rotation runbooks; no production secrets in repo or images. |
| SEC-P0-004 | Admin Access Hardening | Security | P0 — production blocker | Admin access can bypass operational controls. | Identity/MFA | Security Engineer | Production Platform | MFA/step-up, least privilege, audit logs, IP/device policy, no shared admin accounts. |
| SEC-P1-005 | Security Headers and CSP Policy | Security | P1 — required before national rollout | Browser clients may be exposed to injection or clickjacking. | Frontend/API deployment | Security Engineer | Production Platform | CSP, HSTS, X-Frame-Options/frame-ancestors, content-type sniffing protection, referrer policy. **Partial**: HSTS, X-Frame-Options, nosniff, and referrer-policy were already set; `core.middleware.SecurityHeadersMiddleware` now adds a CSP, Permissions-Policy, and Cross-Origin-Resource-Policy for `/api/` responses. Django admin HTML pages are intentionally excluded and still need their own review. |
| SEC-P1-006 | CSRF and Session Hardening Review | Security | P1 — required before national rollout | Session attacks may affect privileged workflows. | Auth/session design | Django Security Engineer | Production Platform | CSRF strategy, secure cookies, SameSite, session timeout, re-auth for critical actions. |
| SEC-P1-007 | Audit Log Immutability | Security | P1 — required before national rollout | Audit evidence can be altered after disputes. | Audit store | Security/Compliance Lead | Production Platform | Append-only or tamper-evident audit trail; hash chaining or immutable storage policy. |
| SEC-P1-008 | PII Retention Policy | Data Protection | P1 — required before national rollout | Sensitive learner data may be kept too long. | Legal/compliance review | Data Protection Lead | Data Governance | Retention periods by data class; deletion/archive rules; school exit process. |
| SEC-P1-009 | Data Export Controls | Data Protection | P1 — required before national rollout | Bulk exports may leak learner data. | Export feature design | Security Engineer | Data Governance | Role gates, approval workflow, audit logs, rate limits, export expiration, watermarking where needed. |
| SEC-P1-010 | Incident Response Runbooks | Operations | P1 — required before national rollout | Breaches or outages may be handled inconsistently. | On-call model | Incident Commander | Operations | Runbooks for tenant breach, upload abuse, grading integrity issue, event failure, data restore. |
| SEC-P1-011 | SAST/DAST Strategy | Security | P1 — required before national rollout | Vulnerabilities may escape CI. | CI pipeline | Security Engineer | DevSecOps | SAST, dependency audit, DAST staging scans, false-positive triage, severity SLAs. |
| SEC-P1-012 | Dependency Update Policy | Security | P1 — required before national rollout | Known CVEs may remain unresolved. | Package management | Platform Engineer | DevSecOps | Scheduled updates, audit triage, emergency patch process, lockfile review. **Resolved (2026-07-03)**: `pip-audit` flagged 16 known vulnerabilities across 5 packages (`cryptography` `GHSA-537c-gmf6-5ccf`/`CVE-2026-34180`; `django` 5× `PYSEC-2026-19x`; `pyjwt` 6× `PYSEC-2026-17x`; `msgpack` `GHSA-6v7p-g79w-8964`; `pip` `PYSEC-2026-196`). Fixed by raising the `cryptography` constraint to `>=48.0.1,<49.0` and regenerating `poetry.lock` (`poetry lock --regenerate`) from a Python 3.11.15 interpreter matching this repo's CI, which resolved `django` to 5.2.15, `pyjwt` to 2.13.0, `msgpack` to 1.2.1, and `pip` to 26.1.2 — all already permitted by existing constraints but not yet reflected in the lockfile. `pip-audit` now reports zero known vulnerabilities with zero ignored advisories (the previously-carried `PYSEC-2025-183` PyJWT exception was removed per the process this row already specified). Verified via a real `docker build` of the production image and a full local test-gate run with zero regressions. `.github/dependabot.yml` (added in this change) now runs this same class of check on a weekly schedule so it does not silently drift again. |
| SEC-P1-013 | Threat Model Review | Security | P1 — required before national rollout | Critical attack paths may be missed. | Architecture docs | Security Architect | Security Closeout | Threat models for CCT, grading, events, identity, tenant isolation, uploads, reporting. |

## 8. Infrastructure and Scaling Backlog

| ID | Title | Area | Priority | Risk if not done | Dependency | Owner role | Suggested phase | Acceptance criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| INF-P0-001 | Production HA Database | Infrastructure | P0 — production blocker | Database failure can take down all schools. | Cloud/database platform | Platform Architect | Production Platform | HA topology, failover test, maintenance window plan, connection pool limits. |
| INF-P0-002 | Database Backups and Point-in-Time Recovery | Infrastructure | P0 — production blocker | Data loss may be unrecoverable. | HA database | DBA/SRE | Production Platform | Automated backups, PITR, restore drills, RPO/RTO documented. |
| INF-P0-003 | Object Storage | Infrastructure | P0 — production blocker | Upload features cannot be safely exposed. | Storage provider | Platform Engineer | CCT Upload Infrastructure | Private buckets/containers, tenant paths, encryption, lifecycle policy, access logs. |
| INF-P0-004 | Load Balancer and TLS Termination | Infrastructure | P0 — production blocker | Traffic may be insecure or unbalanced. | Edge platform | Platform Engineer | Production Platform | TLS, health checks, request limits, blue/green or rolling deploy compatibility. |
| INF-P0-005 | Secrets Manager | Infrastructure | P0 — production blocker | Secrets may be copied into config or images. | Cloud platform | Platform Engineer | Production Platform | Environment-specific secrets, rotation, audit, least privilege. |
| INF-P1-006 | Read Replicas | Infrastructure | P1 — required before national rollout | Read-heavy dashboards may overload primary DB. | HA database | DBA/SRE | Scale Platform | Replica routing strategy, lag monitoring, safe read-only query paths. |
| INF-P1-007 | Autoscaling | Infrastructure | P1 — required before national rollout | Traffic spikes may degrade service. | Metrics and load balancer | SRE | Scale Platform | App and worker autoscaling, safe DB connection limits, load-test proof. |
| INF-P1-008 | Queue Workers | Infrastructure | P1 — required before national rollout | Heavy work may block request paths. | Queue broker | Platform Engineer | Production Platform | Worker pools for events, scans, notices, exports, and heavy future jobs. |
| INF-P1-009 | Private Network Segmentation | Infrastructure | P1 — required before national rollout | Internal services may be overexposed. | Cloud network | Security/Platform Engineer | Production Platform | DB, cache, workers, object storage, and admin paths isolated by network policy. |
| INF-P1-010 | Environment Promotion Strategy | Operations | P1 — required before national rollout | Staging may not match production. | CI/CD | Release Manager | Production Platform | Dev/stage/prod promotion rules, migration rehearsal, rollback plan. |
| INF-P1-011 | Blue/Green or Rolling Deploys | Operations | P1 — required before national rollout | Deploys may cause downtime or partial migrations. | Load balancer/CI | Release Manager | Production Platform | Zero/low-downtime deploy procedure; migration compatibility checklist. |
| INF-P1-012 | Disaster Recovery Plan | Operations | P1 — required before national rollout | Major outage recovery may be improvised. | Backups/infra | SRE | Operations | DR runbook, RTO/RPO, regional recovery path, restore drills. |
| INF-P2-013 | Regional Routing | Infrastructure | P2 — required before scale optimization | National latency may vary widely. | Traffic manager | Platform Architect | Scale Platform | Regional routing analysis, data residency review, failover design. |

## 9. Observability and Incident Response Backlog

| ID | Title | Area | Priority | Risk if not done | Dependency | Owner role | Suggested phase | Acceptance criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| OBS-P0-001 | Structured Logs | Observability | P0 — production blocker | Incidents cannot be reconstructed reliably. | Logging platform | SRE | Observability | **Application-layer DONE**: `structlog`-backed JSON logs with request ID, tenant schema, actor ID, event class (`core/observability.py`, `core/middleware.py`, `docs/OBSERVABILITY.md`). Still open: shipping to an external aggregation platform. |
| OBS-P0-002 | Audit Logs | Observability | P0 — production blocker | Sensitive actions may lack forensic trace. | Audit event model | Security Engineer | Observability | Auth, CCT, grading, events, admin, export, upload, and governance actions audited. Parent-login attempts and rate-limit hits are now structured-logged (`core/security_events.py`); CCT/grading/admin/export audit coverage remains open. |
| OBS-P0-003 | Application Metrics | Observability | P0 — production blocker | System health may be invisible. | Metrics platform | SRE | Observability | **Application-layer DONE for HTTP request metrics**: Prometheus counters/histograms for request rate, status code, and latency, plus a security-event counter, served fail-closed at `/api/observability/metrics/` (`core/metrics.py`, `docs/OBSERVABILITY.md`). Still open: DB/queue/worker/cache health metrics, and an actual scrape/dashboard platform. |
| OBS-P1-004 | Domain Metrics | Observability | P1 — required before national rollout | Product-critical failures may hide inside generic metrics. | Domain events | Product/SRE | Observability | CCT metrics, grading metrics, event dispatch metrics, tenant activity, readiness metrics. |
| OBS-P1-005 | Error Budgets and SLOs | Observability | P1 — required before national rollout | Reliability targets may be undefined. | Metrics platform | SRE Lead | Operations | SLOs for login, grading, CCT evidence, compilation, event dispatch, and dashboards. |
| OBS-P1-006 | Alerts and Dashboards | Observability | P1 — required before national rollout | Operators may miss incidents. | Metrics/logging | SRE | Observability | Alerts for SLA breach, scan failure, event backlog, DB saturation, high error rate, security anomalies. |
| OBS-P1-007 | Trace Correlation IDs | Observability | P1 — required before national rollout | Cross-service debugging may be slow. | Middleware/worker propagation | Platform Engineer | Observability | Request, event, worker, and audit logs share correlation IDs. |
| OBS-P1-008 | Security Event Alerts | Observability | P1 — required before national rollout | Attack signals may not be escalated. | Security logs | Security Engineer | Security Operations | Alerts for rate-limit abuse, admin anomalies, upload abuse, cross-tenant denials, repeated auth failure. |

## 10. Testing and Quality Backlog

| ID | Title | Area | Priority | Risk if not done | Dependency | Owner role | Suggested phase | Acceptance criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TST-P0-001 | CI Authoritative Clean-Run Verification | Testing | P0 — production blocker | Local test results may not match CI. | CI pipeline | Dev Productivity Engineer | CI Hardening | CI runs check, migrations, unit tests, lint, security audit, dependency audit, config/build checks. |
| TST-P1-002 | Load Tests | Testing | P1 — required before national rollout | National traffic behavior unknown. | Load environment | Performance Engineer | Scale Testing | Login, grading, CCT evidence, compilation, events, dashboards tested under representative load. |
| TST-P1-003 | Tenant-Scale Tests | Testing | P1 — required before national rollout | Cross-tenant isolation or query patterns may fail at scale. | Fixture generator | Performance Engineer | Scale Testing | Thousands of tenants simulated without all-schools hot paths. |
| TST-P1-004 | Large Roster Tests | Testing | P1 — required before national rollout | Large schools may time out during grading. | Fixture generator | Grading Engineer | Phase 6D | Large cohorts, components, drafts, batch submit, and compilation measured. |
| TST-P1-005 | CCT Upload Abuse Tests | Testing | P1 — required before national rollout | Upload path may amplify storage/review load. | Upload infrastructure | Security Engineer | CCT Upload Infrastructure | Duplicate replay, oversized file, MIME spoof, rate-limit, scanner failure, and malicious metadata tests. |
| TST-P1-006 | Event Replay Tests | Testing | P1 — required before national rollout | Replay may duplicate side effects. | Event replay tool | Platform Engineer | Event Production | Replay-safe consumers and poison event handling verified. |
| TST-P1-007 | Permission Matrix Tests | Testing | P1 — required before national rollout | Role or tenant drift may leak data. | Policy inventory | Security Engineer | Security Closeout | Matrix covers tenant admin, principal, deputy, HOD, teacher, guardian, curriculum roles, inactive bindings. |
| TST-P1-008 | Red-Team Regression Suite | Testing | P1 — required before national rollout | Known attack classes may regress. | Deep Gate | Security Engineer | Security Closeout | SSRF, XSS, IDOR, mass assignment, event injection, phase drift, no-crawler, no-history-mutation tests. |
| TST-P1-009 | Nightly Deep Gate | Testing | P1 — required before national rollout | Slow security/performance regressions may be missed. | CI schedule | Dev Productivity Engineer | CI Hardening | Scheduled Deep Gate with security audit and targeted scans. |
| TST-P1-010 | Backup Restore Drills | Testing | P1 — required before national rollout | Backups may be unusable. | Backup infrastructure | SRE | Operations | Restore drill passes; data integrity checks documented. |
| TST-P2-011 | Chaos Tests | Testing | P2 — required before scale optimization | Failure behavior under outage unknown. | Staging infra | SRE | Scale Testing | DB/cache/broker/object-storage failure scenarios tested safely. |
| TST-P2-012 | Database Failover Tests | Testing | P2 — required before scale optimization | HA claims unproven. | HA DB | DBA/SRE | Scale Testing | Failover drill with application recovery and RPO/RTO measurement. |
| TST-P2-013 | Parallel Test Isolation Proof | Testing | P2 — required before scale optimization | xdist may introduce false failures or data leakage. | Test DB isolation | Dev Productivity Engineer | CI Optimization | xdist only becomes default after deterministic isolation proof. |

Patch/Turbo is developer feedback. Domain Gate is changed-domain confidence.
Full Gate is authoritative local closeout. Deep Gate is security/performance
closeout. CI remains authoritative clean-run verification.

## 11. Data Protection / Privacy / Retention Backlog

| ID | Title | Area | Priority | Risk if not done | Dependency | Owner role | Suggested phase | Acceptance criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DAT-P0-001 | Data Classification Register | Data Protection | P0 — production blocker | Teams may mishandle learner or evidence data. | Security model | Data Protection Lead | Data Governance | Data classes, owners, sensitivity, allowed events, retention, export rules. |
| DAT-P0-002 | Learner Data Retention Policy | Data Protection | P0 — production blocker | Learner records may be over-retained. | Legal review | Data Protection Lead | Data Governance | Retention and deletion/archive rules for learners, grades, drafts, compiled snapshots, audits. |
| DAT-P1-003 | Evidence Retention Policy | Data Protection | P1 — required before national rollout | Uploaded circular evidence may be kept indefinitely. | Object storage | CCT/Data Protection Lead | CCT Upload Infrastructure | Retention by status, withdrawal, duplicate cluster, legal hold, deletion audit. |
| DAT-P1-004 | Tenant Offboarding and Export Controls | Data Protection | P1 — required before national rollout | Departing schools may lose or overexpose data. | Export controls | Operations/Data Lead | Operations | Tenant export, retention, deletion, suspension, and audit procedure. |
| DAT-P1-005 | PII Event Leakage Monitoring | Data Protection | P1 — required before national rollout | Sensitive data may enter event payloads. | Payload scanner | Security Engineer | Event Production | Automated detection and alerting for learner names, marks, guardian contacts, raw documents. |
| DAT-P2-006 | Privacy Impact Assessment | Data Protection | P2 — required before scale optimization | Regulatory or school-policy risk may be missed. | Data inventory | Data Protection Officer | Compliance | PIA completed for CCT, grading, reports, parent analytics, and future NLP. |

## 12. Developer Governance Backlog

| ID | Title | Area | Priority | Risk if not done | Dependency | Owner role | Suggested phase | Acceptance criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GOV-P0-001 | CODEOWNERS | Developer Governance | P0 — production blocker | High-risk code can merge without correct reviewers. | Repository policy | Engineering Manager | Governance | Owners for CCT, grading, events, security, migrations, CI, docs. |
| GOV-P0-002 | Protected Branches and Required Reviews | Developer Governance | P0 — production blocker | Production branches can change without control. | GitHub settings | Engineering Manager | Governance | Required checks, required reviews, admin bypass policy, signed/reviewed release process. |
| GOV-P1-003 | Migration Review Checklist | Developer Governance | P1 — required before national rollout | Schema changes may break data or deployments. | Migration discipline | Lead Backend Engineer | Governance | Checklist for reversibility, locking risk, data migration safety, tenant impact, rollback. |
| GOV-P1-004 | Security Review Checklist | Developer Governance | P1 — required before national rollout | Security-sensitive changes may miss threat review. | Security owner | Security Architect | Governance | Checklist for auth, tenant isolation, PII, events, uploads, SSRF, XSS, rate limits. |
| GOV-P1-005 | Event Contract Review Checklist | Developer Governance | P1 — required before national rollout | Event payloads may drift or leak data. | Event contracts | Platform Architect | Governance | Versioning, producer allowlist, payload safety, idempotency, retention, replay rules. |
| GOV-P1-006 | Curriculum Change Review Checklist | Developer Governance | P1 — required before national rollout | CCT changes may alter academic truth boundaries. | CCT owner | CCT Architect | Governance | Evidence/truth separation, governance roles, adoption, rollback, no history mutation, docs/tests. |
| GOV-P1-007 | Incident Response Ownership | Operations | P1 — required before national rollout | Incidents may lack clear owner. | On-call model | Operations Lead | Operations | Named incident commander, security owner, platform owner, academic integrity owner. |
| GOV-P1-008 | Release Manager Role | Operations | P1 — required before national rollout | Releases may lack accountable coordination. | CI/CD | Release Manager | Operations | Release checklist, gate evidence, migration plan, rollback plan, communication plan. |
| FAP-P3-001 | Parent Analytics Dependency Contract | Future Apps | P3 — later enterprise enhancement | Parent analytics may query live or overbroad academic data later. | Phase 6D/7 report-ready facts and guardian mapping | Future Apps Architect | Parent Analytics Phase | Parent analytics consumes approved learner-specific projections only; no school-wide leakage; guardian-learner mapping required. |
| FAP-P3-002 | NLP Grounding Boundary Certification | Future Apps | P3 — later enterprise enhancement | Future NLP may generate text from unapproved or live state. | Approved compiled facts and report-ready projections | AI Safety/Academic Integrity Lead | NLP Phase | NLP uses approved facts only; cannot decide grades, curriculum truth, reports, or corrections; outputs remain drafts for review. |
| FAP-P3-003 | Schemes and Lesson Plan Dependency Contracts | Future Apps | P3 — later enterprise enhancement | Future planning apps may silently rewrite teacher work after CCT changes. | CCT adoption and app impact planning | Future Apps Architect | Schemes/Lesson Phase | Schemes and lesson plans consume adopted curriculum context; impacted existing work is reviewed, not silently rewritten. |
| EVT-P3-010 | Kafka/Kinesis/SQS Broker Migration Plan | Events | P3 — later enterprise enhancement | Broker migration could bypass outbox and payload safety. | Event production hardening | Platform Architect | Broker Migration Phase | Migration plan preserves outbox source of truth, idempotency, tenant partitioning, payload safety, replay policy, and rollback path. |

## 13. Suggested Execution Sequence

1. Close this backlog documentation phase.
2. Rerun GitHub Actions.
3. Return to Phase 6D grading readiness dashboards / report-ready projections.
4. Continue grading phases until report-ready.
5. Before exposing CCT public uploads, implement CCT production upload
   infrastructure.
6. Before national rollout, implement observability, rate limits, WAF,
   governance roles, and notice workers.
7. Before reports, ensure Phase 6D/6E and CCT production blockers are tracked.

We are not stopping development until every production blocker is done. We are
recording production blockers so they are not forgotten.

## 14. Definition of Production-Ready

Darasa-Core is production-ready only when:

- P0 blockers in this backlog are complete and verified.
- P1 national rollout requirements are complete or explicitly accepted by
  leadership with documented compensating controls.
- CI has a clean authoritative run.
- Full Gate and Deep Gate pass for the release candidate.
- Tenant isolation, CCT governance, grading integrity, event safety, and data
  protection have current threat-model reviews.
- Backup/restore, incident response, monitoring, WAF/rate limits, secrets,
  object storage, and worker operations are live and tested.
- Production runbooks and ownership are assigned.

## 15. Phase Re-entry Point: Return to Grading Phase 6D

After this backlog documentation phase, product development returns to:

```text
Phase 6D — Grading Readiness Dashboards / Report-Ready Projections
```

Phase 6D should consume Phase 6C canonical compiled facts and CCT governance
state. It must not generate reports, PDFs, NLP remarks, parent analytics, or a
separate academic truth.
