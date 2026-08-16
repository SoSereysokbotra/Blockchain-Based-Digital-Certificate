# SOFTWARE REQUIREMENTS SPECIFICATION
## Blockchain-Based Digital Certificate Issuing Platform (BCIP)

**Version:** 1.3
**Prepared for:** Course Capstone Project Submission
**Team Type:** Individual
**Date:** [Insert Date]

---

## Document Control

| Field | Detail |
|---|---|
| Document Title | Software Requirements Specification – Blockchain-Based Digital Certificate Issuing Platform |
| Prepared By | [Your Name] |
| Student ID | [Your ID] |
| Course / Module | [Insert Course Name] |
| Version | 1.3 |
| Status | Draft |

### Revision History

| Version | Date | Author | Description |
|---|---|---|---|
| 0.1 | [Date] | [Your Name] | Initial draft |
| 1.0 | [Date] | [Your Name] | First complete version submitted for review |
| 1.1 | [Date] | [Your Name] | Stack corrected to Django/DRF/PostgreSQL; added full authentication architecture (§3.1); added canonical hashing spec, bytes32 contract keys, async issuance flow, and Authority Rule (§7); added input validation, idempotency, verification rate-limiting, blockchain error visibility, and expiry-status resolution as explicit requirements (§3.2, §3.4, §3.5, §5.1, §11) |
| 1.2 | [Date] | [Your Name] | Made rate limits explicit (§3.1.5, §3.5.8); committed to client‑supplied idempotency key (§3.2.2.1); clarified async issuance wording (§3.2.7); removed "or download link" from email requirement (§3.6.2); specified quantitative performance load (§5.2.1); added multi‑issuer enforcement to contract (§7.4); relocated implementation details to separate design document; general tightening of wording |
| 1.3 | [Date] | [Your Name] | **Review-driven revision.** Assigned formal NFR-IDs to previously unlabeled §5.4/5.5/5.6 bullets; quantified all previously example-only thresholds (token lifetimes, code expiries, stale-PENDING window, password policy, field length limits); added NFR-1.9 (smart contract unit testing before deployment); added NFR-1.10 (cache backend constraint, consistent with §2.4's no-Redis decision); added NFR-1.11 (reverse-proxy / `X-Forwarded-For` trust policy for IP-based limits); added NFR-1.12 (production restriction of internal/admin tooling); clarified FR-2.1.1 field-length table; clarified FR-2.9 stale-PENDING threshold |

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Overall Description](#2-overall-description)
3. [Functional Requirements](#3-functional-requirements)
4. [External Interface Requirements](#4-external-interface-requirements)
5. [Non-Functional Requirements](#5-non-functional-requirements)
6. [Data Requirements (Logical Data Model)](#6-data-requirements-logical-data-model)
7. [Blockchain Architecture and Smart Contract Design](#7-blockchain-architecture-and-smart-contract-design)
8. [Use Cases](#8-use-cases)
9. [Assumptions, Dependencies, and Constraints](#9-assumptions-dependencies-and-constraints-summary)
10. [Future Enhancements](#10-future-enhancements-out-of-current-scope)
11. [Known Limitations and Design Trade-offs](#11-known-limitations-and-design-trade-offs)

---

## 1. Introduction

### 1.1 Purpose

This Software Requirements Specification (SRS) document describes the functional and non-functional requirements for the Blockchain-Based Digital Certificate Issuing Platform (BCIP). The purpose of the system is to allow educational institutions and training organizations to issue digital certificates that are tamper-resistant and publicly verifiable, by anchoring certificate integrity data on a blockchain network. This document is intended to guide the design, implementation, and testing of the system, and to serve as a reference for evaluating whether the completed system meets its intended requirements.

### 1.2 Scope

The system, referred to as BCIP, is a web-based application consisting of two primary user-facing components:

- An **Organization Portal**, where authenticated staff of an issuing organization can create, issue, view, revoke, and manage digital certificates.
- A **Public Verification Portal**, where any member of the public can verify the authenticity and status of a certificate using a Certificate ID or a QR code, without needing to log in.

The system will generate a downloadable PDF for each issued certificate, record a cryptographic proof of each certificate on a public blockchain network, notify recipients by email, and manage certificate lifecycle states (valid, expired, revoked). The system will **not** store complete certificate documents on-chain; only cryptographic hashes and minimal integrity metadata will be recorded on the blockchain, in order to keep the solution cost-effective and scalable while still providing tamper-evidence.

### 1.3 Intended Audience

- The course instructor / evaluator assessing the project against its requirements.
- The developer (author of this document), as a reference during design and implementation.
- Any future maintainer of the system.

### 1.4 Definitions, Acronyms, and Abbreviations

| Term | Definition |
|---|---|
| BCIP | Blockchain-Based Digital Certificate Issuing Platform (this system) |
| Certificate ID | A unique identifier assigned to each issued certificate |
| Hash / Certificate Hash | A fixed-length value produced by a cryptographic hash function (e.g., SHA-256) that uniquely represents certificate data; any change to the data changes the hash |
| Smart Contract | Self-executing program deployed on a blockchain that stores and manages certificate hash records |
| Testnet | A blockchain network used for testing, functionally similar to a production ("mainnet") network but using tokens with no real monetary value |
| QR Code | A machine-readable code that encodes the certificate verification URL |
| Issuer / Organization | The institution or entity that creates and issues certificates through the Organization Portal |
| Recipient | The individual to whom a certificate is issued |
| Revoked | A certificate status indicating the issuer has invalidated a previously valid certificate |
| IPFS | InterPlanetary File System — optional decentralized file storage for certificate PDFs (stretch goal) |

### 1.5 References

- Project brief: "Blockchain-Based Digital Certificate Issuing Platform" assignment specification
- IEEE Std 830-1998 – Recommended Practice for Software Requirements Specifications (structural reference)
- Ethereum / EVM-compatible testnet documentation (e.g., Sepolia, Polygon Amoy)
- Blockcerts open standard for blockchain-anchored credentials (conceptual reference)

### 1.6 Overview of Document

Section 2 provides an overall description of the product, its functions, users, and constraints. Section 3 lists specific functional requirements grouped by feature area. Section 4 covers external interface requirements. Section 5 covers non-functional requirements. Section 6 describes the system's data model. Section 7 describes the blockchain and smart contract architecture. Section 8 lists use cases. Section 9 covers assumptions, dependencies, and constraints. Section 10 outlines future enhancements.

> **Design Note:** The choices of specific frameworks, libraries, and code-level details (e.g., token‑handling patterns, cache back‑ends) are implementation decisions described in the companion *Design Document*, except where this SRS now pins down a specific constraint (e.g., NFR-1.10) because leaving it open created a testable ambiguity. This SRS otherwise focuses on what the system shall do, independent of the particular technology stack used to achieve it.

---

## 2. Overall Description

### 2.1 Product Perspective

BCIP is a new, standalone web application. It is not a modification of an existing system. It integrates with an external public blockchain network (via a testnet, for the purposes of this project) rather than operating its own private ledger. It also integrates with a third-party email delivery service and a QR code generation library. The high-level architecture consists of a frontend web client, a backend application server, a relational/NoSQL database for off-chain data, and a smart contract deployed on a blockchain test network.

### 2.2 Product Functions

At a high level, BCIP provides the following functions:

- Organization account authentication (login)
- Certificate creation and issuance, including PDF generation
- Recording a certificate's cryptographic hash on the blockchain at issuance time
- Listing and searching certificates issued by the logged-in organization
- Public certificate verification by Certificate ID or QR code scan
- Display of certificate status (Valid / Expired / Revoked) and associated blockchain transaction details
- Certificate revocation by the issuing organization
- Automatic certificate expiration handling based on a configured expiry date
- Automated email notification to recipients when a certificate is issued

### 2.3 User Classes and Characteristics

| User Class | Description | Technical Expertise |
|---|---|---|
| Organization Administrator / Staff | Authenticated user who creates and manages certificates on behalf of the issuing institution | Low–Medium; uses a standard web dashboard |
| Certificate Recipient | Receives a certificate and its verification link/QR code by email; may share it with third parties | Low; passive recipient |
| Public Verifier | Any member of the public (e.g., employer) checking whether a certificate is genuine | Low; uses a simple public web form |

### 2.4 Operating Environment

- **Client:** Any modern web browser (Chrome, Firefox, Edge, Safari) on desktop or mobile.
- **Server:** A Python-based web application (e.g., Django) served via a WSGI server, deployed on a standard cloud host or local server for demonstration.
- **Database:** A relational database management system (e.g., PostgreSQL) for all off-chain data, including certificate records and authentication state. Per NFR-1.10, no separate cache/session service (e.g., Redis) is used; where a cache abstraction is required, it shall be backed by the same relational database.
- **Blockchain:** Polygon Amoy testnet (EVM-compatible, chainId 80002), accessed via a JSON-RPC provider.

### 2.5 Design and Implementation Constraints

- Only a cryptographic hash and minimal metadata will be stored on-chain; full certificate contents remain off-chain, for cost and performance reasons.
- The system will be deployed against a public test network rather than a production mainnet, since this is an academic project without a real budget for gas fees.
- The organization's blockchain transactions must be signed using a wallet/private key held securely by the backend (e.g., via environment variables), never exposed to the client.
- The system must be implementable by a single developer within the project timeline.
- No external cache or session service (e.g., Redis, Memcached) shall be introduced; any in-process or cross-process caching need shall be satisfied using the primary relational database (NFR-1.10).

### 2.6 Assumptions and Dependencies

- It is assumed the organization has a single shared login for this project's scope (multi-branch/multi-admin support is a possible future enhancement).
- It is assumed test-network cryptocurrency (test MATIC) is obtainable free of charge from a public faucet.
- The system depends on the availability of the chosen blockchain RPC provider and email delivery service.

---

## 3. Functional Requirements

Each requirement below is labeled with a unique ID for traceability during design, implementation, and testing.

### 3.1 Organization Authentication

The system shall implement a robust authentication mechanism using short‑lived access tokens, long‑lived refresh tokens with rotation, account lockout, email verification, and password reset. All authentication state shall be persisted in the application database; no additional cache service is required at this project's scale.

#### 3.1.1 Functional Requirements

| ID | Requirement |
|---|---|
| FR-1.1 | The system shall allow an organization to register with an email and password, and shall send a 6‑digit verification code to that email before the account can log in. The code shall expire **10 minutes** after generation. |
| FR-1.2 | The system shall allow an organization user to log in using email and password, and shall reject invalid credentials with a generic error message that does not reveal whether the email exists. |
| FR-1.3 | The system shall issue a short‑lived access token and a long‑lived refresh token upon successful login. The access token shall be returned in the response body; the refresh token shall be set as an `httpOnly`, `Secure`, `SameSite=Strict` cookie and never exposed to client‑side JavaScript. |
| FR-1.4 | The system shall restrict access to all Organization Portal pages and API endpoints to requests bearing a valid, non‑blacklisted access token. |
| FR-1.5 | The system shall support silent access‑token renewal via a dedicated endpoint that consumes the current refresh token and issues a new access/refresh pair (rotation). A previously used refresh token shall be rejected immediately if presented again. |
| FR-1.6 | The system shall lock out an account after 5 failed login attempts within 15 minutes, and lock out an IP address after 20 failed attempts within 15 minutes, each for a 30‑minute cooldown. |
| FR-1.7 | The system shall allow a logged‑in user to log out, which shall revoke their refresh token and blacklist their current access token's identifier for its remaining lifetime. |
| FR-1.8 | The system shall support a three‑step password reset flow: request reset code → verify code → set new password. The reset code shall expire **10 minutes** after generation and is single-use. Successfully resetting a password shall revoke all of that organization's existing refresh tokens (i.e., log out all sessions). |
| FR-1.9 | The system shall allow an unverified account to resend its verification code, and a password‑reset request to be resent, without revealing whether the underlying email is registered. |

#### 3.1.2 Token Strategy

- **Access Token:** Lifetime is fixed at **15 minutes** (binding, not illustrative). Stored in‑memory by the client, and sent in the `Authorization` header.
- **Refresh Token:** Lifetime is fixed at **7 days** (binding, not illustrative). Stored only in an `httpOnly`, `Secure`, `SameSite=Strict` cookie, and never touched by JavaScript.

Access tokens shall embed a unique identifier (`jti`) so that a specific token can be independently blacklisted before expiry. Refresh tokens shall be hashed before being persisted in the database; the raw token value shall never be stored.

#### 3.1.3 Authentication Flows

**Registration**
`POST /api/auth/register/` → validate input, reject if a verified account already exists with the same email; hash the password; generate a 6‑digit verification code; upsert the organization row; enqueue a verification email; set a signed `registration_verification` cookie; respond `201`.

**Email Verification**
`POST /api/auth/verify-email/` → read the email from the signed cookie; validate the submitted code; if the code matches and has not expired, mark the account as verified and clear the cookie; respond `200`.

**Password Reset (three‑step)**
Step 1 – request reset code; Step 2 – verify code (single‑use); Step 3 – set new password, delete all existing refresh tokens, and send a confirmation email.

**Login**
Check account lockout status → validate credentials → if successful, clear lockout counters and issue token pair; if failure, record attempt and reject with a generic error.

**Token Refresh (rotation)**
Verify the refresh token from the cookie; if valid, atomically delete the old token and create a new pair; replace the cookie; respond with the new access token.

**Logout**
Delete the refresh token from the database; blacklist the current access token's `jti`; clear the refresh token cookie.

#### 3.1.4 Rate Limiting

The following rate limits shall be enforced per IP address (or per user where applicable). The limits are chosen to prevent abuse while accommodating normal usage. Per NFR-1.11, these limits shall be keyed on a documented, deliberately-chosen definition of "client IP" (see NFR-1.11).

| Endpoint / Action | Limit |
|---|---|
| Registration (`/register`) | 5 requests per hour per IP |
| Email / password‑reset code verification | 10 requests per minute per IP |
| Resend verification / reset code | 3 requests per minute per IP |
| Password reset request | 5 requests per hour per IP |
| Login (`/login`) | 10 requests per minute per IP |
| Token refresh | 30 requests per minute per IP |
| Logout | 10 requests per minute per IP |

#### 3.1.5 Security Requirements

- Passwords shall be stored using a strong, salted hashing algorithm (e.g., PBKDF2, bcrypt, Argon2).
- Passwords shall be a minimum of **10 characters** and shall not be among the 1,000 most common breached passwords (a static common-password list is acceptable for this project's scale).
- All session‑related cookies shall be `httpOnly`, `SameSite=Strict`, and `Secure` in production.
- Verification and password-reset codes shall be stored in the database with the expiration times defined in FR-1.1 / FR-1.8, and shall be invalidated after a single successful use.
- Password reset shall invalidate all existing refresh tokens (effectively logging out all sessions).
- No internal secrets (password hashes, verification codes) shall be leaked in API responses.

### 3.2 Certificate Creation and Issuance

| ID | Requirement |
|---|---|
| FR-2.1 | The system shall provide a form for an authenticated organization user to enter certificate details: recipient name, recipient email, course/award title, issue date, and optional expiry date. |
| FR-2.1.1 | The system shall validate and sanitize all certificate text fields before they are persisted or hashed: reject or strip Unicode control and zero‑width characters, enforce a maximum length of **200 characters** for `recipient_name` and `course_title`, enforce RFC 5322 format and a maximum length of **254 characters** for `recipient_email`, reject HTML/script‑like content (`<`, `>`, and matching tag patterns), and trim leading/trailing whitespace. This validation occurs server‑side and applies to any data that will be used in the canonical hash, PDF rendering, or email. |
| FR-2.1.2 | The system shall reject a certificate creation request if a required field fails validation, and shall return a field‑level error message so the organization user can correct it. |
| FR-2.2 | The system shall generate a unique Certificate ID for every certificate created. |
| FR-2.2.1 | The system shall accept a client‑supplied `Idempotency-Key` header on certificate creation requests. A repeated submission with the same key (within a 24‑hour window) shall return the existing certificate record instead of creating a duplicate. If no key is supplied, the system shall still prevent exact duplicate submissions (same organization, recipient email, course title, and issue date) from creating a second record. |
| FR-2.3 | The system shall generate a downloadable PDF representation of the certificate, including the recipient's name, award title, issue date, Certificate ID, and a QR code linking to the public verification page. |
| FR-2.4 | The system shall compute a cryptographic hash (SHA‑256) of the certificate's canonical data upon issuance. |
| FR-2.5 | The system shall submit a transaction to the deployed smart contract to record the Certificate ID hash, certificate hash, issuer identifier, and issue timestamp on the blockchain. |
| FR-2.6 | The system shall store the resulting blockchain transaction hash alongside the certificate record in the off‑chain database. |
| FR-2.7 | The system shall not transition a certificate's status to `VALID` until the corresponding blockchain transaction has been confirmed. The initial creation request may return before confirmation is complete (HTTP 202), leaving the certificate in a `PENDING` state. |
| FR-2.8 | If the blockchain transaction underlying an issuance fails, the system shall set the certificate's status to `FAILED`, record a human‑readable failure reason, and surface this state visibly in the Organization Dashboard, rather than leaving the certificate silently `PENDING`. |
| FR-2.9 | The system shall provide a manual "Retry Issuance" action in the Organization Portal for any certificate in `FAILED` status, or in `PENDING` status for longer than **10 minutes** ("stale PENDING"), which re‑submits the anchor transaction without creating a duplicate database record. |
| FR-2.10 | The system shall log every blockchain interaction attempt (issuance and revocation), whether successful or not, including the error message if any, to a queryable log for debugging and audit purposes. |

### 3.3 Certificate Management (Organization View)

| ID | Requirement |
|---|---|
| FR-3.1 | The system shall display a list of all certificates issued by the logged‑in organization, including recipient name, Certificate ID, issue date, and current status. The displayed status shall reflect the denormalized value kept in the database, updated by background jobs (see §3.4). |
| FR-3.2 | The system shall allow the organization user to search or filter issued certificates (e.g., by recipient name or Certificate ID). |
| FR-3.3 | The system shall allow the organization user to view full details of a specific certificate, including its blockchain transaction reference. |
| FR-3.4 | The system shall allow the organization user to revoke a previously issued, non‑expired certificate, with a mandatory reason field. |
| FR-3.5 | The system shall update the certificate's status to "Revoked" immediately upon confirmation of a revocation action. |

### 3.4 Certificate Lifecycle (Expiration and Revocation)

| ID | Requirement |
|---|---|
| FR-4.1 | The system shall support an optional expiry date at the time of certificate creation. |
| FR-4.2 | The system shall automatically compute and display a certificate's status as "Expired" once the current date passes the certificate's expiry date, without requiring manual intervention. |
| FR-4.2.1 | A scheduled background task (at least once per day) shall update the stored `status` field of all `VALID` certificates whose `expiry_date` has passed to `EXPIRED`. This keeps list views fast. The **public verification page** shall always resolve expiry status live against the expiry date, so it never shows a stale value. |
| FR-4.3 | The system shall display exactly one of five statuses for any certificate at any time: `PENDING`, `VALID`, `EXPIRED`, `REVOKED`, or `FAILED`. |
| FR-4.4 | A revoked certificate shall remain marked "Revoked" permanently and shall not be reactivated through the standard portal interface. |

### 3.5 Public Certificate Verification

| ID | Requirement |
|---|---|
| FR-5.1 | The system shall provide a public page where any visitor can enter a Certificate ID to verify a certificate, without requiring login. |
| FR-5.2 | The system shall provide a mechanism to verify a certificate automatically when its QR code is scanned, by directing the scanner to a URL containing the Certificate ID. |
| FR-5.3 | Upon verification, the system shall recompute the certificate's hash from the stored certificate data and compare it against the hash recorded on the blockchain. |
| FR-5.4 | The system shall display the certificate's recipient name, award/course title, issue date, and current status (Valid / Expired / Revoked) on the verification result page. |
| FR-5.5 | The system shall display the associated blockchain transaction reference and a link to view it on a public block explorer. |
| FR-5.6 | The system shall display a clear tamper‑warning message if the recomputed hash does not match the on‑chain hash. |
| FR-5.7 | The system shall return a clear "not found" result if the entered Certificate ID does not exist in the system. |
| FR-5.8 | The public verification endpoint shall be rate‑limited to **30 requests per minute per IP address**. This protects the blockchain RPC provider from excessive traffic. |
| FR-5.9 | The system shall cache immutable on‑chain fields (`certHash`, `issuedAt`) indefinitely once first retrieved, so that repeated verifications of the same certificate do not each require a fresh RPC call. The `revoked` flag shall be cached for at most 60 seconds and invalidated when the organization's own revocation transaction confirms. This cache shall be implemented per NFR-1.10 (no external cache service). |

### 3.6 Email Notifications

| ID | Requirement |
|---|---|
| FR-6.1 | The system shall automatically send an email to the recipient's registered email address when a certificate's status transitions to `VALID` (i.e., after the blockchain transaction has been confirmed). |
| FR-6.2 | The notification email shall include the certificate PDF as a file attachment. |
| FR-6.3 | The system shall log the delivery status of each notification email and allow the organization user to resend it manually if delivery fails. |

---

## 4. External Interface Requirements

### 4.1 User Interfaces

- Organization Login page
- Organization Dashboard (list of issued certificates, search/filter)
- Certificate Creation Form
- Certificate Detail View (organization side, including blockchain reference and revoke action)
- Public Verification Page (Certificate ID entry form and results display)
- Certificate PDF template (recipient‑facing)

### 4.2 Hardware Interfaces

No dedicated hardware is required beyond a standard computing device with internet access and a camera‑enabled device (e.g., smartphone) for scanning QR codes.

### 4.3 Software Interfaces

| Interface | Purpose |
|---|---|
| Blockchain RPC Provider (Polygon Amoy) | Submit and read smart contract transactions |
| Smart Contract (`CertificateRegistry` on Amoy) | Store and retrieve certificate hash records and revocation flags |
| Email Delivery Service (SMTP / transactional email API) | Send certificate issuance and authentication (verification/reset) notifications |
| PDF Rendering Library | Render certificate HTML/CSS into a downloadable PDF |
| QR Code Generation Library | Encode the verification URL into a scannable QR image |
| Relational Database | Persist off‑chain certificate, organization, authentication, and log data; also serves as the cache backend per NFR-1.10 |

### 4.4 Communication Interfaces

- All client–server communication shall use HTTPS.
- The backend shall communicate with the blockchain network using JSON‑RPC over HTTPS.
- Email shall be sent via SMTP or an equivalent transactional email API.

---

## 5. Non-Functional Requirements

### 5.1 Security

| ID | Requirement |
|---|---|
| NFR-1.1 | Passwords shall be stored using a strong, salted hashing algorithm (e.g., PBKDF2, bcrypt, Argon2) and never in plaintext, and shall meet the minimum policy defined in §3.1.5. |
| NFR-1.2 | The blockchain wallet private key used to sign issuance/revocation transactions shall be stored server‑side only (e.g., environment variables / secrets manager) and never exposed to the client. |
| NFR-1.3 | All Organization Portal endpoints shall require a valid, non‑blacklisted access token. |
| NFR-1.4 | The public verification endpoints shall be read‑only and shall not expose any means of modifying certificate data. This shall be verified by an automated test asserting that all public verification routes reject non-GET HTTP methods. |
| NFR-1.5 | Every Organization Portal query shall be scoped to the authenticated user's own organization at the data‑access level, so that an organization can never read or act on another organization's certificates even if a valid certificate ID is supplied. |
| NFR-1.6 | Refresh tokens shall never be exposed to client‑side JavaScript (transported only via `httpOnly` cookies) and shall be single‑use: a rotated‑out refresh token shall be rejected immediately if presented again. |
| NFR-1.7 | The public verification endpoint shall enforce the per‑IP rate limit specified in FR‑5.8 to prevent abuse of the metered blockchain RPC provider. |
| NFR-1.8 | All certificate text input shall be validated and sanitized server‑side (FR‑2.1.1) before being persisted, hashed, rendered to PDF, or emailed. |
| NFR-1.9 | The smart contract's access-control logic — specifically that `revokeCertificate` reverts when `msg.sender` is not the original issuer, and that `issueCertificate` reverts for unauthorized callers — shall be verified by automated unit tests (e.g., Hardhat or Foundry) prior to any testnet deployment of a new contract version. |
| NFR-1.10 | Consistent with the "no external cache/session service" constraint (§2.4), any caching required by this system (e.g., rate-limit counters, FR-5.9 on-chain data cache) shall be implemented using either in-process memory (single-worker deployments only) or a database-backed cache table. A cache mechanism that silently loses correctness under a multi-process deployment (e.g., unscoped in-process memory used for rate limiting) shall not be considered compliant. |
| NFR-1.11 | Where rate limiting or lockout logic is keyed by client IP address, the system shall use a single, explicitly documented method for determining that address (e.g., trusting a specific `X-Forwarded-For` position only when behind a known reverse proxy, or the raw socket address otherwise), to prevent both spoofing-based bypass and false-positive lockouts of shared-IP clients. |
| NFR-1.12 | Any internal or administrative tooling not intended for public or recipient use (e.g., the Django admin site) shall be access-restricted (authentication required, limited to staff/superuser accounts) before any non-local deployment. |

### 5.2 Performance

| ID | Requirement |
|---|---|
| NFR-2.1 | Under a load of **10 concurrent public verification requests** against a warmed FR-5.9 cache, with a responsive blockchain RPC endpoint (median RPC response < 500ms), the system shall return a verification result within 3 seconds for at least 95% of requests. |
| NFR-2.2 | The certificate list view shall support pagination (default page size 25, configurable) to remain responsive as the number of issued certificates grows. |

### 5.3 Usability

- The public verification page shall be usable without any instructions, requiring only a Certificate ID or QR scan.
- The system shall provide clear success/error feedback for all key actions (issuance, revocation, verification).

### 5.4 Reliability and Availability

| ID | Requirement |
|---|---|
| NFR-4.1 | If the blockchain network is temporarily unavailable, the system shall queue or retry the issuance/revocation transaction via a background task, leaving the certificate in `PENDING`/`FAILED` status and informing the user, rather than silently failing. |
| NFR-4.2 | Off‑chain certificate data (database) shall remain the authoritative source for display content; the blockchain serves as the authoritative source for revocation status and tamper‑evidence, per the Authority Rule (§7.4.1). |

### 5.5 Maintainability

| ID | Requirement |
|---|---|
| NFR-5.1 | The codebase shall separate concerns across frontend, backend API, database layer, and blockchain‑interaction layer to support future maintenance. |
| NFR-5.2 | Configuration values (RPC URLs, contract address, email credentials) shall be externalized via environment variables, not hard‑coded. |

### 5.6 Scalability

| ID | Requirement |
|---|---|
| NFR-6.1 | The system's data model shall support multiple organizations without redesign, even if only one is used in the current demonstration. |

---

## 6. Data Requirements (Logical Data Model)

This section describes the core entities required for the system's database.

### 6.1 Organization

- organization_id (PK)
- name
- email (login identifier, unique)
- password_hash
- is_verified (boolean)
- verification_code / verification_code_expiry (nullable)
- password_reset_code / password_reset_code_expiry (nullable)
- wallet_address (blockchain address used to issue certificates)
- created_at

### 6.2 Certificate

- certificate_id (PK, unique, human‑readable/UUID)
- organization_id (FK → Organization)
- idempotency_key (nullable, unique per organization when present; used to detect duplicate submissions)
- recipient_name
- recipient_email
- course_title
- issue_date
- expiry_date (nullable)
- status (`PENDING` / `VALID` / `EXPIRED` / `REVOKED` / `FAILED`)
- failure_reason (nullable)
- certificate_hash (SHA‑256 of canonical certificate data)
- pdf_sha256 (SHA‑256 of the generated PDF at issuance time; informational only)
- blockchain_tx_hash (nullable)
- pdf_url / pdf_storage_reference
- created_at

### 6.3 Revocation Log

- revocation_id (PK)
- certificate_id (FK → Certificate)
- revoked_by (organization_id)
- reason
- revoked_at

### 6.4 Notification Log

- notification_id (PK)
- certificate_id (FK → Certificate)
- recipient_email
- status (Sent / Failed)
- sent_at

### 6.5 Refresh Token

- token_id (PK)
- organization_id (FK → Organization)
- token_hash (SHA‑256 of the raw refresh token)
- expires_at
- created_at

### 6.6 Login Attempt

- attempt_id (PK)
- email (indexed)
- ip_address (indexed)
- succeeded (boolean)
- attempted_at

### 6.7 Blockchain Interaction Log

- log_id (PK)
- certificate_id (FK → Certificate, nullable)
- action (`ISSUE` / `REVOKE` / `VERIFY_READ`)
- succeeded (boolean)
- error_message (nullable)
- tx_hash (nullable)
- attempted_at

### 6.8 Cache Entry (supports NFR-1.10)

- cache_key (PK)
- cache_value (text/JSON)
- expires_at (nullable — null means indefinite, per FR-5.9's immutable-field caching)

**Relationships:** One Organization issues many Certificates (1–N). One Certificate has at most one Revocation Log entry (1–0..1). One Certificate may have multiple Notification Log entries (1–N). One Organization may have multiple active Refresh Tokens (1–N). Login Attempt rows are not foreign‑keyed to Organization (failed attempts with unrecognized emails must still be recorded). One Certificate may have multiple Blockchain Interaction Log entries (1–N). Cache Entry rows are not foreign-keyed to any other entity.

---

## 7. Blockchain Architecture and Smart Contract Design

### 7.1 Design Rationale

Full certificate documents will not be stored on‑chain. The system follows a **hash‑anchoring pattern**: certificate data is stored off‑chain, and only a cryptographic hash of that data — plus minimal identifying metadata — is written to a smart contract. Verification compares a recomputed hash against the immutable on‑chain record.

### 7.2 Network Choice

The smart contract will be deployed on **Polygon Amoy** (chainId `80002`), a public EVM‑compatible test network. Amoy is chosen for its fast block times, low friction for obtaining test tokens, and the ability to generate real, publicly viewable transactions on a block explorer.

### 7.2.1 Canonical Hashing Specification

The system shall compute the on‑chain certificate hash from a deterministic, JSON‑based canonical representation of the certificate data fields. The canonical form must be identical between issuance and verification; therefore it shall be defined in exactly one location in the codebase. The canonical representation shall include:
- A format version number (`v: 1`)
- Certificate ID, organization ID, recipient name (trimmed), recipient email (lowercased, trimmed), course title (trimmed), issue date (ISO 8601 date), and expiry date (ISO 8601 date, or null).
- The JSON object shall be serialized with sorted keys, compact separators, and UTF‑8 encoding.

The on‑chain hash is `sha256(canonical‑bytes)`. Note that the hash is computed over the certificate's **data fields**, not the rendered PDF, because PDF rendering is not byte‑reproducible across environments.

### 7.3 Smart Contract Responsibilities

- Store a mapping from a hashed Certificate ID (`bytes32`) to a record containing: certificate hash, issuer address, issue timestamp, and revocation flag.
- Provide a function to add a new certificate record (callable only by an authorized issuer address).
- Provide a function to update a certificate's status to Revoked (callable **only by the original issuer** of that certificate).
- Provide a read‑only (view) function to retrieve a certificate record by hashed Certificate ID.
- Emit events on issuance and revocation for auditability.
- Per NFR-1.9, all of the above access-control behaviors shall have corresponding automated unit tests prior to testnet deployment.

### 7.4 Contract Structure

The contract shall use `bytes32` keys (derived by hashing the Certificate ID with `keccak256`) rather than string keys, to reduce gas costs and enable efficient event indexing.

| Element | Description |
|---|---|
| `struct CertificateRecord` | `{ bytes32 certHash; address issuer; uint256 issuedAt; bool revoked; }` |
| `mapping(bytes32 => CertificateRecord) private certificates` | Maps hashed Certificate ID to its record |
| `function issueCertificate(bytes32 certIdHash, bytes32 certHash) external onlyIssuer` | Adds a new record; restricted to authorized issuer addresses |
| `function revokeCertificate(bytes32 certIdHash) external` | Marks a record as revoked; must revert if `msg.sender` does not match the `issuer` stored in the certificate's record |
| `function getCertificate(bytes32 certIdHash) external view returns (CertificateRecord memory)` | Public read function for verification |
| `event CertificateIssued(bytes32 indexed certIdHash, bytes32 certHash, address indexed issuer)` | Emitted on issuance |
| `event CertificateRevoked(bytes32 indexed certIdHash)` | Emitted on revocation |

### 7.4.1 Authority Rule

The system defines a single rule to resolve any disagreement between the database and the blockchain: **the blockchain is authoritative for the `revoked` flag; the database is authoritative for every other displayed field.** The verification flow always reads the revocation status from the on‑chain record, never from the database.

### 7.5 Issuance Flow (Asynchronous)

1. The organization user submits the certificate creation form; the API returns immediately (HTTP 202) after steps 2‑4.
2. The backend generates the Certificate ID, canonical data, and SHA‑256 hash.
3. The backend renders the PDF and QR code synchronously.
4. The backend inserts the certificate row with status `PENDING` and returns the Certificate ID.
5. A background task signs and sends the `issueCertificate` transaction.
6. On confirmation, the task updates the row: sets `blockchain_tx_hash` and transitions status to `VALID`.
7. The system sends the recipient notification email **only after** status becomes `VALID`.
8. The Organization Portal allows the user to see the `PENDING → VALID` transition; if the transaction fails, the row is marked `FAILED`. If the row remains `PENDING` for longer than the threshold in FR-2.9, it becomes eligible for manual retry.

To prevent nonce collisions, all blockchain write operations shall be serialized through a single background worker.

### 7.6 Verification Flow

1. A user submits a Certificate ID via the public verification page or QR scan.
2. The backend retrieves the certificate record from the off‑chain database.
3. The backend recomputes the SHA‑256 hash of the certificate data using the canonical function.
4. The backend queries the smart contract's `getCertificate` function using the hashed Certificate ID. Immutable fields are served from cache; the `revoked` flag is cached briefly (per FR-5.9 / NFR-1.10).
5. The backend compares the recomputed hash against the on‑chain `certHash`. The on‑chain `revoked` flag determines revocation; the stored `expiry_date` determines expiry.
6. The system resolves exactly one of five outcomes:
   - **NOT FOUND** – no certificate with that ID.
   - **VALID** – hash matches, not revoked, within expiry.
   - **EXPIRED** – hash matches, past expiry date.
   - **REVOKED** – on‑chain `revoked` flag is true.
   - **TAMPERED** – recomputed hash does not match the on‑chain hash.

---

## 8. Use Cases

### 8.1 Use Case: Issue Certificate

| Field | Detail |
|---|---|
| Actor | Organization Staff (authenticated) |
| Precondition | User is logged in to the Organization Portal |
| Trigger | User submits the certificate creation form |
| Main Flow | 1) User enters recipient and certificate details. 2) System generates a Certificate ID, PDF, and QR code. 3) System computes the certificate hash and stores the record with status `PENDING`, returning HTTP 202. 4) A background task submits the transaction to the smart contract. 5) On confirmation, the task updates the record's transaction reference and status to `VALID`. 6) System sends a notification email to the recipient only after status becomes `VALID`. |
| Alternate Flow | If the blockchain transaction fails, the record is marked `FAILED` and can be retried manually. If an idempotency key is supplied, a duplicate request returns the existing record. |
| Postcondition | A new certificate record exists; once its background transaction confirms, its status is "Valid", it is recorded on‑chain, and the recipient has been notified. |

### 8.2 Use Case: Verify Certificate

| Field | Detail |
|---|---|
| Actor | Public Verifier (unauthenticated) |
| Precondition | None – page is publicly accessible |
| Trigger | User enters a Certificate ID or scans a certificate's QR code |
| Main Flow | 1) System looks up the certificate. 2) System recomputes the hash and queries the blockchain. 3) System compares results and computes the final status. 4) System displays certificate details, status, and blockchain transaction link. |
| Alternate Flow | If the Certificate ID does not exist, the system displays a clear "not found" message. If the hash does not match, the system displays a tamper warning. |
| Postcondition | The verifier has an accurate, evidence‑backed view of the certificate's authenticity and status. |

### 8.3 Use Case: Revoke Certificate

| Field | Detail |
|---|---|
| Actor | Organization Staff (authenticated) |
| Precondition | User is logged in; certificate exists and is not already revoked |
| Trigger | User selects "Revoke" on a certificate and provides a reason |
| Main Flow | 1) System submits a revocation transaction to the smart contract. 2) System updates the certificate's status to "Revoked" in the database. 3) System logs the revocation reason and timestamp. |
| Postcondition | The certificate's status is permanently "Revoked" and reflected in both the database and the blockchain. |

---

## 9. Assumptions, Dependencies, and Constraints (Summary)

- This is an academic capstone project developed individually; the scope reflects what is achievable by one developer within the project timeline.
- A public test blockchain network will be used instead of mainnet, for cost reasons; this will be clearly documented and justified in the final report.
- Only a single organization account is required for demonstration purposes, though the data model supports multiple organizations.
- Free‑tier or sandbox services will be used for email delivery and blockchain RPC access.

---

## 10. Future Enhancements (Out of Current Scope)

- Multi‑admin / role‑based access within a single organization.
- Support for multiple organizations with independent branding on issued certificates.
- Storing certificate PDFs on IPFS for fully decentralized retrieval.
- Bulk certificate issuance via CSV upload.
- A mobile app for scanning and verifying certificates offline‑first.
- Deployment to a production mainnet with gas‑cost optimization.

---

## 11. Known Limitations and Design Trade-offs

| Area | Limitation / Risk | Resolution Adopted |
|---|---|---|
| Input handling | User‑supplied text fields are permanently anchored on‑chain via their hash; unsanitized input could corrupt PDF rendering or produce confusing hashes. | Server‑side validation and sanitization before any field is hashed or rendered (FR‑2.1.1, FR‑2.1.2, NFR‑1.8). |
| Duplicate submissions | A double‑click or retried request could create duplicate records and on‑chain transactions. | Idempotency key (FR‑2.2.1); uniqueness constraint on key fields. |
| Public endpoint abuse | The verification endpoint triggers a metered RPC call; scripted abuse could exhaust the RPC quota. | Per‑IP rate limit of 30 req/min (FR‑5.8) plus caching of immutable on‑chain fields (FR‑5.9), with the cache mechanism constrained by NFR-1.10. |
| Blockchain failure visibility | A failed transaction without user feedback could leave a certificate stuck as `PENDING`. | `FAILED` status with reason, manual retry after a defined stale-PENDING threshold, and full interaction logging (FR‑2.8, FR‑2.9, FR‑2.10). |
| Expiry‑status consistency | Reading status live from the chain for every dashboard row would be slow. | Background task updates stored status daily for list views; verification page always resolves expiry live (FR‑4.2.1). |
| Single hot wallet | All on‑chain writes are signed by one server‑held wallet. Acceptable for a single‑organization demo but would need a per‑org signing strategy to scale. | Out of scope; noted for future enhancement (§10). |
| No external cache | All authentication state (lockout counters, token blacklist, refresh tokens) and rate-limit/verification caching is stored in the relational database. | Deliberate choice for this project scale (NFR-1.10); adequate for single‑process deployment via in-process cache, or multi-process deployment via database-backed cache. If the system grows substantially, a dedicated cache service would be considered. |
| Smart contract change risk | A bug in access-control logic (e.g., unauthorized revocation) is expensive to fix once real transactions exist against a deployed contract. | Mandatory automated unit testing of access-control paths prior to deployment (NFR-1.9). |
| Reverse-proxy IP spoofing | If the app is deployed behind a proxy/load balancer without a defined trust policy, IP-based rate limits and lockouts can be bypassed or falsely triggered. | Single, documented IP-resolution method (NFR-1.11). |
| Admin tooling exposure | Django's built-in admin interface, enabled for development convenience, could expose certificate/organization data if left open in a non-local deployment. | Mandatory access restriction before non-local deployment (NFR-1.12). |

---

*End of Document*