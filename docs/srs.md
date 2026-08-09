# SOFTWARE REQUIREMENTS SPECIFICATION
## Blockchain-Based Digital Certificate Issuing Platform (BCIP)

**Version:** 1.0
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
| Version | 1.0 |
| Status | Draft |

### Revision History

| Version | Date | Author | Description |
|---|---|---|---|
| 0.1 | [Date] | [Your Name] | Initial draft |
| 1.0 | [Date] | [Your Name] | First complete version submitted for review |

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

---

## 1. Introduction

### 1.1 Purpose

This Software Requirements Specification (SRS) document describes the functional and non-functional requirements for the Blockchain-Based Digital Certificate Issuing Platform (BCIP). The purpose of the system is to allow educational institutions and training organizations to issue digital certificates that are tamper-resistant and publicly verifiable, by anchoring certificate integrity data of<!--  -->f a blockchain network. This document is intended to guide the design, implementation, and testing of the system, and to serve as a reference for evaluating whether the completed system meets its intended requirements.

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
- **Server:** Node.js-based backend, deployed on a standard cloud host or local server for demonstration.
- **Database:** A relational database (e.g., PostgreSQL/MySQL) or document database (e.g., MongoDB) for off-chain data.
- **Blockchain:** An EVM-compatible public test network (e.g., Sepolia or Polygon Amoy), accessed via a JSON-RPC provider.

### 2.5 Design and Implementation Constraints

- Only a cryptographic hash and minimal metadata will be stored on-chain; full certificate contents remain off-chain, for cost and performance reasons.
- The system will be deployed against a public test network rather than a production mainnet, since this is an academic project without a real budget for gas fees.
- The organization's blockchain transactions must be signed using a wallet/private key held securely by the backend (e.g., via environment variables), never exposed to the client.
- The system must be implementable by a single developer within the project timeline.

### 2.6 Assumptions and Dependencies

- It is assumed the organization has a single shared login for this project's scope (multi-branch/multi-admin support is a possible future enhancement).
- It is assumed test-network cryptocurrency (test ETH/MATIC) is obtainable free of charge from a public faucet.
- The system depends on the availability of the chosen blockchain RPC provider and email delivery service.

---

## 3. Functional Requirements

Each requirement below is labeled with a unique ID for traceability during design, implementation, and testing (e.g., in a future Requirements Traceability Matrix).

### 3.1 Organization Authentication

| ID | Requirement |
|---|---|
| FR-1.1 | The system shall allow an organization user to log in using an email/username and password. |
| FR-1.2 | The system shall reject login attempts with invalid credentials and display an appropriate error message. |
| FR-1.3 | The system shall maintain an authenticated session using a secure token (e.g., JWT) and shall expire the session after a period of inactivity. |
| FR-1.4 | The system shall restrict access to all Organization Portal pages and API endpoints to authenticated users only. |

### 3.2 Certificate Creation and Issuance

| ID | Requirement |
|---|---|
| FR-2.1 | The system shall provide a form for an authenticated organization user to enter certificate details: recipient name, recipient email, course/award title, issue date, and optional expiry date. |
| FR-2.2 | The system shall generate a unique Certificate ID for every certificate created. |
| FR-2.3 | The system shall generate a downloadable PDF representation of the certificate, including the recipient's name, award title, issue date, Certificate ID, and a QR code linking to the public verification page. |
| FR-2.4 | The system shall compute a cryptographic hash (SHA-256 or equivalent) of the certificate's canonical data upon issuance. |
| FR-2.5 | The system shall submit a transaction to the deployed smart contract to record the Certificate ID, certificate hash, issuer identifier, and issue timestamp on the blockchain. |
| FR-2.6 | The system shall store the resulting blockchain transaction hash / reference alongside the certificate record in the off-chain database. |
| FR-2.7 | The system shall not allow certificate issuance to complete successfully unless the blockchain transaction is confirmed, and shall display an error and allow retry if the transaction fails. |

