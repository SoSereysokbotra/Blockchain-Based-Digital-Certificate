# BCIP Phased Implementation Plan

**Version:** 2.0
**Corresponding SRS:** BCIP SRS v1.3
**Purpose:** Guide an AI coding assistant (Claude Code) to build the Blockchain-Based Digital Certificate Issuing Platform step‑by‑step.

**Changelog from v1.0:** Docker is now mandatory (was optional) given WeasyPrint's native dependency risk; inserted a new **Phase 1 – Smart Contract Unit Testing** ahead of application development, per SRS NFR-1.9; added an explicit cache-backend decision task to Phase 3 (Authentication), per SRS NFR-1.10; tightened multiple Phase Completion Criteria to be objectively measurable; added production hardening of Django admin and a CI/test-execution task to the final phase; corrected SRS traceability lines throughout to cite every requirement a phase actually satisfies, including the newly added NFR-1.9–1.12. All phases after Phase 0 are renumbered by +1 relative to v1.0 to accommodate the new smart-contract-testing phase.

---

## How to Use This Plan

1. Open this file and the SRS (v1.3) in your Claude Code session.
2. Start at **Phase 0** and work forward; do not skip phases unless explicitly marked as optional.
3. At the end of each phase, verify that all "Phase Completion Criteria" are met before moving on — these are written to be objectively checkable (specific commands, specific outputs, specific bounds), not subjective judgment calls.
4. Each phase lists the *SRS requirements* that must be satisfied; use the SRS as the authoritative spec.

---

## Phase 0 – Project Scaffolding & Environment Setup

