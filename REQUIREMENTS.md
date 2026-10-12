# TRISHUL-Q — Requirements

**Everything you need to install, configure and run the full TRISHUL-Q system.**

This file is the single checklist for the whole stack: software prerequisites,
Python & Node dependencies, the database, environment variables, ports, optional
integrations, build/run steps — plus an honest "what is implemented vs what needs
external setup" table at the end.

---

## 1. Software prerequisites

| # | Requirement | Minimum | Why / notes |
|---|---|---|---|
| 1 | **Python** | 3.10+ (3.12 tested) | Backend (FastAPI), QDS engine, tests. |
| 2 | **Node.js + npm** | Node 20+, npm 10+ | Builds the React frontend (`frontend/`). |
| 3 | **PostgreSQL** | 14+ (16 recommended) | **Primary datastore** (replaces the old SQLite build). |
| 4 | **Git** | any | Optional — to clone / version the project. |
| 5 | **Docker + Docker Compose** | recent | Optional but easiest way to run PostgreSQL (`docker compose up -d db`). |
| 6 | OS | Linux / macOS / Windows 10+ | Any OS with Python + Node. |

> No quantum hardware, GPU, or cloud account is required — the quantum protocol
> is simulated in software.

---

## 2. Python dependencies (backend)

Install with:

```bash
pip install -r requirements.txt
```

| Package | Purpose |
|---|---|
| `fastapi`, `uvicorn[standard]`, `python-multipart` | Web API, ASGI server, form/file uploads |
| `SQLAlchemy>=2.0`, `psycopg2-binary` | PostgreSQL access with connection pooling |
| `numpy` | Exact linear algebra for the quantum simulation (teleportation, states) |
| `scipy` | 3-sigma threshold calibration z-scores + QRNG chi-square health test |
| `reportlab` | PDF export (TRISHUL-Q header, admin registrations) |
| `qrcode` | LAN URL QR code on the landing page |
| `psutil` | **Real** CPU / memory metrics for the admin dashboard graph |
| `httpx` | Google OAuth token exchange + test client |
| `pytest` | Automated test-suite |

**Optional (quantum randomness):** `pip install -r requirements-quantum.txt`
(`qiskit`, `qiskit-aer`). If absent, the QRNG silently falls back to OS entropy
(`secrets`) and everything still works.

---

## 3. Node dependencies (frontend)

Install + build:

```bash
cd frontend
npm install
npm run build          # → frontend/dist  (served by FastAPI at "/")
```

| Package | Purpose |
|---|---|
| `react`, `react-dom` | Public React application |
| `react-router-dom` | Client-side routing (landing, login, consoles) |
| `vite`, `@vitejs/plugin-react` | Build tool / dev server |

> **Charts use no library** — a small hand-rolled canvas helper
> (`src/components/Chart.jsx`). No heavy chart libs, no ML.
>
> **Fallback build:** in constrained/containerised environments where the Vite
> bundler (WASM) is unavailable, use `npm run build:esbuild` — it produces the
> same `dist/` output using esbuild.

---

## 4. Database (PostgreSQL)

* **Default URL:** `postgresql+psycopg2://trishul:trishul@localhost:5432/trishulq`
* **Create it:** `docker compose up -d db` **or** `createdb trishulq`.
* **Connection pooling:** SQLAlchemy engine with `pool_pre_ping`, `pool_size`
  (default 10) and `max_overflow` (default 20).
* **Tables created automatically** on first start (14 tables + 14 indexes):
  `users, sessions, signatures, messages, security_events, admin_requests,
  admin_messages, support_messages, performance_metrics, analysis_snapshots,
  settings, recovery, used_nonces, system_metrics`.
* **Indexed:** users, sessions, signatures, messages, security_events,
  admin_requests, performance_metrics, support/admin messages.
* **SQLite fallback:** allowed only when `TRISHUL_DB_FALLBACK=1` (for local
  dev / the test-suite). **Set it to `0` in production** so the app fails loudly
  rather than silently using SQLite.

---

## 5. Environment variables (`.env`)

Copy `.env.example` → `.env`. Key variables:

| Variable | Default | Required? | Meaning |
|---|---|---|---|
| `APP_ENV` | `development` | recommended | `production` disables the SQLite fallback |
| `DATABASE_URL` | postgres URL | **yes** | PostgreSQL connection string |
| `TRISHUL_DB_FALLBACK` | `1` | dev only | Ignored in production |
| `TRISHUL_SUPERADMIN_USERNAME` | `superadmin` | yes | Super Admin login |
| `TRISHUL_SUPERADMIN_PASSWORD` | `TrishulQ@2026` | yes (change it) | Seeded once, hashed |
| `SUPER_ADMIN_EMAIL` | — | recommended | Where admin welcome credentials are emailed |
| `SECRET_KEY` / `SESSION_SECRET` | — | recommended | Auxiliary signing secrets |
| `APP_MODE` | `lan` | no | `local` / `lan` / `live` |
| `PUBLIC_BASE_URL` | `http://localhost:8000` | recommended | Used in login/reset links & QR (set to your ngrok URL) |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | — | optional | Enables "Continue with Google" |
| `GOOGLE_REDIRECT_URI` | derived | optional | Explicit override; else derived per request |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USERNAME` / `SMTP_PASSWORD` / `SMTP_FROM_EMAIL` / `SMTP_FROM_NAME` / `SMTP_USE_TLS` | — | optional | Centralized email service |
| `TRISHUL_PASSWORD_MIN_LENGTH` / `TRISHUL_RESET_TTL_SECONDS` | `8` / `3600` | optional | Password & reset-token policy |
| `TRISHUL_LOGIN_MAX_ATTEMPTS` / `TRISHUL_RESET_MAX_REQUESTS` | `6` / `4` | optional | Rate limits / brute-force protection |

### v2 upgrade — new database tables

`roles`, `password_reset_tokens`, `oauth_accounts`, `audit_logs`,
`verification_events` — plus new `users` columns `must_change_password`,
`email_verified`, `created_by`, `owner_admin` (sender↔admin), `updated_at`,
`last_login`, `auth_provider`. Tables are created/migrated automatically on start.

---

## 6. Ports & URLs

| Service | URL | Exposure |
|---|---|---|
| Public React app | `http://localhost:8000` (`http://<LAN-IP>:8000`) | public / LAN |
| **Super Admin panel** | `http://127.0.0.1:8000/superadmin` | **localhost only** (server-enforced) |
| API docs | `http://localhost:8000/docs` | public |
| PostgreSQL | `localhost:5432` | local / docker network |

Ports used: **8000** (app), **5432** (PostgreSQL), **5173** (Vite dev server, optional).

---

## 7. Optional integrations

| Integration | Needed for | How to enable |
|---|---|---|
| **Google OAuth** | Sender/Receiver "Sign in with Google" | Set `GOOGLE_CLIENT_ID` + `GOOGLE_CLIENT_SECRET`; add redirect URI `http://localhost:8000/api/auth/google/callback`. |
| **SMTP mail** | Emailing admin credentials, "mail check" | Set `SMTP_*` vars. Without it, credentials are shown in the panel. |
| **Qiskit Aer** | Real superposition randomness for the QRNG | `pip install -r requirements-quantum.txt`. Falls back to OS entropy automatically. |

---

## 8. Build & run (all steps)

```bash
# 1. database
docker compose up -d db

# 2. backend
cp .env.example .env                 # edit DATABASE_URL + passwords
pip install -r requirements.txt
python server.py                     # http://localhost:8000

# 3. frontend
cd frontend && npm install && npm run build   # (fallback: npm run build:esbuild)

# 4. tests
python -m pytest backend/tests -q
```

One-shot: `./start.sh` (Linux/macOS) or `start.bat` (Windows).

---

## 9. What is implemented vs. what needs external setup

### Implemented and working in this project

| Area | Status |
|---|---|
| Single public domain + separate **localhost-only Super Admin** panel | ✅ |
| Roles: Super Admin / Admin / Sender / Receiver (capability-based) | ✅ |
| **Admin registration request → approve/reject** flow | ✅ |
| **Random password generator**, **PDF export** (TRISHUL-Q header), **mail** (SMTP) | ✅ |
| **PostgreSQL** layer with pooling + indexes + SQLite fallback | ✅ |
| Main **Landing Page** (navbar, hero, How-it-Works, 6-member team, project details, footer) | ✅ |
| **Pauli-eigenstate** QDS key + random X/Y/Z basis verification + per-basis **QBER** | ✅ |
| **Forgery-probability engine** (closed form `(1/2)^k` + Monte-Carlo 8-attack suite), **P_honest** | ✅ |
| **UNAUTHORIZED_VERIFICATION** as a first-class security event | ✅ |
| **Security-Analysis panel** with live charts (canvas, no library) | ✅ |
| QDS sign/send/verify, HMAC, replay protection, QEC, QRNG, live SOC feed | ✅ |
| Automated test-suite (quantum, Pauli, forgery, flows, isolation, DB) | ✅ |

### Needs external setup (by you, on the target machine)

| Item | What to do |
|---|---|
| A running **PostgreSQL** server | `docker compose up -d db` or install PostgreSQL. (The build sandbox had only the `psql` client, so the PostgreSQL path was validated at the SQL/dialect level, not against a live server.) |
| **Node.js** to build the React app | `cd frontend && npm install && npm run build` |
| **SMTP credentials** (optional) | Only if you want automatic credential emails |
| **Google OAuth credentials** (optional) | Only if you want Google sign-in |
| Replace **team placeholders** | Edit `frontend/src/pages/Landing.jsx` (6 members) |
| Change the **Super Admin password** | After first login (seeded default is for demo only) |

---

## 10. Quick self-check after install

```bash
curl http://localhost:8000/api/health          # {"status":"ok", "database":{...}}
curl http://localhost:8000/api/system/info     # shows the app + DB dialect + QRNG source
python -m pytest backend/tests -q              # all tests should pass
```