### 3.3 Certificate Management (Organization View)

| ID | Requirement |
|---|---|
| FR-3.1 | The system shall display a list of all certificates issued by the logged-in organization, including recipient name, Certificate ID, issue date, and current status. |
| FR-3.2 | The system shall allow the organization user to search or filter issued certificates (e.g., by recipient name or Certificate ID). |
| FR-3.3 | The system shall allow the organization user to view full details of a specific certificate, including its blockchain transaction reference. |
| FR-3.4 | The system shall allow the organization user to revoke a previously issued, non-expired certificate, with a mandatory reason field. |
| FR-3.5 | The system shall update the certificate's status to "Revoked" immediately upon confirmation of a revocation action. |

### 3.4 Certificate Lifecycle (Expiration and Revocation)

| ID | Requirement |
|---|---|
| FR-4.1 | The system shall support an optional expiry date at the time of certificate creation. |
| FR-4.2 | The system shall automatically compute and display a certificate's status as "Expired" once the current date passes the certificate's expiry date, without requiring manual intervention. |
| FR-4.3 | The system shall display exactly one of three statuses for any certificate at any time: Valid, Expired, or Revoked. |
| FR-4.4 | A revoked certificate shall remain marked "Revoked" permanently and shall not be reactivated through the standard portal interface. |

### 3.5 Public Certificate Verification

| ID | Requirement |
|---|---|
| FR-5.1 | The system shall provide a public page where any visitor can enter a Certificate ID to verify a certificate, without requiring login. |
| FR-5.2 | The system shall provide a mechanism to verify a certificate automatically when its QR code is scanned, by directing the scanner to a URL containing the Certificate ID. |
| FR-5.3 | Upon verification, the system shall recompute the certificate's hash from the stored certificate data and compare it against the hash recorded on the blockchain. |
| FR-5.4 | The system shall display the certificate's recipient name, award/course title, issue date, and current status (Valid / Expired / Revoked) on the verification result page. |
| FR-5.5 | The system shall display the associated blockchain transaction reference and a link to view it on a public block explorer. |
| FR-5.6 | The system shall display a clear tamper-warning message if the recomputed hash does not match the on-chain hash. |
| FR-5.7 | The system shall return a clear "not found" result if the entered Certificate ID does not exist in the system. |

### 3.6 Email Notifications

| ID | Requirement |
|---|---|
| FR-6.1 | The system shall automatically send an email to the recipient's registered email address when a certificate is successfully issued. |
| FR-6.2 | The notification email shall include the certificate PDF (as an attachment or download link) and the public verification link. |
| FR-6.3 | The system shall log the delivery status of each notification email and allow the organization user to resend it manually if delivery fails. |

---

## 4. External Interface Requirements

### 4.1 User Interfaces

- Organization Login page
- Organization Dashboard (list of issued certificates, search/filter)
- Certificate Creation Form
- Certificate Detail View (organization side, including blockchain reference and revoke action)
- Public Verification Page (Certificate ID entry form and results display)
- Certificate PDF template (recipient-facing)

### 4.2 Hardware Interfaces

No dedicated hardware is required beyond a standard computing device with internet access and a camera-enabled device (e.g., smartphone) for scanning QR codes.

### 4.3 Software Interfaces

| Interface | Purpose |
|---|---|
| Blockchain RPC Provider (e.g., Infura/Alchemy) | Submit and read smart contract transactions on the test network |
| Smart Contract (deployed on testnet) | Store and retrieve certificate hash records and status flags |
| Email Delivery Service (e.g., SendGrid/Nodemailer + SMTP) | Send certificate issuance notifications |
| PDF Generation Library | Render certificate data into a downloadable PDF |
| QR Code Generation Library | Encode the verification URL into a scannable QR image |
| Database | Persist off-chain certificate, organization, and log data |

### 4.4 Communication Interfaces

