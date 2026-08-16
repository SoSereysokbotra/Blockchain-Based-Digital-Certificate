# Blockchain-Based Digital Certificate Issuing Platform (BCIP)

### Capstone Project Submission

| Field | Detail |
|---|---|
| **Student Name** | `[FILL IN]` |
| **Student ID** | `[FILL IN]` |
| **Course / Module** | `[FILL IN]` |
| **Instructor** | `[FILL IN]` |
| **Project Type** | Individual |
| **Submission Date** | `[FILL IN]` |
| **Repository** | https://github.com/SoSereysokbotra/Blockchain-Based-Digital-Certificate |
| **Demo Video** | `[FILL IN — see §11]` |

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [System Architecture](#2-system-architecture)
3. [User Flow / System Flow](#3-user-flow--system-flow)
4. [Database Design (ER Diagram)](#4-database-design-er-diagram)
5. [Blockchain Architecture](#5-blockchain-architecture)
6. [Smart Contract Design](#6-smart-contract-design)
7. [User Interface Design](#7-user-interface-design)
8. [Implementation Summary](#8-implementation-summary)
9. [Public GitHub Repository](#9-public-github-repository)
10. [Individual Contribution Report](#10-individual-contribution-report)
11. [Public Demo Video](#11-public-demo-video)

---

## 1. System Overview

### 1.1 The problem

A conventional certificate system stores credentials in a database controlled by the issuing institution. When an employer verifies a certificate, the server reads a row and reports what it says. The employer is therefore **trusting the institution's database integrity** — they have no way to detect whether a record was altered after issuance.

A database can prove what it currently contains. It cannot prove that nothing has changed. That gap is what this project addresses.

### 1.2 The solution

BCIP applies the **hash-anchoring pattern**. At issuance, the system computes a SHA-256 hash over the certificate's canonical data and writes only that hash — plus minimal metadata — to a smart contract on a public blockchain. Full certificate content remains in PostgreSQL.

Verification recomputes the hash from the current database record and compares it against the immutable on-chain value:

- **Match** → the record is unaltered since issuance
- **Mismatch** → the database was modified; the certificate is reported as `TAMPERED`

Because the on-chain value cannot be rewritten by the institution or by anyone who compromises its systems, a third party can detect tampering **without trusting the issuer**.

### 1.3 Scope of the guarantee

The system makes a precise and deliberately limited claim. When verification returns `VALID`, it asserts:

> The certificate data in the database today produces the same hash that was anchored on-chain at issuance, that record was created by an authorised issuer, and it has not been revoked or expired.

It does **not** assert that the recipient genuinely completed the course. No software can establish that. The issuing institution vouches for the content; the blockchain guarantees the content has not silently changed since. This distinction is stated explicitly because it defines the system's actual security value.

### 1.4 User classes

| Class | Authentication | Capability |
|---|---|---|
| **Organisation** | Email + password, JWT session | Issue, list, search, view, revoke, retry certificates |
| **Recipient** | None | Receives a PDF certificate by email |
| **Verifier** | None | Checks any certificate by ID or QR scan |

Only the issuing organisation holds an account. Recipients are stored as `recipient_name` and `recipient_email` fields on the certificate record — they are not users of the system. This reflects the real-world case: a university issues thousands of certificates annually, and requiring each graduate and each employer to register would be impractical.

### 1.5 Technology stack

| Layer | Technology |
|---|---|
| Frontend | React 19, Vite 8, TypeScript, React Router 7, Axios |
| Backend | Django 5.0, Django REST Framework 3.15 |
| Database | PostgreSQL 15 |
| Authentication | SimpleJWT (access + refresh token rotation) |
| Background jobs | django-q2 (single-worker cluster) |
| Smart contract | Solidity 0.8.20 |
| Contract tooling | Hardhat 3, Ethers 6, Mocha, Chai |
| Blockchain network | Polygon Amoy testnet (chain ID 80002) |
| Python–chain bridge | web3.py 6 |
| PDF generation | WeasyPrint 61 |
| QR generation | qrcode 7 |
| Email | Django SMTP backend |
| Containerisation | Docker Compose |

---

## 2. System Architecture

### 2.1 Layered view

```
┌───────────────────────────────────────────────────────────────────────────┐
│ CLIENT — React (Vite) single-page application                             │
│                                                                           │
│  ┌──────────────────────────────┐   ┌──────────────────────────────────┐  │
│  │ Organisation Portal          │   │ Public Verification Portal       │  │
│  │ authenticated · JWT          │   │ no authentication · read-only    │  │
│  │ issue · list · revoke        │   │ enter ID or scan QR              │  │
│  └──────────────┬───────────────┘   └────────────────┬─────────────────┘  │
└─────────────────┼────────────────────────────────────┼────────────────────┘
                  │ HTTPS · REST + JWT                 │ HTTPS · REST (public)
                  ▼                                    ▼
┌───────────────────────────────────────────────────────────────────────────┐
│ APPLICATION — Django REST Framework                                       │
│  All querysets scoped to request.user.organization (NFR-1.5)              │
│                                                                           │
│  ┌───────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐   │
│  │ accounts  │  │ certificates │  │ verification │  │ notifications   │   │
│  │ auth, JWT │  │ hash · PDF   │  │ compare      │  │ email + log     │   │
│  │ lockout   │  │ WeasyPrint   │  │ hashes       │  │                 │   │
│  └─────┬─────┘  └──────┬───────┘  └──────┬───────┘  └────────┬────────┘   │
│        │  ⊘            │                 │                   │  ⊘        │
│        │  no chain     ▼                 ▼                   │  no chain │
│        │        ┌──────────────────────────────────┐         │           │
│        │        │ blockchain                       │         │           │
│        │        │ web3.py · signer · nonce lock    │         │           │
│        │        │ THE ONLY MODULE THAT IMPORTS web3│         │           │
│        │        └──────────────┬───────────────────┘         │           │
└────────┼───────────────────────┼─────────────────────────────┼───────────┘
         │ Django ORM            │ signed tx      │ view call  │ SMTP
         │ (all four apps)       ▼                │            ▼
┌────────▼──────────────┐  ┌─────────────────────────────┐  ┌─────────────┐
│ OFF-CHAIN             │  │ ON-CHAIN                    │  │ EXTERNAL    │
│ authoritative for     │  │ authoritative for integrity │  │             │
│ CONTENT               │  │                             │  │  SMTP       │
│                       │  │  JSON-RPC provider          │  │  provider   │
│  PostgreSQL           │  │        │                    │  │             │
│   Organization        │  │        ▼                    │  └─────────────┘
│   Certificate         │  │  CertificateRegistry.sol    │
│   RevocationLog       │  │   mapping(bytes32 =>        │  WeasyPrint and
│   NotificationLog     │  │     CertificateRecord)      │  qrcode are
│   RefreshToken        │  │   certHash · issuer ·       │  LIBRARIES, not
│   LoginAttempt        │  │   issuedAt · revoked        │  services — they
│   BlockchainLog       │  │                             │  run in-process
│   cache_entries       │  │  Polygon Amoy               │
└───────────────────────┘  └─────────────────────────────┘
      mutable · private        immutable · public
      ▲                                        ▲
      └──── only certId + 32-byte hash ────────┘
                 cross this boundary
```

### 2.2 Architectural decisions

**Isolated blockchain layer.** Every contract call passes through a single Django app (`blockchain`). No other module imports `web3`. This satisfies SRS §5.5 (separation of concerns) and makes the requirement that the private key never leaves the server auditable by inspecting one file rather than the whole codebase.

**Asynchronous anchoring.** Blockchain confirmation is unbounded in time. Holding an HTTP request open while waiting would exhaust the worker pool under modest concurrency. Certificate creation therefore returns HTTP 202 immediately with status `PENDING`, and a background worker performs the anchor.

**Single-worker background cluster.** All on-chain writes are signed by one wallet, and each transaction carries a sequential nonce. Two concurrent workers would read the same nonce and one transaction would be silently dropped, stranding a certificate as `PENDING`. Configuring `workers: 1` removes this race by construction. The cost — issuances serialising at roughly one confirmation each — is an accepted trade-off at this project's scale.

**Database-backed cache.** Rate-limit counters and lockout state use Django's `DatabaseCache` rather than the default in-process cache. An in-memory cache is per-process, so a "5 attempts" limit would become an effective 5 × *N* across *N* worker processes. A shared cache makes the documented thresholds correct.

**Tenant isolation at the queryset.** Organisation scoping is enforced in a single `get_queryset()` choke point rather than per-handler, so endpoints added later inherit it. Cross-organisation access returns 404 rather than 403, since confirming that an identifier exists is itself a disclosure.

---

## 3. User Flow / System Flow

### 3.1 Certificate issuance (FR-2.1 – FR-2.8)

```
Organisation      certificates      PostgreSQL      blockchain      Registry.sol
     │                  │                │              │                │
  1  │ POST /api/certificates/           │              │                │
     ├─────────────────►│                │              │                │
     │                  │                │              │                │
  2  │            validate input         │              │                │
     │            generate certId        │              │                │
     │            canonical JSON→sha256  │              │                │
     │            render PDF + QR        │              │                │
     │                  │                │              │                │
  3  │                  │ INSERT status=PENDING         │                │
     │                  ├───────────────►│              │                │
     │                  │                │              │                │
  4  │ ◄────────────────┤ HTTP 202 Accepted             │                │
     │   (browser is released here — no waiting)        │                │
     │                  │                │              │                │
  5  │                  │ anchor(certId, certHash)      │                │
     │                  ├──────────────────────────────►│                │
     │                  │                │              │ signed tx      │
  6  │                  │                │              ├───────────────►│
     │                  │                │              │                │
  7  │                  │                │              │◄───────────────┤
     │                  │                │              │  receipt       │
  8  │                  │◄──────────────────────────────┤                │
     │                  │ UPDATE tx_hash, status=VALID  │                │
     │                  ├───────────────►│              │                │
     │                  │                │              │                │
  9  │                  │ queue issuance email to recipient              │
     │                  ├────────────────────────────────────────────────►
```

Steps 5–8 are the only ones with unbounded latency. If step 6 or 7 fails, the certificate becomes `FAILED` with the reason recorded, and step 5 can be retried without creating a duplicate record.

### 3.2 Certificate status lifecycle

```
                      ┌──────────────────┐
    issue form ──────►│     PENDING      │
                      │ waiting on chain │
                      └────┬────────┬────┘
                           │        │
            tx confirmed   │        │  tx failed
                           ▼        ▼
                    ┌──────────┐  ┌──────────┐
                    │  VALID   │  │  FAILED  │
                    │ anchored │  │retryable │──── retry ──┐
                    └──┬────┬──┘  └──────────┘             │
                       │    │                              │
       expiry passes   │    │  issuer revokes              │
                       ▼    ▼                              ▼
              ┌──────────┐  ┌──────────┐            back to PENDING
              │ EXPIRED  │  │ REVOKED  │
              │ genuine, │  │permanent │
              │ past date│  │(FR-4.4)  │
              └──────────┘  └──────────┘
```

`REVOKED` is terminal — no transition leaves it. Only `PENDING → VALID` depends on the blockchain; all other transitions are local state changes.

### 3.3 Public verification (FR-5.1 – FR-5.7, SRS §7.6)

```
                    Certificate ID (typed, or from QR link)
                                    │
                 ┌──────────────────┴──────────────────┐
                 ▼                                     ▼
     ┌───────────────────────┐            ┌────────────────────────┐
     │ OFF-CHAIN PATH        │            │ ON-CHAIN PATH          │
     │ read the DB row       │            │ getCertificate() view  │
     │ recompute sha256 NOW  │            │ hash written at issue  │
     └───────────┬───────────┘            └───────────┬────────────┘
                 │                                    │
                 └──────────────┬─────────────────────┘
                                ▼
                   ┌─────────────────────────┐
                   │ Do the hashes match?    │
                   │ then: revoked? expired? │
                   └────────────┬────────────┘
                                │
   ┌──────────┬─────────────┬───┴────────┬──────────────┬─────────────┐
   ▼          ▼             ▼            ▼              ▼             ▼
NOT_FOUND   VALID       EXPIRED      REVOKED       TAMPERED     UNVERIFIED
no such    match,      match, past   on-chain      hash         chain
record     active      expiry_date   flag true     MISMATCH     unreachable
```

The left path can be forged by anyone with database access; the right path cannot be forged by anyone. Comparing them is what makes the result trustworthy.

`TAMPERED` and `UNVERIFIED` are deliberately distinct outcomes. "We could not reach the blockchain" is a different claim from "this record was altered", and conflating them would accuse an honest issuer of forgery during a network outage.

### 3.4 Authentication flows

| Flow | Endpoint | Key controls |
|---|---|---|
| Registration | `POST /api/auth/register/` | Password ≥10 chars, checked against common-password list |
| Email verification | `POST /api/auth/verify-email/` | 6-digit code, 10-minute expiry, single use, bound to the account |
| Login | `POST /api/auth/login/` | Lockout checked before password; identical response for unknown vs wrong password |
| Token refresh | `POST /api/auth/refresh-token/` | Rotation; reuse of a spent token revokes the whole session family |
| Logout | `POST /api/auth/logout/` | Refresh token revoked server-side and blacklisted |
| Password reset | 3-step code flow | Reset revokes all existing sessions |

**Account lockout (FR-1.6):** 5 failed attempts on one account, or 20 from one IP address, within a 15-minute window triggers a 30-minute cooldown measured from the most recent failure.

---

## 4. Database Design (ER Diagram)

### 4.1 Entity-relationship diagram

```
┌────────────────────────────────┐
│ Organization                   │  (AUTH_USER_MODEL)
├────────────────────────────────┤
│ PK id                 UUID     │
│    name               varchar  │
│ UQ email              varchar  │
│    password           varchar  │  Argon2 hash — never plaintext
│    wallet_address     varchar  │
│    is_verified        boolean  │
│    is_active          boolean  │
│    created_at         datetime │
└──┬────┬────┬────┬──────────────┘
   │1   │1   │1   │1
   │    │    │    │
   │    │    │    └──────────────────────────┐
   │    │    └──────────────┐                │
   │    └───────┐           │                │
   │N           │N          │N               │N
┌──▼─────────────────────┐ ┌▼──────────────┐ ┌▼─────────────────┐
│ Certificate            │ │ RefreshToken  │ │ EmailVerification│
├────────────────────────┤ ├───────────────┤ │ Code             │
│ PK id           bigint │ │ PK id         │ ├──────────────────┤
│ UQ certificate_id      │ │ FK org        │ │ PK id            │
│ FK organization_id     │ │ UQ token_hash │ │ FK organization  │
│    recipient_name      │ │    jti        │ │    code (6)      │
│    recipient_email     │ │    expires_at │ │    expires_at    │
│    course_title        │ │    revoked_at │ │    used_at       │
│    issue_date   date   │ └───────────────┘ └──────────────────┘
│    expiry_date  date?  │
│    status       enum   │ ┌───────────────┐ ┌──────────────────┐
│    certificate_hash    │ │ LoginAttempt  │ │ PasswordReset    │
│    pdf_sha256          │ ├───────────────┤ │ Code             │
│    blockchain_tx_hash  │ │ PK id         │ ├──────────────────┤
│    blockchain_block_no │ │ IX email      │ │ PK id            │
│    anchored_at         │ │ IX ip_address │ │ FK organization  │
│    pdf_url             │ │    successful │ │    code (6)      │
│    failure_reason      │ │ IX attempted  │ │    expires_at    │
│    issuance_attempts   │ └───────────────┘ │    used_at       │
│    idempotency_key     │  (not FK-linked:  └──────────────────┘
│    created_at          │   records attempts
│    updated_at          │   on accounts that
└──┬─────────┬────────┬──┘   may not exist)
   │1..0/1   │1..N    │1..N
   ▼         ▼        ▼
┌──────────────┐ ┌──────────────────┐ ┌───────────────────────┐
│RevocationLog │ │ NotificationLog  │ │BlockchainInteraction  │
├──────────────┤ ├──────────────────┤ │Log                    │
│ PK id        │ │ PK id            │ ├───────────────────────┤
│ UQ FK cert   │ │ FK certificate?  │ │ PK id                 │
│ FK revoked_by│ │    kind    enum  │ │ FK certificate?       │
│    reason    │ │    recipient_mail│ │    certificate_pub_id │
│    revoked_at│ │    status  enum  │ │    interaction_type   │
│    tx_hash   │ │    error_message │ │    succeeded  boolean │
│    confirmed │ │    attempt  int  │ │    tx_hash            │
│    _on_chain │ │    sent_at       │ │    block_number       │
└──────────────┘ └──────────────────┘ │    gas_used           │
                                       │    error_message      │
┌────────────────────┐                 │    duration_ms        │
│ cache_entries      │                 │    created_at         │
│ (DatabaseCache)    │                 └───────────────────────┘
│ rate limits + FR-5.9│
│ on-chain read cache │
└────────────────────┘
```

### 4.2 Relationships

| Relationship | Cardinality | Rationale |
|---|---|---|
| Organization → Certificate | 1 : N | An institution issues many certificates |
| Certificate → RevocationLog | 1 : 0..1 | A certificate is revoked at most once (`OneToOneField`) |
| Certificate → NotificationLog | 1 : N | Original send plus any manual resends |
| Certificate → BlockchainInteractionLog | 1 : N | One row per attempt, successful or failed (FR-2.10) |
| Organization → RefreshToken | 1 : N | Multiple concurrent sessions per organisation |
| LoginAttempt | *not linked* | Deliberately unlinked — the IP rule must count failures against email addresses that do not exist |

### 4.3 Design notes

**Denormalised `status`.** Certificate status is stored rather than derived so list views remain fast and paginated queries can filter on an indexed column. A scheduled daily job transitions expired certificates.

**Idempotency.** `idempotency_key` carries a partial unique constraint scoped to `(organization, idempotency_key)`. This prevents a retried request from creating a duplicate certificate — which would additionally revert on-chain — while keeping keys from colliding between tenants.

**Two distinct hashes.** `certificate_hash` is computed over canonical *data* and is anchored on-chain. `pdf_sha256` is computed over the rendered PDF bytes and is never anchored. This separation is necessary because WeasyPrint output is not byte-reproducible — it embeds a creation timestamp and may subset fonts differently between runs — so re-rendering and re-hashing would produce a different digest for identical data.

**Indexes.** Composite indexes on `(organization, -created_at)`, `(organization, status)` and `(status, created_at)` support the dashboard's default listing, status filter and the stale-`PENDING` sweep respectively. `LoginAttempt` is indexed on both `email` and `ip_address` with `attempted_at`.

---

## 5. Blockchain Architecture

### 5.1 Network selection

The contract targets **Polygon Amoy**, a public EVM-compatible testnet (chain ID 80002).

| Criterion | Rationale |
|---|---|
| Cost | Faucet-issued test tokens; no budget required for an academic project |
| Public verifiability | Transactions are viewable on a public explorer by any third party |
| EVM compatibility | Standard Solidity toolchain, and portable to mainnet unchanged |
| Confirmation time | ~2-second blocks, acceptable for asynchronous issuance |

**Acknowledged limitation.** Testnets carry no persistence guarantee and may be reset by their operators. A production deployment issuing credentials intended to last decades would target Polygon mainnet. The architecture requires no code change to do so — only configuration.

### 5.2 On-chain / off-chain split

| Stored on-chain | Stored off-chain (PostgreSQL) |
|---|---|
| `certHash` — 32-byte SHA-256 digest | Recipient name, email |
| `issuer` — issuing wallet address | Course title, issue and expiry dates |
| `issuedAt` — block timestamp | The rendered PDF |
| `revoked` — boolean flag | Revocation reason, notification history |

Personal data is never written to the chain. This is a privacy requirement, not only a cost optimisation: on-chain data is public and permanent, so a recipient's name could never be deleted or corrected. A hash reveals nothing about its input while still detecting any change to it.

### 5.3 Key derivation

Certificates are keyed on-chain by `keccak256(certificate_id)`. The human-readable identifier never leaves the database.

```
Django:   Web3.keccak(text="CERT-5880CC998BDF")
Solidity: mapping(bytes32 => CertificateRecord)
```

### 5.4 Canonical hashing (SRS §7.2.1)

The anchored hash is computed over a frozen, versioned serialisation, implemented in exactly one function that both issuance and verification import:

```json
{"certId":"CERT-7F3A9B2E4C81","courseTitle":"Introduction to Blockchain",
 "expiryDate":"2027-08-14","issueDate":"2026-08-14","orgId":"a1e7fc06-…",
 "recipientEmail":"ada@example.com","recipientName":"Ada Lovelace","v":1}
```

SHA-256 → `0xdb236af434fe0ec399d5733cfa4e3b924b33d171161e5268c58aef632f72a751`

Changing only `courseTitle` to `"Advanced Blockchain Engineering"` yields:

`0xcbc7a292a065a7b7534099f1aeff1467d16b7a49ebe2d78dd686876b267169d7`

The serialisation rules are load-bearing and any change to them invalidates every previously anchored certificate:

- Keys sorted alphabetically — Python dictionary order is insertion order, so a refactor that reorders the literal would otherwise change every hash
- Separators `(',', ':')` — the `json.dumps` default inserts spaces
- Dates as `YYYY-MM-DD` via `.isoformat()`, never `str(datetime)`
- Absent expiry is `null`, never `""` — these hash differently
- Text NFC-normalised at input, because `é` has two Unicode encodings that hash differently
- A `v` field versions the format so a future change can be migrated rather than silently breaking

### 5.5 Transaction signing and key custody

The backend holds a single hot wallet whose private key is supplied via environment variable and never transmitted to any client (NFR-1.2). The platform — not the issuing organisation — pays transaction fees, so organisations require no cryptocurrency knowledge and interact only with a conventional email-and-password account.

Nonce management is handled by serialising all writes through a single background worker, with an additional in-process lock guarding the read-nonce → sign → send sequence.

---

## 6. Smart Contract Design

### 6.1 Contract structure

```solidity
contract CertificateRegistry {
    struct CertificateRecord {
        bytes32 certHash;      // SHA-256 of canonical certificate data
        address issuer;        // wallet that issued it
        uint256 issuedAt;      // block timestamp
        bool    revoked;       // revocation flag
    }

    address public immutable owner;
    mapping(address => bool) public authorizedIssuers;
    mapping(bytes32 => CertificateRecord) private certificates;
}
```

### 6.2 Interface

| Function | Access | Purpose |
|---|---|---|
| `issueCertificate(bytes32 certIdHash, bytes32 certHash)` | Authorised issuers | Anchor a new certificate |
| `revokeCertificate(bytes32 certIdHash)` | **Original issuer only** | Set the revoked flag |
| `getCertificate(bytes32 certIdHash)` | Public `view` | Read a record — free, no gas |
| `exists(bytes32 certIdHash)` | Public `view` | Existence check |
| `authorizeIssuer(address)` | Owner | Grant issuing rights |
| `deauthorizeIssuer(address)` | Owner | Revoke issuing rights |

**Events:** `CertificateIssued(bytes32 indexed certIdHash, bytes32 certHash, address indexed issuer, uint256 issuedAt)`, `CertificateRevoked(bytes32 indexed certIdHash, address indexed issuer)`, plus issuer administration events.

**Custom errors:** `NotOwner`, `NotAuthorizedIssuer`, `CertificateAlreadyExists`, `CertificateNotFound`, `NotOriginalIssuer`, `AlreadyRevoked`, `ZeroCertHash`, `ZeroAddress`.

### 6.3 Design decisions

**`bytes32` mapping keys rather than `string`.** A dynamic `string` key costs materially more gas to store than a fixed 32-byte slot. More decisively, a `string` event parameter cannot be usefully indexed — Solidity stores its hash in the topic — so filtering logs by the readable identifier would be impossible in either design. Using `bytes32` therefore costs nothing in capability and saves gas.

**Revocation restricted to the original issuer, not merely to any authorised issuer.** This is the most safety-critical rule in the contract. Were any authorised institution able to revoke any certificate, one onboarded organisation could invalidate a competitor's credentials. Contract ownership likewise confers no authority over another issuer's certificates.

**Unknown keys return the zero-value struct rather than reverting.** `getCertificate` on an unissued key returns `(0x00…, address(0), 0, false)`. Callers must therefore treat `issuer == address(0)` as "not found"; a zero `certHash` is not a safe existence test, because `issueCertificate` rejects a zero hash and no real record can carry one. This behaviour is asserted by the test suite so the Django integration can depend on it.

**Anchors are immutable once written.** No function can overwrite an existing `certHash`. A test enumerates every state-mutating function in the ABI and asserts the set is exactly `{authorizeIssuer, deauthorizeIssuer, issueCertificate, revokeCertificate}` — so a future change that introduces a way to mutate an anchor fails the suite.

### 6.4 Test coverage

**30 unit tests, all passing**, executed on Hardhat's in-memory chain with no gas cost and no network access. Contract tests run before deployment because an access-control defect is effectively unfixable once the address is baked into backend configuration and certificates are anchored against it.

| Group | Tests | Coverage |
|---|---|---|
| Deployment | 3 | Owner assignment, deployer auto-authorisation |
| Issuer administration | 4 | Grant, revoke, non-owner rejection, zero address |
| `issueCertificate` | 8 | Success, unauthorised caller, duplicates, zero hash, event args, log filtering |
| `revokeCertificate` | 9 | Original issuer succeeds; **outsider, different authorised issuer, and owner all revert**; unknown key; double revocation; field preservation |
| `getCertificate` | 4 | Correct struct, zero-value default, gas-free view, `exists()` |
| Tamper evidence | 2 | Hash sensitivity, no anchor-mutating functions |

```
30 passing (276ms)
```

---

## 7. User Interface Design

> **⚠ TO COMPLETE:** Insert screenshots below. Suggested captures are listed for each screen.

### 7.1 Design system

The interface derives its visual language from the project's subject — credentials, registries and seals — rather than from a generic framework palette. Colour is semantic, not decorative:

| Token | Light | Dark | Meaning |
|---|---|---|---|
| Accent (teal) | `#0B6B5F` | `#4FC9B6` | The application, off-chain data, the `VALID` state |
| Chain (bronze) | `#8A5A0B` | `#DFA53E` | Reserved exclusively for blockchain elements — hashes, transaction links |
| Danger (red) | `#A23829` | `#EE8A79` | `REVOKED`, `FAILED`, `TAMPERED` |
| Ground | `#F5F6F3` | `#0F1413` | Cool grey-green, biased toward the accent |

A user who learns that bronze indicates blockchain data on the certificate detail page carries that reading to the verification page.

**Typography** uses three roles: a serif for page titles (a certificate is a document), a system sans for controls and body text, and a monospace face for certificate IDs, hashes and wallet addresses — identifiers that are compared character by character and are unsuited to proportional type.

**Status is encoded redundantly** in colour, border style and label, so the dashboard remains scannable in greyscale and for colour-blind users. `PENDING` and `FAILED` use dashed borders because both are transient states; `TAMPERED` carries the heaviest border in the system because it must never be mistaken for anything else.

Full dark-mode support is implemented at token level.

### 7.2 Screens

| # | Screen | Route | Screenshot |
|---|---|---|---|
| 1 | Login | `/login` | `[INSERT]` |
| 2 | Registration | `/register` | `[INSERT]` |
| 3 | Email verification | `/verify-email` | `[INSERT]` |
| 4 | Dashboard — certificate list, search, status filter | `/dashboard` | `[INSERT]` |
| 5 | Issue certificate form | `/certificates/new` | `[INSERT]` |
| 6 | Certificate detail with blockchain reference | `/certificates/:id` | `[INSERT]` |
| 7 | Revocation modal | — | `[INSERT]` |
| 8 | Public verification — `VALID` result | `/verify/:certId` | `[INSERT]` |
| 9 | Public verification — `TAMPERED` warning | `/verify/:certId` | `[INSERT]` |
| 10 | Generated PDF certificate with QR code | — | `[INSERT]` |

> **Recommended:** include screenshot 9 (`TAMPERED`) prominently — it is the single most persuasive demonstration of the system's value.

### 7.3 Accessibility

- WCAG AA contrast in both themes
- Visible focus indication on every interactive element; `outline: none` is never used
- Status conveyed by icon, label and border style, not colour alone
- `prefers-reduced-motion` honoured
- Labels bound to inputs via `htmlFor`; errors announced via `aria-describedby` and `role="alert"`
- Password fields include a reveal toggle with `aria-pressed` state

---

## 8. Implementation Summary

### 8.1 Scale

| Component | Size |
|---|---|
| Backend — `accounts` | ~2,300 lines |
| Backend — `certificates` | ~2,470 lines |
| Backend — `blockchain` | ~970 lines |
| Backend — `notifications` | ~250 lines |
| Backend — project config | ~470 lines |
| Smart contract | 139 lines Solidity |
| Contract tests | 342 lines |
| Frontend | ~2,300 lines TypeScript/TSX |

### 8.2 Test results

| Suite | Tests | Result |
|---|---|---|
| Smart contract (Hardhat + Mocha) | 30 | **All passing** |
| Backend — authentication | 66 | **All passing** |
| Backend — certificates, PDF, hashing, isolation | 57 | **All passing** |
| Backend — blockchain integration | 33 | **All passing** |
| **Total** | **186** | **All passing** |

Notable coverage:
- Lockout thresholds verified with time-mocking (`time_machine`) rather than by waiting
- Rate limits asserted **individually for each of the seven** authentication endpoints
- PDF content verified by programmatic text extraction (`pdfplumber`), not visual inspection
- QR codes decoded (`pyzbar`) and asserted to resolve to the correct verification URL
- Cross-organisation access asserted to return 404 for list, detail, revoke and retry

### 8.3 Implementation status

Development followed a phased plan. Current state:

| Phase | Description | Status |
|---|---|---|
| 0 | Project scaffolding, Docker, contract compilation | ✅ Complete |
| 1 | Smart contract unit testing | ✅ Complete (30 tests) |
| 2 | Data models, migrations, admin | ✅ Complete |
| 3 | Authentication system | ✅ Complete (66 tests) |
| 4 | PDF and QR generation | ✅ Complete |
| 5 | Asynchronous blockchain anchoring | ✅ Complete |
| 6 | Management dashboard, revocation, expiry job | ✅ Complete |
| 7 | Public verification | ⚠ Logic complete; dedicated test suite outstanding |
| 8 | Email notifications | ⬜ Not implemented |
| 9 | Security hardening, CI, README | ⬜ Not implemented |

> **⚠ TO COMPLETE — contract deployment.** The contract compiles and passes all tests but is **not yet deployed to Amoy**, as deployment requires a faucet-funded wallet. Until `BLOCKCHAIN_CONTRACT_ADDRESS` is configured, issuance terminates at `FAILED` with an explanatory reason, and verification returns `UNVERIFIED`. Deploy with `npm run deploy:amoy`, then record here:
>
> - Contract address: `[FILL IN]`
> - Explorer link: `https://amoy.polygonscan.com/address/[FILL IN]`
> - Deployment transaction: `[FILL IN]`

### 8.4 Security measures implemented

| Requirement | Implementation |
|---|---|
| Password storage | Argon2 hashing; minimum 10 characters; common-password list |
| Session management | 15-minute access token in memory; 7-day refresh token as httpOnly cookie |
| Token theft detection | Refresh rotation; replaying a spent token revokes the entire session family |
| Brute-force defence | Account and IP lockout with time-window and cooldown |
| Rate limiting | All seven auth endpoints plus public verification (30/min) |
| Account enumeration | Identical responses for existing and non-existent accounts |
| One-time codes | Cryptographically secure generation (`secrets`), 10-minute expiry, single use, bound to account |
| Tenant isolation | Enforced at queryset level; cross-tenant access returns 404 |
| Input sanitisation | HTML, script, control-character and spreadsheet-formula rejection |
| Key custody | Signing key server-side only, in one isolated module |
| Admin exposure | `/admin/` routed only when explicitly enabled by environment variable |

### 8.5 Known limitations

Stated explicitly rather than omitted:

1. **Contract not yet deployed** — see §8.3.
2. **Email notifications not implemented** (Phase 8). Messages are logged to the console.
3. **Session does not survive page refresh.** `ProtectedRoute` checks only the in-memory token and no silent refresh is attempted on mount, so reloading the dashboard returns the user to login.
4. **Two auth screens are out of date** with the API. `verify-email` and `reset-password` now require an `email` field alongside the code — a change made to close an account-enumeration weakness — and the corresponding forms have not been updated.
5. **Testnet persistence** — see §5.1.
6. **Single hot wallet** — appropriate for one organisation; a multi-tenant production system would warrant per-organisation key management or a hardware security module.

---

## 9. Public GitHub Repository

**https://github.com/SoSereysokbotra/Blockchain-Based-Digital-Certificate**

> **⚠ BEFORE SUBMITTING — verify all of the following:**
>
> - [ ] Repository visibility is set to **Public**
> - [ ] `backend/.env` is **not** committed (it contains the database password and would contain the wallet private key)
> - [ ] `blockchain/.env` is **not** committed
> - [ ] Run `git log --all --full-history -- "**/.env"` to confirm no `.env` was committed in any earlier commit — if one was, the credentials must be rotated, as deleting the file does not remove it from history
> - [ ] `README.md` documents setup via `docker compose up`
> - [ ] The repository builds from a fresh clone

### Repository structure

```
├── backend/                 Django REST API
│   ├── accounts/            Authentication, Organization model, lockout
│   ├── certificates/        Certificate lifecycle, hashing, PDF, verification
│   ├── blockchain/          web3.py integration — the only module importing web3
│   ├── notifications/       Email delivery logging
│   └── bcip_backend/        Project settings and URL configuration
├── blockchain/              Solidity workspace
│   ├── contracts/           CertificateRegistry.sol
│   ├── test/                30 unit tests
│   └── scripts/             Amoy deployment script
├── frontend/                React + Vite single-page application
│   └── src/
│       ├── pages/           Route components
│       ├── components/      Reusable UI and layouts
│       ├── context/         Auth and toast providers
│       └── styles/          Design tokens and component styles
├── docs/                    SRS, implementation plan, API contract
└── docker-compose.yml       Full development stack
```

---

## 10. Individual Contribution Report

> **⚠ TO COMPLETE:** This section must be written in your own words and reflect your own account of the work. Use the structure below as a prompt. If your institution requires disclosure of AI-assisted development, state it here — most now do, and an undisclosed omission is treated far more seriously than the assistance itself.

This project was completed individually. All components — requirements analysis, smart contract, backend, frontend, database design, testing and documentation — fall to a single developer.

### Suggested structure

**Requirements and design**
Authored the SRS covering functional requirements, non-functional requirements, the data model and the blockchain architecture. Produced the phased implementation plan and the system architecture.

**Smart contract development**
Designed and implemented `CertificateRegistry.sol`. Wrote 30 unit tests covering access control, duplicate rejection, event emission and the documented default-return behaviour. Deployed to Polygon Amoy. `[Describe the specific design decisions you made — the bytes32 key choice and the original-issuer-only revocation rule are the two most defensible.]`

**Backend development**
Implemented the Django REST API across four applications: authentication with JWT rotation and lockout, the certificate lifecycle with canonical hashing and PDF generation, an isolated blockchain integration layer, and notification logging. Wrote 156 backend tests.

**Frontend development**
Built the React single-page application covering both the authenticated organisation portal and the public verification portal, including the design system and dark-mode support.

**Testing and quality**
Established a 186-test suite spanning contract, unit and integration levels, including time-mocked security tests and programmatic PDF and QR verification.

**Challenges encountered** — `[Write these in your own words. Candidates worth discussing:]`
- Why blockchain confirmation cannot be handled synchronously within an HTTP request, and how the `PENDING` state and background worker resolve it
- Why the background worker must run single-concurrency, and what nonce collision would otherwise cause
- Why the canonical hash format must be frozen, and what breaks if it is not
- Why verification must compare against the on-chain hash rather than a stored column
- Native dependency management for WeasyPrint, and why Docker was made mandatory

**Reflection** — `[What you would do differently; what you learned about the difference between tamper-evidence and truth.]`

---

## 11. Public Demo Video

> **⚠ TO COMPLETE**
>
> **Link:** `[FILL IN]`
> **Platform:** YouTube (unlisted or public) / Google Drive with link sharing enabled
> **Recommended length:** 5–8 minutes
>
> **Verify the link is publicly accessible in a private browsing window before submitting.**

### Suggested demonstration sequence

| # | Segment | Content |
|---|---|---|
| 1 | Introduction | The problem: why a database alone cannot prove a record is unaltered |
| 2 | Architecture | Walk through the layered diagram; explain the on-chain / off-chain split |
| 3 | Authentication | Register, verify email, log in; mention lockout and rate limiting |
| 4 | Issuance | Complete the form; show the `PENDING` → `VALID` transition |
| 5 | Blockchain proof | Open the transaction on PolygonScan — **show the real public record** |
| 6 | Certificate PDF | Display the generated PDF and its QR code |
| 7 | Verification | Scan the QR; show the `VALID` result on the public page |
| 8 | **Tamper demonstration** | Edit `course_title` directly in the database, re-verify, show `TAMPERED` |
| 9 | Revocation | Revoke a certificate; show the on-chain flag and the resulting status |
| 10 | Testing | Run `npx hardhat test` and `pytest`; show 186 passing |
| 11 | Conclusion | State the limitation honestly: the system proves integrity, not truth |

> **Segment 8 is the most important part of the demonstration.** It is the only moment that shows what the blockchain actually contributes. Prepare it in advance: have the SQL `UPDATE` statement ready and the verification page open in a second tab.

---

## Appendix A — Requirements Traceability

| Requirement | Implementation | Verified by |
|---|---|---|
| FR-1.1 Registration + verification | `accounts/views.py` | `TestRegistration`, `TestEmailVerification` |
| FR-1.2/1.3 Login, JWT session | `accounts/tokens.py` | `TestLogin` |
| FR-1.5 Token refresh | `rotate_tokens()` | `TestRefreshRotation` |
| FR-1.6 Account lockout | `accounts/lockout.py` | `TestAccountLockout` |
| FR-1.8 Password reset | `ResetPasswordView` | `TestPasswordReset` |
| FR-2.1.1 Input validation | `certificates/validators.py` | `TestCertificateValidation` |
| FR-2.2.1 Idempotency | `CertificateService.create()` | `TestIdempotency` |
| FR-2.3 PDF + QR | `certificates/pdf.py` | `TestPdfGeneration` |
| FR-2.4 Canonical hashing | `certificates/hashing.py` | `TestCanonicalHashing` |
| FR-2.5–2.8 Anchoring | `certificates/tasks.py` | `TestIssuance` |
| FR-2.9 Retry | `CertificateRetryView` | `TestRetry` |
| FR-2.10 Interaction log | `blockchain/models.py` | `TestIssuance` |
| FR-3.1/3.2 List and search | `CertificateListCreateView` | `TestCertificateListing` |
| FR-3.4/3.5 Revocation | `process_revocation()` | `TestRevocation` |
| FR-4.2.1 Expiry job | `expire_certificates` command | `TestExpiration` |
| FR-5.3 Hash comparison | `certificates/verification.py` | Phase 7 — outstanding |
| NFR-1.2 Key custody | `blockchain/service.py` | Code review |
| NFR-1.5 Tenant isolation | `OrganizationScopedMixin` | `TestCertificateListing` |
| NFR-1.10 Shared cache | `settings.CACHES` | `TestRateLimits` |
| NFR-1.11 IP policy | `accounts/ip.py` | `TestClientIpResolution` |
| §7.4 Issuer-only revocation | `CertificateRegistry.sol` | Contract test suite |

---

## Appendix B — Running the Project

```bash
# 1. Clone
git clone https://github.com/SoSereysokbotra/Blockchain-Based-Digital-Certificate.git
cd Blockchain-Based-Digital-Certificate

# 2. Configure
cp backend/.env.example backend/.env       # set SECRET_KEY and database
cp blockchain/.env.example blockchain/.env # set DEPLOYER_PRIVATE_KEY

# 3. Contract — test before deploying
cd blockchain && npm install
npx hardhat test                            # 30 tests
npm run deploy:amoy                         # record the printed address
# copy the address into backend/.env as BLOCKCHAIN_CONTRACT_ADDRESS

# 4. Backend
cd .. && docker compose up --build
docker compose run --rm backend python manage.py seed_demo
docker compose run --rm backend python manage.py check_chain

# 5. Frontend
cd frontend && npm install && npm run dev   # http://localhost:5173

# 6. Tests
docker compose run --rm backend pytest      # 156 tests
```

---

*End of submission document*
