# TRISHUL-Q

**Threat Recognition, Identification & Signature Handling under Unified Logic — Quantum**

A teleportation-based **Quantum Digital Signature (QDS)** platform with three
detection layers ("teen shool" = three prongs):

| Layer | What it checks | Where |
|---|---|---|
| 1 | Bell-state teleportation integrity + Pauli corrections + replay | `backend/quantum/*`, `backend/qds/*` |
| 2 | **Pauli-eigenstate X/Y/Z basis verification** (per-basis QBER) | `backend/quantum/pauli_eigenstates.py`, `backend/qds/verification.py` |
| 3 | Hoeffding-bounded statistical deviation + **forgery-probability engine** | `backend/detection/*` |

> Honesty note: this is a **software simulation** of the quantum protocol
> (exact linear algebra with NumPy). It does **not** run on quantum hardware and
> does **not** claim unconditional security. There is **no ML** anywhere in the
> detection pipeline, and **no hard-coded statistics** — every number comes from
> the live engine or from PostgreSQL.

---

## Architecture

```
                ┌────────────────────────────── PUBLIC DOMAIN / LAN ──────────────────────────────┐
  Landing Page  │  Home · About Project · How it Works · Team · Request Admin Access · Login       │
  (React SPA)   │                                                                                   │
                │   SENDER  (capability 'send')  ──▶  /sender      sign · attach · send             │
                │   RECEIVER (capability 'receive') ─▶ /receiver   verify (X/Y/Z QBER) · ack         │
                │   ADMIN   (online)               ─▶ /admin       dashboard · users · events ·      │
                │                                                  statistics · analysis · settings  │
                └───────────────────────────────────────────────────────────────────────────────────┘
                                     │
        ┌────────────────────────────┴─────────────────────────────┐
        │  SUPER ADMIN  —  127.0.0.1 ONLY  →  /superadmin           │
        │  admin requests · approve/reject · manage admins & users  │
        │  DB overview · attack analytics · PDF export · mail       │
        │  random password generator · two-way messaging            │
        └───────────────────────────────────────────────────────────┘
                                     │
                     FastAPI backend  ·  PostgreSQL (pooled, indexed)
                     QDS engine (signature + independent verification)
```

**Roles:** `superadmin` (localhost only) · `admin` (online) · `user`
(Sender/Receiver via capabilities `send` / `receive`).

---

## Quick start

### 1. PostgreSQL (primary datastore)

```bash
docker compose up -d db          # starts PostgreSQL 16 on :5432
# or, with a local install:
createdb trishulq
```

### 2. Backend

```bash
cp .env.example .env             # edit DATABASE_URL + passwords
pip install -r requirements.txt
python server.py                 # http://localhost:8000
```

### 3. Frontend (React)

```bash
cd frontend
npm install
npm run build                    # → frontend/dist (served by FastAPI)
# dev mode instead: npm run dev   (proxies /api to :8000)
```

Then open:

| What | Where |
|---|---|
| Public app (landing + consoles) | `http://localhost:8000` |
| LAN devices | `http://<LAN-IP>:8000` |
| **Super Admin panel** | `http://127.0.0.1:8000/superadmin` — **localhost only** |
| API docs | `http://localhost:8000/docs` |

One-shot start: `./start.sh` (Linux/macOS) or `start.bat` (Windows).

**Windows — full setup in one command** (DB + Google OAuth + ngrok public link + run):

```powershell
.\setup.ps1
```

It prompts for your PostgreSQL password, Google Client ID/Secret and ngrok
authtoken, creates the database, starts the public tunnel, writes `.env`, and
launches the server.

**Windows — install PostgreSQL + create the database + tables in one command:**

```powershell
.\db-setup.ps1
```

Installs PostgreSQL 15 if missing, creates the role/database, creates all
tables and verifies the connection.

**Windows — run everything (ngrok tunnel + server) in one command:**

```powershell
.\run.ps1
```

---

## Public (internet) link

The app runs **locally** by default — `http://localhost:8000` (and the LAN IP).
To make it reachable on the internet, put a tunnel in front of port 8000:

```bash
# Option A — Cloudflare quick tunnel (free, no account needed)
cloudflared tunnel --url http://localhost:8000

# Option B — ngrok (needs a free authtoken)
ngrok http 8000
```

