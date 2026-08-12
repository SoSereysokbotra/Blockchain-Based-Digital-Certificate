# API Contract

This document defines the strict API contract between the BCIP frontend and backend. Both sides must implement this contract exactly.

## Common Data Types

### Enums
- **CertificateStatus**: `"PENDING" | "VALID" | "EXPIRED" | "REVOKED" | "FAILED"`
- **VerificationOutcome**: `"VALID" | "EXPIRED" | "REVOKED" | "TAMPERED" | "NOT_FOUND"`

## Authentication Endpoints

### 1. Register Organization
- **POST** `/api/auth/register/`
- **Request Body**:
  ```json
  {
    "name": "string",
    "email": "string",
    "password": "string (min 10 chars)"
  }
  ```
- **Response (201 Created)**: Empty / success message.
- **Response (400 Bad Request)**: Validation errors (e.g., `{"email": ["Email already exists."]}`)

### 2. Verify Email
- **POST** `/api/auth/verify-email/`
- **Request Body**: `{"code": "string"}`
- **Response (200 OK)**: Success.

### 3. Login
- **POST** `/api/auth/login/`
- **Request Body**: `{"email": "string", "password": "string"}`
- **Response (200 OK)**:
  ```json
  {
    "access_token": "string"
  }
  ```
  *(Also sets `refresh_token` as an HttpOnly cookie)*
- **Response (401 Unauthorized)**: `{"detail": "Invalid credentials."}`
- **Response (423 Locked)**: `{"detail": "Account locked. Try again later."}`

### 4. Refresh Token
- **POST** `/api/auth/refresh-token/`
- **Request Body**: None *(uses HttpOnly cookie)*
- **Response (200 OK)**: `{"access_token": "string"}`

### 5. Logout
- **POST** `/api/auth/logout/`
- **Request Body**: None
- **Response (200 OK)**: Clears cookie.

### 6. Request Password Reset
- **POST** `/api/auth/request-password-reset/`
- **Request Body**: `{"email": "string"}`
- **Response (200 OK)**: Success message.

### 7. Verify Password Reset
- **POST** `/api/auth/verify-password-reset/`
- **Request Body**: `{"code": "string"}`
- **Response (200 OK)**: Success message.

### 8. Reset Password
- **POST** `/api/auth/reset-password/`
- **Request Body**: `{"code": "string", "new_password": "string"}`
- **Response (200 OK)**: Success message.

## Certificate Management (Requires Auth)

### 9. Create Certificate
- **POST** `/api/certificates/`
- **Headers**: `Idempotency-Key: <uuid>`
- **Request Body**:
  ```json
  {
    "recipient_name": "string (max 200)",
    "recipient_email": "string",
    "course_title": "string (max 200)",
    "issue_date": "YYYY-MM-DD",
    "expiry_date": "YYYY-MM-DD | null"
  }
  ```
- **Response (202 Accepted)**:
  ```json
  {
    "certificate_id": "string",
    "status": "PENDING",
    "pdf_url": "string"
  }
  ```
- **Response (400 Bad Request)**: Validation errors.

### 10. List Certificates
- **GET** `/api/certificates/`
- **Query Params**: `?page=1&search=...`
- **Response (200 OK)**:
  ```json
  {
    "count": "number",
    "next": "string | null",
    "previous": "string | null",
    "results": [
      {
        "certificate_id": "string",
        "recipient_name": "string",
        "issue_date": "YYYY-MM-DD",
        "status": "CertificateStatus"
      }
    ]
  }
  ```

### 11. Certificate Detail
- **GET** `/api/certificates/:id/`
- **Response (200 OK)**:
  ```json
  {
    "certificate_id": "string",
    "recipient_name": "string",
    "recipient_email": "string",
    "course_title": "string",
    "issue_date": "YYYY-MM-DD",
    "expiry_date": "YYYY-MM-DD | null",
    "status": "CertificateStatus",
    "blockchain_tx_hash": "string | null",
    "pdf_url": "string"
  }
  ```

### 12. Revoke Certificate
- **POST** `/api/certificates/:id/revoke/`
- **Request Body**: `{"reason": "string"}`
- **Response (202 Accepted)**: Indicates revocation process started.

### 13. Retry Issuance
- **POST** `/api/certificates/:id/retry/`
- **Request Body**: None
- **Response (202 Accepted)**: Indicates retry process started.

### 14. Resend Notification
- **POST** `/api/certificates/:id/resend-notification/`
- **Request Body**: None
- **Response (202 Accepted)**: Indicates resend requested.
- **Response (409 Conflict)**: Cannot send notification if not VALID.

## Public Endpoints

### 15. Verify Certificate
- **GET** `/api/public/verify/:cert_id/`
- **Response (200 OK)**:
  ```json
  {
    "certificate_id": "string",
    "recipient_name": "string",
    "course_title": "string",
    "issue_date": "YYYY-MM-DD",
    "status": "VerificationOutcome",
    "blockchain_tx_hash": "string | null",
    "revocation_reason": "string | null"
  }
  ```
