# TRISHUL-Q — Change Log

## Round 1 — fixes & hardening (2026-10-07)

### 1. Password-reset email
- The reset link now falls back to the request's own base URL when
  `PUBLIC_BASE_URL` is empty, so the emailed link is always well-formed.
- If SMTP delivery fails, a `MAIL_FAILED` security event is raised instead of
  the API silently reporting success — the Super Admin can now see undelivered
  mail in the Security Events / Audit tabs.

### 2. All welcome mail went to one inbox  (FIXED)
- `_email_admin_welcome()` previously sent **every** new Admin's credentials to
  the single `SUPER_ADMIN_EMAIL` inbox. It now sends the welcome mail to the
  **Admin's own email address**. Tick *"Also copy the Super Admin"* to
  additionally copy the Super Admin. Applies to create-admin, approve-request
  and reset-password.

### 3. Quantum salt (sender → receiver)  (NEW)
- Every signature now appends **32 QRNG-generated random "salt" bits** to the
  qubit stream (deterministic Z-basis salt qubits).
- The salt's hash is folded into the signature **MAC**, so it is tamper-evident
  exactly like a cryptographic salt.
- The receiver **decodes** the salt bits from the transmitted qubit record and
  reports them under `quantum_salt` in the verification verdict. Flipping or
  stripping any salt bit breaks the MAC → the message is **REJECTED**.

### 4. Google sign-in with no account  (FIXED)
- Previously a brand-new Google sign-in silently created a default **receiver**
  account (both `send` + `receive`). It now creates **no** account: the user is
  redirected to `/register` with their Google email/name prefilled and must
  choose **Sender / Receiver / Both** themselves.

### 5. Super-admin Mail panel lost typed data  (FIXED)
- The panel re-rendered `#view` on every tab switch / refresh, wiping
  half-filled forms. Added form-state **stash/restore** so typed values survive
  re-renders.

### 6. Attack resistance
- Documented the threat model and coverage — see `SECURITY.md`.
- New: **quantum-salt tamper detection** bound into the MAC.
- Retained: message + attachment integrity, HMAC over signature metadata,
  sender identity + source-IP binding, nonce replay protection, signature TTL,
  Pauli-eigenstate forgery detection, 3-qubit QEC, Hoeffding-widened thresholds.

### 7. PostgreSQL only  (CHANGED)
- SQLite fallback is **disabled by default** (`ALLOW_SQLITE_FALLBACK = False`);
  the app now fails loudly if PostgreSQL is unreachable. Default DB port is
  **15432**.
- The test-suite still runs on a throw-away SQLite file via an explicit
  `sqlite://` `DATABASE_URL` (that is not a fallback).