**Goal:** A runnable Django/DRF project with a PostgreSQL database, a configured blockchain connection, and the initial smart contract compiled (not yet deployed — deployment now waits until after Phase 1's tests pass).

**Tasks:**
- Initialize a Django project with a `certificates` app and an `accounts` app.
- Configure PostgreSQL via environment variables (e.g., `DATABASE_URL`); ensure no Redis or other cache service is configured (SRS §2.4, NFR-1.10).
- **Set up Docker/docker‑compose for development. This is now mandatory, not optional** — WeasyPrint (used in Phase 4) depends on native system libraries (Pango, Cairo, GDK-Pixbuf) that are unreliable to install manually across OSes. A working `docker-compose.yml` bringing up the app + PostgreSQL avoids this class of setup failure entirely.
- Install required Python packages:
  - `djangorestframework`, `djangorestframework-simplejwt`
  - `web3.py`
  - `django-q2` (for background tasks)
  - `WeasyPrint`
  - `qrcode[pil]`
  - `django-ratelimit`
  - `argon2-cffi` (optional, for password hashing)
- Install a Solidity development toolchain (Hardhat or Foundry) as a Node/standalone dependency, isolated from the Python/Django tooling — this is required starting in Phase 1.
- Write a Solidity smart contract `CertificateRegistry.sol` based on SRS §7.4 (struct with `bytes32 certHash`, `address issuer`, `uint256 issuedAt`, `bool revoked`; mapping with `bytes32` keys; `issueCertificate`, `revokeCertificate`, `getCertificate`; events). **Compile only — do not deploy yet.**
- Create a `.env.example` file listing all required environment variables.
- Run initial migrations to confirm DB connectivity.

**SRS Requirements Addressed:** 2.4, 2.5 (partially — contract written, not yet deployed), 7.3, 7.4, NFR-1.2 (env-var key storage pattern established), NFR-5.2 (config externalization pattern established)
**Phase Completion Criteria:**
- `docker-compose up` brings up the Django app and PostgreSQL with no manual host-level dependency installation required.
- Django development server starts without errors inside the container.
- PostgreSQL schema is created and migrations run cleanly.
- `CertificateRegistry.sol` compiles successfully with the chosen toolchain (`npx hardhat compile` or `forge build`) with zero errors.
- The contract is **not yet deployed** — deployment is gated on Phase 1 passing.

---

## Phase 1 – Smart Contract Unit Testing (NEW)

**Goal:** Prove the smart contract's access-control logic is correct via automated tests *before* it is deployed to Amoy or wired into the Django backend, per SRS NFR-1.9. This is the highest-risk piece of on-chain logic (an access-control bug is expensive to fix post-deployment), so it is validated first and in isolation.

**Tasks:**
- Using the toolchain installed in Phase 0 (Hardhat or Foundry), write unit tests against `CertificateRegistry.sol` running on a local/in-memory chain (Hardhat Network or Anvil) — no testnet or real gas required for this phase.
- Test `issueCertificate`:
  - Succeeds when called by an authorized issuer address with a fresh `certIdHash`.
  - Reverts when called by a non-authorized address.
  - Reverts (or is otherwise handled per design) when called twice with the same `certIdHash`.
  - Emits `CertificateIssued` with the correct indexed parameters.
- Test `revokeCertificate`:
  - Succeeds when called by the original issuer of that specific certificate.
  - **Reverts when called by any address other than the original issuer** — this is the single most safety-critical assertion in the whole system (SRS §7.4).
  - Reverts when called on a `certIdHash` that was never issued.
  - Emits `CertificateRevoked` with the correct indexed parameter.
- Test `getCertificate`:
  - Returns the correct struct fields for an issued certificate.
  - Returns a zero/default struct for a `certIdHash` that was never issued (document the exact default so the Django integration in Phase 5 can rely on it).
- Only **after all tests pass**, deploy the contract to Polygon Amoy using a hardcoded wallet (private key from env, per NFR-1.2). Store the contract address and ABI where the Django app can read them.
- Write a simple Django management command that can call `getCertificate` with a dummy `bytes32` key against the now-deployed Amoy contract and log the (empty/default) response, confirming the RPC connection from the Django side.

**SRS Requirements Addressed:** NFR-1.9, §7.3, §7.4 (access-control verification), 2.5 (deployment)
**Phase Completion Criteria:**
- All contract unit tests pass locally with **zero manual/testnet interaction** (fast, repeatable, no gas cost).
- Specifically, a test asserting `revokeCertificate` from a non-issuer address reverts is present and passing.
- The contract is deployed to Amoy; the deployed address is verified on a block explorer (e.g., PolygonScan Amoy).
- The Django management command successfully calls `getCertificate` against the live Amoy contract and logs a response without error.

---

## Phase 2 – Data Models & ORM

**Goal:** All database models defined, migrated, and accessible via Django admin (for quick inspection during development). No auth or blockchain logic yet.

**Tasks:**
- Implement models exactly as specified in SRS §6:
  - `Organization` (with fields for verification codes, password reset codes, wallet address)
  - `Certificate` (with idempotency_key, status choices including PENDING/VALID/EXPIRED/REVOKED/FAILED, certificate_hash, pdf_sha256, blockchain_tx_hash)
  - `RevocationLog`
  - `NotificationLog`
  - `RefreshToken`
  - `LoginAttempt`
  - `BlockchainInteractionLog`
  - `CacheEntry` (SRS §6.8) — supports the database-backed cache decision required by NFR-1.10; this table backs both `django-ratelimit`'s storage and the FR-5.9 on-chain data cache configured in Phase 3.
- Add indexes on `email` and `ip_address` in `LoginAttempt`.
- Register models in Django admin for easy viewing. **Note:** this admin access will need to be restricted before any non-local deployment — tracked explicitly in the final phase (NFR-1.12) so it isn't forgotten.
- Run `makemigrations` and `migrate`.
- Create a data migration or management command to seed a test organization (with hashed password and verified flag) for later use.

**SRS Requirements Addressed:** 6.1–6.8
**Phase Completion Criteria:**
- All tables exist in PostgreSQL; Django admin can list/create/delete records.
- A test `Organization` row exists with `wallet_address` set to the deployer address from Phase 1.
- `python manage.py showmigrations` shows no unapplied migrations.

---

## Phase 3 – Authentication System (Full)

**Goal:** Complete registration, email verification, login, token refresh, logout, account lockout, and password reset — all working without blockchain or certificate features. The database-backed cache decision required for rate limiting is made and implemented in this phase.

**Tasks:**
- **Configure the cache backend before implementing rate limiting.** Per SRS NFR-1.10, configure Django's `CACHES` setting to use `django.core.cache.backends.db.DatabaseCache` pointed at the `CacheEntry` table from Phase 2 (or an auto-created cache table, documented either way). Confirm `django-ratelimit` is configured to use this cache, **not** the default `LocMemCache`, so that rate limits and lockout counters remain correct if the app is later run with multiple worker processes.
- Build DRF serializers and views for:
  - `POST /api/auth/register/` (FR‑1.1)
  - `POST /api/auth/verify-email/` (FR‑1.1)
  - `POST /api/auth/resend-email-verification/` (FR‑1.9)
  - `POST /api/auth/login/` (FR‑1.2, FR‑1.3, FR‑1.6)
  - `POST /api/auth/refresh-token/` (FR‑1.5, NFR‑1.6)
  - `POST /api/auth/logout/` (FR‑1.7)
  - Password reset trio (FR‑1.8, FR‑1.9):
    - `POST /api/auth/request-password-reset/`
    - `POST /api/auth/verify-password-reset/`
    - `POST /api/auth/reset-password/`
  - `POST /api/auth/resend-password-reset-verification/`
- Implement token strategy per SRS §3.1.2 (now binding, not illustrative):
  - Access token, 15-minute lifetime, returned in JSON body.
  - Refresh token, 7-day lifetime, set as `httpOnly` cookie (FR‑1.3).
  - SimpleJWT blacklist app active; blacklist access token on logout and old refresh token on rotation.
  - Refresh token stored as hash in the `RefreshToken` model (NFR‑1.6).
- Implement verification/reset code expiry per SRS FR-1.1/FR-1.8: codes expire 10 minutes after generation, single-use.
- Implement password policy per SRS §3.1.5: minimum 10 characters, checked against a static common-password list.
- Implement account lockout (FR‑1.6):
  - Check `LoginAttempt` before login; return 423 if locked.
  - Record failed/successful attempts.
  - Scheduled cleanup (or query‑based filtering) to ignore old attempts.
- **Implement a documented IP-resolution policy (NFR-1.11)**: a single utility function used everywhere client IP is needed for rate limiting/lockout, with an explicit, commented decision on whether/how far to trust `X-Forwarded-For` (document the assumption: e.g., "not behind a proxy in this deployment; direct socket IP used").
- Apply rate limiting per SRS §3.1.4 (using `django-ratelimit` with exact thresholds), using the cache backend configured above.
- Email‑related actions (verification, reset) should *log* the email content to the console for now; actual SMTP integration comes later.
- Write a comprehensive set of API tests (using Django's test client) covering all flows, including lockout, rotation, and token blacklisting.

**SRS Requirements Addressed:** FR‑1.1–FR‑1.9, NFR‑1.1, NFR‑1.3, NFR‑1.6, NFR-1.10, NFR-1.11, §3.1.4 rate limits, §3.1.5 security requirements
**Phase Completion Criteria:**
- `settings.py` shows a `DatabaseCache` (or equivalent non-default, cross-process-safe) configuration, and a code comment or test confirms `django-ratelimit` is using it.
- All authentication endpoints return correct HTTP status codes and token cookies.
- Lockout triggers after exactly 5 failed logins (account) / 20 failed logins (IP) within 15 minutes, and clears after a 30‑minute cooldown — each verified by a dedicated test using time-mocking, not manual waiting.
- Verification and password-reset codes are rejected after 10 minutes (time-mocked test) and after one successful use.
- Password reset correctly deletes all existing refresh tokens.
- Refresh token rotation rejects a reused token with 401.
- Rate limits enforced for **each** of the 7 endpoints listed in SRS §3.1.4 individually (429 returned when exceeded) — list each endpoint's test explicitly rather than asserting rate limiting "in general."
- All tests pass under `python manage.py test` (or `pytest`) with zero failures.

---

## Phase 4 – Certificate PDF & QR Code Generation

**Goal:** Given certificate data, the system can generate a styled PDF with a QR code. No blockchain anchoring yet.

**Tasks:**
- Build a `CertificateService` class (or utility functions) that:
  - Accepts validated certificate data.
  - Generates a unique Certificate ID (UUID or prefixed string).
  - Renders an HTML certificate template with recipient name, course, issue date, Certificate ID, and a QR code image.
  - Converts HTML to PDF using WeasyPrint (running inside the Docker container configured in Phase 0 — do not attempt bare-metal WeasyPrint installation).
  - Saves the PDF to a configurable storage location (local filesystem or cloud bucket stub).
- Create a simple DRF endpoint `POST /api/certificates/` (temporarily unauthenticated) that calls the service, stores the certificate record with status `PENDING`, and returns the Certificate ID and PDF URL.
- The generated QR code must encode the public verification URL (e.g., `https://<domain>/verify/<cert_id>`).
- Implement the input validation/sanitization from FR‑2.1.1 and FR‑2.1.2 using the now-binding field limits (200 chars for name/title, RFC 5322 + 254 chars for email; reject HTML/script-like content).

**SRS Requirements Addressed:** FR‑2.1, FR‑2.1.1, FR‑2.1.2, FR‑2.2, FR-2.2.1 (idempotency, see below), FR‑2.3, FR‑2.6 (partially, no tx hash yet), FR‑5.2 (QR code), NFR-1.8
**Phase Completion Criteria:**
- Hitting the endpoint with valid data creates a `Certificate` record, generates a PDF file, and returns a URL that serves the PDF.
- A programmatic PDF-text-extraction check (e.g., via `pdfplumber` or similar) confirms the recipient name, course title, issue date, and Certificate ID are all present as text in the generated PDF — not a manual visual check.
- Scanning the embedded QR code (or decoding it programmatically, e.g., with `pyzbar`) resolves to the expected verification URL string.
- Invalid input is rejected with field‑level errors; a test specifically submits a 201-character name and asserts a 400 field-level error, and a test submits an HTML-tag-containing title and asserts rejection.
- Idempotency key (FR‑2.2.1) works: sending the same key within 24 hours returns the existing record (test asserts identical `certificate_id` returned, not just a 200).

---

## Phase 5 – Blockchain Anchoring (Asynchronous Issuance)

**Goal:** When a certificate is created, its hash is recorded on‑chain via a background task; the certificate becomes `VALID` only after confirmation.

**Tasks:**
- Implement the canonical hashing function (SRS §7.2.1) in `certificates/hashing.py`. Use `sha256(canonical(cert))`. The hash must be deterministic — add a unit test that hashes the same input twice and asserts identical output, and a test that changing any one field changes the hash.
- Integrate web3.py: write a `BlockchainService` class that:
  - Connects to Amoy using the provider URL and wallet private key from env.
  - Has methods `issue_certificate(cert_id, cert_hash)` and `revoke_certificate(cert_id)` that build and send transactions.
  - Returns the transaction hash.
- Set up `django-q2` with a single‑concurrency cluster (to avoid nonce collisions). Document this as a deliberate throughput bottleneck (all on-chain writes serialize through one worker) — acceptable for this project's scale per SRS §11, not a bug.
- Create a background task `process_issuance(certificate_id)` that:
  - Fetches the certificate record.
  - Calls `BlockchainService.issue_certificate` with `keccak256(cert_id)` and the certificate hash.
  - Waits for transaction receipt.
  - Updates `Certificate.blockchain_tx_hash` and changes status from `PENDING` to `VALID`.
  - If the transaction fails, sets status to `FAILED` and stores the error in `failure_reason` (and logs to `BlockchainInteractionLog` per FR‑2.10).
- Modify the certificate creation endpoint (now behind authentication from Phase 3):
  - Validate input, compute canonical hash, store hash in DB, set status `PENDING`, enqueue the background task, return HTTP 202.
  - Ensure the idempotency check prevents duplicate tasks.
- Provide a `POST /api/certificates/<id>/retry/` endpoint for retrying issuances that are `FAILED` **or** `PENDING` for more than 10 minutes (FR‑2.9's now-quantified stale-PENDING threshold).
- Add a scheduled task (or cron) that runs at least every 10 minutes, checks for `PENDING` certificates older than the FR-2.9 threshold, and flags them as eligible for retry in the dashboard (does not have to auto-retry, but must make them visibly actionable).

**SRS Requirements Addressed:** FR‑2.4, FR‑2.5, FR‑2.6, FR‑2.7, FR‑2.8, FR‑2.9, FR‑2.10, §7.5, §7.2.1
**Phase Completion Criteria:**
- Creating a certificate via the API returns 202, record is `PENDING`.
- Within a few seconds, the background task confirms the transaction, status becomes `VALID`, and `blockchain_tx_hash` is populated.
- Calling `getCertificate(keccak256(cert_id))` on the deployed contract returns the correct hash — confirmed against the Phase 1 test suite's documented expected struct shape.
- Simulate a transaction failure (e.g., wrong nonce, or a mocked `web3.py` exception) and verify status becomes `FAILED` with a `failure_reason` populated, and that the retry endpoint successfully re-submits and eventually reaches `VALID`.
- A certificate artificially left `PENDING` for >10 minutes (test via time-mocking or direct DB manipulation) is confirmed retry-eligible by the scheduled task/dashboard flag.
- `BlockchainInteractionLog` contains one entry per attempt, including at least one `succeeded=False` entry from the simulated failure above.

---

## Phase 6 – Certificate Management Dashboard (Organization Portal)

**Goal:** Authenticated organization users can list, search, view, and revoke certificates.

**Tasks:**
- Build DRF viewsets/endpoints (all scoped to the authenticated organization per NFR‑1.5):
  - `GET /api/certificates/` – paginated list (default page size 25, per NFR-2.2) with search/filter by recipient name or cert ID (FR‑3.1, FR‑3.2).
  - `GET /api/certificates/<id>/` – full detail including blockchain tx hash (FR‑3.3).
  - `POST /api/certificates/<id>/revoke/` – initiates revocation (FR‑3.4, FR‑3.5).
- Revocation flow (asynchronous, similar to issuance):
  - Endpoint validates the request, logs the reason in `RevocationLog`, enqueues a `process_revocation` task.
  - The task calls `revokeCertificate` on the contract; upon receipt, updates `status` to `REVOKED`.
  - The `revokeCertificate` contract method's issuer-only enforcement was already verified in Phase 1 — this task only needs to confirm the Django integration surfaces a contract revert correctly (e.g., as a `FAILED` revocation with a clear error) rather than silently succeeding.
- Implement the daily expiration job (FR‑4.2.1): a Django management command that selects `VALID` certificates with `expiry_date < now()` and updates status to `EXPIRED`. Schedule it via `django-q2` scheduler or an OS cron job.
- Status in list views must be the denormalized `status` field (updated by the expiration job and by issuance/revocation tasks).
- Build simple React/Vite frontend pages (or use Django templates for demo) to demonstrate the dashboard: login, list certificates, create new, view details, revoke. Ensure the frontend manages access tokens and refreshes silently. (You may keep the frontend minimal; a functional DRF browsable API with authentication is acceptable for academic demo, but basic UI is preferred.)

**SRS Requirements Addressed:** FR‑3.1–3.5, FR‑4.1, FR‑4.2, FR‑4.2.1, FR‑4.3, FR‑4.4, NFR‑1.5, NFR-2.2
**Phase Completion Criteria:**
- Logged‑in user sees only their organization's certificates (test: create a second organization, confirm cross-organization list/detail/revoke all return 404 or empty, not just filtered).
- Search/filter works correctly against both recipient name and Certificate ID.
- Revoking a certificate causes its status to become REVOKED within a bounded, tested time window (e.g., within 30 seconds against a local/Amoy testnet in the test suite); the contract's `revoked` flag is confirmed true via `getCertificate`.
- Expired certificates automatically transition to EXPIRED after the scheduled job runs (test: create a certificate with a past `expiry_date`, run the management command directly, assert status change).
- List endpoint returns paginated results with the documented page size once more than one page of data exists.

---

## Phase 7 – Public Verification Portal

**Goal:** Anyone can verify a certificate by ID or QR scan, receiving a trustworthy status and blockchain proof.

**Tasks:**
- Create a public DRF endpoint `GET /api/public/verify/<cert_id>/` (no authentication). Enforce GET-only per NFR-1.4; add a test asserting POST/PUT/DELETE to this route return 405.
- Implement the verification logic as described in SRS §7.6:
  - Retrieve certificate from DB; if not found, return "NOT FOUND".
  - Recompute canonical hash.
  - Call `getCertificate(keccak256(cert_id))` on the contract.
  - Compare hash and check `revoked` flag (per Authority Rule).
  - Determine final status: VALID, EXPIRED, REVOKED, TAMPERED.
  - Return JSON with certificate details, status, blockchain tx hash, and a block explorer link.
- Implement caching using the **same database-backed cache configured in Phase 3** (per NFR-1.10): cache `certHash` and `issuedAt` indefinitely once first retrieved; cache the `revoked` flag for 60 seconds and explicitly invalidate that cache entry when the organization's own revocation transaction confirms (Phase 6's revocation task should call this invalidation).
- Apply rate limiting of 30 req/min per IP on this endpoint (FR‑5.8, NFR‑1.7), using the Phase 3 IP-resolution policy (NFR-1.11) for consistency.
- Build a minimal public HTML page that accepts a Certificate ID, calls the API, and displays the result in a user‑friendly format (including tamper warning in red).
- The QR code scanned from a certificate PDF must open this page with the ID prefilled.

**SRS Requirements Addressed:** FR‑5.1–5.9, §7.6, NFR‑2.1, NFR-1.4, NFR-1.10
**Phase Completion Criteria:**
- Entering a valid Certificate ID shows all details and status VALID.
- Scanning the QR code on a PDF opens the verification page and auto‑populates the ID.
- A tampered certificate (where you manually change the DB `course_title` and recompute) shows TAMPERED warning and clearly indicates hash mismatch.
- A test confirms non-GET requests to the verification endpoint return 405 (NFR-1.4).
- Rate limit returns 429 when exceeded — 31st request within a minute from one IP.
- A load test (e.g., using `locust`, `hey`, or a threaded Django test client — name the tool used in the test suite) issuing 10 concurrent requests against a warmed cache returns results within 3 seconds for at least 95% of requests (NFR-2.1's now-precise bound).
- A test confirms the `revoked` flag cache entry is invalidated (i.e., a fresh read reflects `True`) within 60 seconds of a revocation confirming, and immediately if Phase 6's explicit invalidation call fires correctly.

---

## Phase 8 – Email Notifications & Logging

**Goal:** Recipients receive an email with the PDF when issuance completes; all important actions are logged.

**Tasks:**
- Configure Django's SMTP backend (or an email service like SendGrid) using environment variables.
- Implement a notification service that:
  - After the issuance background task sets status to `VALID`, sends an email to `recipient_email` with the PDF attached (FR‑6.2).
  - Logs the send attempt in `NotificationLog` (FR‑6.3).
  - On failure, logs the error and sets the log status to `Failed`.
- Add a manual resend action: `POST /api/certificates/<id>/resend-notification/` (FR‑6.3).
- Ensure that authentication emails (verification, password reset) are also sent via SMTP (replacing the console logging from Phase 3).
- Add Django's admin action or management command to view `BlockchainInteractionLog` and `NotificationLog`.

**SRS Requirements Addressed:** FR‑6.1, FR‑6.2, FR‑6.3
**Phase Completion Criteria:**
- When a certificate transitions to VALID, an email is sent to the recipient with the PDF attached (verified via Django's test email backend capturing the outgoing message and asserting an attachment is present).
- The email contains a clickable verification link (assert the link string is present and points to the correct `cert_id`).
- If SMTP is down (simulate via a mocked backend raising an exception), the log shows `Failed` and a resend can be manually triggered and succeeds against the (now-working) mock.
- Authentication emails (verify/reset) arrive at the registered address (captured via the test backend).

---

## Phase 9 – Security Hardening, Config, CI & Final Polish

**Goal:** Ensure all security requirements are implemented, configuration is externalized, the project is ready for submission, and the previously-flagged Django admin exposure is closed.

**Tasks:**
- Verify `DEBUG=False` in production settings; all secrets in environment variables.
- Ensure HTTPS is enforced in production (if deployed) and cookies have `Secure` flag.
- **Restrict Django admin access (NFR-1.12):** require `is_staff`/`is_superuser` (Django's default already does this, but confirm no view/permission has been accidentally loosened), and add a settings-level guard (e.g., only mount `/admin/` when an explicit `ENABLE_ADMIN` env var is set, or IP-allowlist it) so it isn't silently exposed on a public deployment.
- Run through the OWASP‑style checklist: CSRF protection (DRF token auth), XSS (React/Vite default escaping), SQL injection (ORM), CORS settings (only allow frontend origin).
- **Wire the full test suite into a single documented command** (e.g., `docker-compose run web pytest --cov`) and confirm a coverage report is generated. This does not require a hosted CI service, but the command must be runnable by a fresh clone with no undocumented setup steps.
- Write a comprehensive README explaining how to:
  - Set up the project via Docker (primary path) or manually (documented fallback).
  - Deploy the smart contract and configure the `.env` (referencing Phase 1's test-then-deploy sequence).
  - Run the full test suite (the single command above).
- Add integration tests that cover the whole issuance→verification→revocation flow, including blockchain interaction (using a local test network or a mocked web3).
- Review the code for any remaining hard‑coded values; run an automated `grep`-based check (e.g., for likely private-key or password patterns) rather than a manual read-through only, and document the check performed.
- Confirm the canonical hashing function (§7.2.1) is defined in exactly one place — a static check (grep for the function name / a `sha256(canonical(` pattern) confirming a single definition site.
- (Optional) Deploy a live demo on a free cloud platform (Heroku/Railway) connected to Amoy.

**SRS Requirements Addressed:** NFR‑1.1–1.12, NFR‑5.1, NFR-5.2, NFR-6.1, §5.2 Performance
**Phase Completion Criteria:**
- All environment‑specific values are read from `os.environ`.
- `/admin/` is confirmed inaccessible (or explicitly gated) in a settings configuration matching the documented production posture.
- Test suite covers authentication, issuance, verification, revocation, lockout, and rate limits, runnable via the single documented command with a passing result and a generated coverage report.
- README allows a fresh clone to be running (via `docker-compose up`) within a time bound you state and verify yourself (e.g., "under 10 minutes on a clean machine with Docker installed") — timed at least once and the observed time recorded in the README or submission notes.
- No sensitive data (private keys, passwords) committed to version control — confirmed via the automated grep check above, not eyeballing.

---

## Phase 10 – (Optional Stretch Goals)

Only attempt if all previous phases are complete and fully tested.

- IPFS storage for certificate PDFs (update `pdf_url` to IPFS hash).
- Multi‑organization branding (each org has a logo/color scheme used in PDFs).
- Bulk CSV issuance.
- Offline‑first verification mobile app (PWA).

---

*End of Implementation Plan*