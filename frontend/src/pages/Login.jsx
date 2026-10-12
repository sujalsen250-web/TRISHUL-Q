import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { useAuth } from "../App.jsx";
import Trident from "../components/Trident.jsx";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [err, setErr] = useState("");
  const [google, setGoogle] = useState(false);
  const [busy, setBusy] = useState(false);
  const nav = useNavigate();
  const { refresh } = useAuth();

  useEffect(() => {
    api("/api/auth/google/status").then((s) => setGoogle(!!s.configured)).catch(() => {});
    const gErr = new URLSearchParams(location.search).get("google_error");
    if (gErr) setErr("Google sign-in failed: " + gErr.replace(/_/g, " "));
  }, []);

  async function submit(e) {
    e.preventDefault();
    setErr(""); setBusy(true);
    try {
      const res = await api("/api/auth/login", { method: "POST", body: { email, password } });
      await refresh();
      nav(res.redirect || "/");
    } catch (ex) { setErr(ex.message); }
    finally { setBusy(false); }
  }

  return (
    <div className="center-wrap">
      <div className="card auth-card">
        <div style={{ textAlign: "center" }}>
          <Trident size={54} />
          <h2 style={{ marginTop: 10 }}>TRISHUL-Q</h2>
          <p className="muted" style={{ fontSize: 13 }}>Sign in to your account</p>
        </div>
        <form onSubmit={submit}>
          <label>Email</label>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                 autoComplete="username" placeholder="you@example.com" />
          <label>Password</label>
          <div style={{ position: "relative" }}>
            <input type={show ? "text" : "password"} value={password}
                   onChange={(e) => setPassword(e.target.value)}
                   autoComplete="current-password" style={{ paddingRight: 52 }} />
            <button type="button" onClick={() => setShow(!show)}
                    title={show ? "Hide password" : "Show password"}
                    style={{ position: "absolute", right: 6, top: "50%", transform: "translateY(-50%)",
                             background: "none", border: 0, color: "var(--muted)", cursor: "pointer" }}>
              {show ? "Hide" : "Show"}
            </button>
          </div>
          <div style={{ marginTop: 18 }}>
            <button className="btn primary" style={{ width: "100%" }} disabled={busy}>
              {busy ? "Signing in…" : "LOGIN"}
            </button>
          </div>
        </form>

        {google && (
          <a className="btn" style={{ width: "100%", marginTop: 12 }} href="/api/auth/google/login">
            <svg width="17" height="17" viewBox="0 0 48 48" aria-hidden="true">
              <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.3 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.9 1.2 8 3.1l5.7-5.7C34.1 6.1 29.3 4 24 4 13 4 4 13 4 24s9 20 20 20 20-9 20-20c0-1.2-.1-2.3-.4-3.5z"/>
              <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.9 1.2 8 3.1l5.7-5.7C34.1 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z"/>
              <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.3 0-9.7-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z"/>
              <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.1-4.1 5.4l6.2 5.2C41 35.6 44 30.2 44 24c0-1.2-.1-2.3-.4-3.5z"/>
            </svg>
            Continue with Google
          </a>
        )}

        {err && <div className="alert error">{err}</div>}

        <div className="row" style={{ justifyContent: "space-between", marginTop: 14, fontSize: 13 }}>
          <Link to="/forgot-password">Forgot Password?</Link>
          <Link to="/register">Create account</Link>
        </div>
        <p className="muted" style={{ textAlign: "center", fontSize: 11.5, marginTop: 12 }}>
          Super Admin signs in on the local panel only (http://127.0.0.1:8000/superadmin).
        </p>
      </div>
    </div>
  );
}