- All client–server communication shall use HTTPS.
- The backend shall communicate with the blockchain network using JSON-RPC over HTTPS.
- Email shall be sent via SMTP or an equivalent transactional email API.

---

## 5. Non-Functional Requirements

### 5.1 Security

| ID | Requirement |
|---|---|
| NFR-1.1 | Passwords shall be stored using a strong, salted hashing algorithm (e.g., bcrypt) and never in plaintext. |
| NFR-1.2 | The blockchain wallet private key used to sign issuance/revocation transactions shall be stored server-side only (e.g., environment variables / secrets manager) and never exposed to the client. |
| NFR-1.3 | All Organization Portal endpoints shall require a valid authentication token. |
| NFR-1.4 | The public verification endpoints shall be read-only and shall not expose any means of modifying certificate data. |

### 5.2 Performance

| ID | Requirement |
|---|---|
| NFR-2.1 | Public certificate verification (excluding blockchain confirmation latency) shall return a result within 3 seconds under normal load. |
| NFR-2.2 | The certificate list view shall support pagination to remain responsive as the number of issued certificates grows. |

### 5.3 Usability

- The public verification page shall be usable without any instructions, requiring only a Certificate ID or QR scan.
- The system shall provide clear success/error feedback for all key actions (issuance, revocation, verification).

### 5.4 Reliability and Availability

- If the blockchain network is temporarily unavailable, the system shall queue or retry the transaction and inform the user, rather than silently failing.
- Off-chain certificate data shall remain the authoritative source for display content, with the blockchain serving as the integrity/tamper-evidence layer.

### 5.5 Maintainability

- The codebase shall separate concerns across frontend, backend API, database layer, and blockchain-interaction layer to support future maintenance.
- Configuration values (RPC URLs, contract address, email credentials) shall be externalized via environment variables, not hard-coded.

### 5.6 Scalability

- The system's architecture shall allow additional organizations to be onboarded without redesigning the data model (e.g., an Organization table/collection, even if only one organization is used in this project's demo).

---

## 6. Data Requirements (Logical Data Model)

This section describes the core entities required for the system's database (ER Diagram). Exact field types should be finalized during detailed design.

### 6.1 Organization

- organization_id (PK)
- name
- email (login identifier)
- password_hash
- wallet_address (blockchain address used to issue certificates)
- created_at

### 6.2 Certificate

- certificate_id (PK, unique, human-readable/UUID)
- organization_id (FK → Organization)
- recipient_name
- recipient_email
- course_title
- issue_date
- expiry_date (nullable)
- status (Valid / Expired / Revoked – derived or stored)
- certificate_hash (SHA-256 of canonical certificate data)
- blockchain_tx_hash
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

**Relationships:** One Organization issues many Certificates (1–N). One Certificate has at most one Revocation Log entry (1–0..1). One Certificate may have multiple Notification Log entries, e.g., original send plus resend attempts (1–N).

---

## 7. Blockchain Architecture and Smart Contract Design

### 7.1 Design Rationale

Full certificate documents will not be stored on-chain, since doing so is costly and unnecessary for the goal of tamper-evidence. Instead, the system follows a **hash-anchoring pattern**: certificate data is stored off-chain in the application database, and only a cryptographic hash of that data — plus minimal identifying metadata — is written to a smart contract. Verification is performed by recomputing the hash of the stored data and comparing it against the immutable on-chain record. If the two match, the data has not been altered since issuance; if they differ, tampering is indicated.

### 7.2 Network Choice

The smart contract will be deployed on a public EVM-compatible test network (e.g., Ethereum Sepolia or Polygon Amoy). Test networks are chosen over mainnet for this academic project because they allow free transactions using faucet-issued test tokens while still producing real, publicly viewable, and independently verifiable transactions on a public block explorer.

### 7.3 Smart Contract Responsibilities

