import { useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api.js";

function strength(pw) {
  let s = 0;
  if (pw.length >= 8) s++;
  if (pw.length >= 12) s++;
  if (/[a-z]/.test(pw) && /[A-Z]/.test(pw)) s++;
  if (/\d/.test(pw) && /[^A-Za-z0-9]/.test(pw)) s++;
  return ["very weak", "weak", "fair", "strong", "very strong"][s];
}

export default function ResetPassword() {
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const [pw, setPw] = useState("");
  const [confirm, setConfirm] = useState("");
  const [err, setErr] = useState("");
  const [done, setDone] = useState("");
  const nav = useNavigate();
  const label = useMemo(() => strength(pw), [pw]);

  async function submit(e) {
    e.preventDefault();
    setErr(""); setDone("");
    if (pw !== confirm) { setErr("Passwords do not match"); return; }
    try {
      const r = await api("/api/auth/reset-password",
        { method: "POST", body: { token, new_password: pw, confirm_password: confirm } });
      setDone(r.message);
      setTimeout(() => nav("/login"), 1600);
    } catch (ex) { setErr(ex.message); }
  }

  return (
    <div className="center-wrap">
      <div className="card auth-card">
        <h2 style={{ textAlign: "center" }}>Reset Password</h2>
        {!token && <div className="alert warn">Missing reset token in the link.</div>}
        <form onSubmit={submit}>
          <label>New Password</label>
          <input type="password" value={pw} onChange={(e) => setPw(e.target.value)} />
          {pw && <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>Strength: {label}</div>}
          <label>Confirm Password</label>
          <input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
          <div style={{ marginTop: 18 }}>
            <button className="btn primary" style={{ width: "100%" }} disabled={!token}>
              RESET PASSWORD
            </button>
          </div>
        </form>
        {done && <div className="alert ok">{done}</div>}
        {err && <div className="alert error">{err}</div>}
        <p className="muted" style={{ textAlign: "center", fontSize: 12, marginTop: 12 }}>
          <Link to="/login">Back to login</Link>
        </p>
      </div>
    </div>
  );
}
