# 🎓 Darasa API

![Python](https://img.shields.io/badge/Python-3.12-blue?style=for-the-badge&logo=python)
![Django](https://img.shields.io/badge/Django-4.x-092E20?style=for-the-badge&logo=django)
![Celery](https://img.shields.io/badge/Celery-Async-37814A?style=for-the-badge&logo=celery)
![Cloudflare R2](https://img.shields.io/badge/Cloudflare_R2-Vault-F38020?style=for-the-badge&logo=cloudflare)
![Security](https://img.shields.io/badge/Security-Hardened-red?style=for-the-badge)

**Darasa API** is an enterprise-grade, role-based School Management System API built on an **Event-Driven Architecture (EDA)**. It provides educational institutions with a highly resilient, asynchronous backend to manage student lifecycles, academic grading, and tuition billing at scale while maintaining strict cryptographic isolation of PII.

## 🏗 Architecture & The Secure Document Vault

Darasa implements a **Secure Vault Pattern**, utilizing Cloudflare R2 as the single source of truth for all sensitive binary assets (assignments, medical clearances, report cards). Django orchestrates state, permissions, and routing, but offloads heavy I/O to maintain blazing-fast API response times.

* **Strict RBAC Routing:** Endpoints are governed by a rigid hierarchy (`SuperAdmin`, `SchoolAdmin`, `Teacher`, `Student`, `Parent`). Access is evaluated at the object level before any database serialization occurs.
* **Asynchronous Processing:** Heavy operations like generating batch PDF report cards, recalculating district-wide GPAs, or sending bulk tuition invoices are offloaded to Celery workers via our internal event bus.
* **Secure Document Delivery:** Transcripts and homework assignments are never served directly. The API validates the requester's UUID and role, then generates time-limited (60s) presigned R2 GET URLs for secure, ephemeral downloading.

## 🚀 Key Features

* **Multi-Tenant / Multi-School Isolation:** Deep QuerySet filtering guarantees absolute data siloing. A user in School A physically cannot query records in School B at the database level.
* **Ruthless Security Posture:** Built-in defenses against Insecure Direct Object Reference (IDOR) attacks. Primary keys are strictly UUIDv4 to prevent sequential guessing of student profiles or financial records.
* **Atomic Tuition Ledger:** Billing quotas and tuition payments are strictly enforced using database-level row locks (`SELECT FOR UPDATE`) to prevent concurrent TOCTOU (Time-of-Check to Time-of-Use) race conditions during financial transactions.
* **Idempotent Webhooks:** Payment gateway webhooks for tuition processing are secured via HMAC-SHA256, strictly validated against replay attacks, and processed idempotently via payload hashing.

## 🛠 Tech Stack

* **Core:** Python 3.12, Django 4.x, Django REST Framework (DRF)
* **Database:** PostgreSQL (with `django-db-locks` for atomic financial operations)
* **Async Workers:** Celery + Redis
* **Storage:** Cloudflare R2 (S3-compatible Secure Vault)
* **Billing:** Stripe / Lemon Squeezy integration
* **Infrastructure:** Docker, Docker Compose, CI/CD Pipeline

## 💻 Getting Started (Local Development)

### 1. Prerequisites
* Docker & Docker Compose
* Git

### 2. Environment Setup
Clone the repository and set up your `.env` file (see `.env.example` for required keys):
```bash
git clone git@github.com:ALEX-MUTHOMI/DARASA-API.git
cd DARASA-API
# Create and populate your .env file