The tunnel prints a public `https://…` URL — that is your landing page.
Set `PUBLIC_BASE_URL` in `.env` to that URL so emails/QR codes point to it.
The **Super Admin panel stays localhost-only** in every mode (server-enforced).

## Google sign-in (optional)

Google login only appears once credentials are configured:

1. Google Cloud Console → **APIs & Services → Credentials → Create OAuth client ID**
   (Web application).
2. Authorised redirect URI: `http://localhost:8000/api/auth/google/callback`
   (add your tunnel URL too, if you use one).
3. Put the values in `.env`:

   ```
   GOOGLE_CLIENT_ID=…
   GOOGLE_CLIENT_SECRET=…
   ```

4. Restart the server — the "Continue with Google" button then shows on the login page.

Without these, the button is hidden and `/api/auth/google/*` reports *not configured* — that is expected.

---

## Authentication & admin (v2)

- **Login is EMAIL + PASSWORD** (username also accepted). Login page has
  show/hide password, *Continue with Google*, and *Forgot Password?*.
- **Google OAuth** — set `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` (and add the
  redirect URI(s) in the Google console). Google sign-in only ever creates
  normal users; it cannot create or authenticate privileged accounts.
- **Forgot password** — `/forgot-password` → emailed single-use reset link →
  `/reset-password` (token hashed at rest, expiring, invalidated after use).
- **Super Admin creates Admins** (`/superadmin` → Admins): a strong random
  temporary password is generated (never `admin123` etc.), stored only as a
  hash, and a ready-to-copy **welcome message** is emailed to `SUPER_ADMIN_EMAIL`
  (with *Copy Credentials* / *Copy Welcome Message* buttons in the panel).
- **Forced first-login change** — admins created with a temporary password must
  change it (`/change-password`) before reaching the dashboard.
- **Admin manages Senders** — the Admin dashboard has a **Senders** tab to
  create / activate / deactivate senders under their management.
- **Audit logging** — every security-sensitive action (logins, failures, admin
  and sender lifecycle, password resets) is recorded and visible to the
  Super Admin (Audit Logs / Auth Events tabs).
- **Rate limiting & brute-force protection** on login and password-reset.

## First login

- **Super Admin:** `superadmin` / `TrishulQ@2026` (change it — seeded once, hashed).
  Panel: `http://127.0.0.1:8000/superadmin` (localhost only).
- **Admin:** created by the Super Admin (panel → Admins → Create Admin), or via
  an approved *Request Admin Access*. Signs in with email + temporary password,
  then is forced to change it.
- **Sender / Receiver:** self-register on the landing page, or sign in with Google.

---

## Demo flow (what judges see)

1. **Sender** generates a QDS signature → the panel shows the **Pauli basis per qubit**.
2. **Receiver** opens the message → **X/Y/Z check counts, per-basis QBER, P_honest ≈ 1**.
3. Forgery at high intensity → **P_forge jumps**, Pauli mismatches appear, message **REJECTED**.
4. An unauthorized verify attempt → **`UNAUTHORIZED_VERIFICATION`** appears in the SOC feed.
5. **Admin → Security Analysis** shows the live **P_forge curve** and the 8-attack suite.

---

## Testing

```bash
python -m pytest backend/tests -q
```

Covers the quantum engine, Pauli eigenstates, the forgery engine, the QDS
send/verify pipeline, the **UNAUTHORIZED_VERIFICATION** event, **Super Admin
localhost isolation**, the **admin request/approval flow**, the password
generator, PDF export, and the persistence layer.

---

## Layout

```
trishul-q/
├── backend/            FastAPI app, QDS engine, quantum + detection modules
│   ├── quantum/        qubit, bell_states, pauli, pauli_eigenstates, teleportation,
│   │                   measurement, qec, qrng
│   ├── qds/            signature (v8 Pauli key), verification (X/Y/Z QBER)
│   ├── detection/      hoeffding, threshold, statistics, calibration, forgery
│   ├── config.py db.py auth.py security.py mailer.py pdf.py events.py metrics.py main.py
│   └── tests/
├── frontend/           React (Vite) public app  →  built to frontend/dist
├── superadmin/         simpler localhost-only Super Admin panel
├── docker-compose.yml  PostgreSQL (+ optional app container)
├── REQUIREMENTS.md     ← everything you need to install / configure
└── server.py
```

See **[REQUIREMENTS.md](REQUIREMENTS.md)** for the full list of prerequisites,
dependencies and configuration.
