import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setErr(""); setMsg(""); setBusy(true);
    try {
      const r = await api("/api/auth/forgot-password", { method: "POST", body: { email } });
      setMsg(r.message);
    } catch (ex) { setErr(ex.message); }
    finally { setBusy(false); }
  }

  return (
    <div className="center-wrap">
      <div className="card auth-card">
        <h2 style={{ textAlign: "center" }}>Forgot Password</h2>
        <p className="muted" style={{ textAlign: "center", fontSize: 13 }}>
          Enter your email and we will send a single-use reset link.
        </p>
        <form onSubmit={submit}>
          <label>Email</label>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                 placeholder="you@example.com" />
          <div style={{ marginTop: 18 }}>
            <button className="btn primary" style={{ width: "100%" }} disabled={busy}>
              {busy ? "Sending…" : "SEND RESET LINK"}
            </button>
          </div>
        </form>
        {msg && <div className="alert ok">{msg}</div>}
        {err && <div className="alert error">{err}</div>}
        <p className="muted" style={{ textAlign: "center", fontSize: 12, marginTop: 12 }}>
          <Link to="/login">Back to login</Link>
        </p>
      </div>
    </div>
  );
}