- Store a mapping from Certificate ID to a record containing: certificate hash, issuer address, issue timestamp, and status (Active/Revoked).
- Provide a function to add a new certificate record (callable only by an authorized issuer address).
- Provide a function to update a certificate's status to Revoked (callable only by the original issuer address).
- Provide a read-only (view) function to retrieve a certificate record by Certificate ID for verification purposes.
- Emit events on issuance and revocation to support transaction lookup and auditability.

### 7.4 Illustrative Contract Structure

| Element | Description |
|---|---|
| `struct CertificateRecord` | `{ bytes32 certHash; address issuer; uint256 issuedAt; bool revoked; }` |
| `mapping(string => CertificateRecord) certificates` | Maps Certificate ID to its record |
| `function issueCertificate(string certId, bytes32 certHash)` | Adds a new record; restricted to authorized issuer addresses |
| `function revokeCertificate(string certId)` | Marks an existing record as revoked; restricted to the original issuer |
| `function getCertificate(string certId) view returns (CertificateRecord)` | Public read function used by the verification page |
| `event CertificateIssued(string certId, bytes32 certHash, address issuer)` | Emitted on issuance |
| `event CertificateRevoked(string certId)` | Emitted on revocation |

*(This is illustrative, not final — refine during detailed design.)*

### 7.5 Verification Flow

1. A user submits a Certificate ID via the public verification page or QR scan.
2. The backend retrieves the corresponding certificate record from the off-chain database.
3. The backend recomputes the SHA-256 hash of the retrieved certificate data.
4. The backend queries the smart contract's `getCertificate` function using the Certificate ID.
5. The backend compares the recomputed hash against the on-chain `certHash` and checks the on-chain `revoked` flag and the stored expiry date.
6. The system displays the final status (Valid / Expired / Revoked / Tampered–Not Verified) along with the blockchain transaction reference.

---

## 8. Use Cases

### 8.1 Use Case: Issue Certificate

| Field | Detail |
|---|---|
| Actor | Organization Staff (authenticated) |
| Precondition | User is logged in to the Organization Portal |
| Trigger | User submits the certificate creation form |
| Main Flow | 1) User enters recipient and certificate details. 2) System generates a Certificate ID and PDF. 3) System computes the certificate hash. 4) System submits a transaction to the smart contract. 5) System stores the certificate record and transaction reference. 6) System sends a notification email to the recipient. |
| Alternate Flow | If the blockchain transaction fails, the system displays an error and allows the user to retry without duplicating the database record. |
| Postcondition | A new certificate exists with status "Valid", is recorded on-chain, and the recipient has been notified. |

### 8.2 Use Case: Verify Certificate

| Field | Detail |
|---|---|
| Actor | Public Verifier (unauthenticated) |
| Precondition | None – page is publicly accessible |
| Trigger | User enters a Certificate ID or scans a certificate's QR code |
| Main Flow | 1) System looks up the certificate. 2) System recomputes the hash and queries the blockchain. 3) System compares results and computes the final status. 4) System displays certificate details, status, and blockchain transaction link. |
| Alternate Flow | If the Certificate ID does not exist, the system displays a clear "not found" message. If the hash does not match, the system displays a tamper warning. |
| Postcondition | The verifier has an accurate, evidence-backed view of the certificate's authenticity and status. |

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

- This is an academic capstone  project developed individually; the scope reflects what is achievable by one developer within the project timeline.
- A public test blockchain network will be used instead of mainnet, for cost reasons; this will be clearly documented and justified in the final report.
- Only a single organization account is required for demonstration purposes, though the data model supports multiple organizations.
- Free-tier or sandbox services will be used for email delivery and blockchain RPC access.

---

## 10. Future Enhancements (Out of Current Scope)

- Multi-admin / role-based access within a single organization.
- Support for multiple organizations with independent branding on issued certificates.
- Storing certificate PDFs on IPFS for fully decentralized retrieval.
- Bulk certificate issuance via CSV upload.
- A mobile app for scanning and verifying certificates offline-first.
- Deployment to a production mainnet with gas-cost optimization.

---

*End of Document*