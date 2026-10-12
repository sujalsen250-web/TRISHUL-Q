import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { useAuth } from "../App.jsx";

export default function ChangePassword({ forced = false }) {
  const [current, setCurrent] = useState("");
  const [pw, setPw] = useState("");
  const [confirm, setConfirm] = useState("");
  const [err, setErr] = useState("");
  const [ok, setOk] = useState("");
  const nav = useNavigate();
  const { me, refresh } = useAuth();

  function homeFor(m) {
    if (!m) return "/";
    if (m.role === "admin") return "/admin";
    return (m.capabilities || []).includes("receive") ? "/receiver" : "/sender";
  }

  async function submit(e) {
    e.preventDefault();
    setErr(""); setOk("");
    if (pw !== confirm) { setErr("Passwords do not match"); return; }
    try {
      await api("/api/auth/change-password",
        { method: "POST", body: { current_password: current, new_password: pw, confirm_password: confirm } });
      setOk("Password updated.");
      await refresh();
      setTimeout(() => nav(homeFor(me)), 900);
    } catch (ex) { setErr(ex.message); }
  }

  return (
    <div className="center-wrap">
      <div className="card auth-card">
        <h2 style={{ textAlign: "center" }}>
          {forced ? "Change Your Temporary Password" : "Change Password"}
        </h2>
        {forced && (
          <div className="alert warn">
            For security, you must change the temporary password before continuing.
          </div>
        )}
        <form onSubmit={submit}>
          <label>Current password</label>
          <input type="password" value={current} onChange={(e) => setCurrent(e.target.value)} />
          <label>New password</label>
          <input type="password" value={pw} onChange={(e) => setPw(e.target.value)} />
          <label>Confirm new password</label>
          <input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
          <div style={{ marginTop: 18 }}>
            <button className="btn primary" style={{ width: "100%" }}>UPDATE PASSWORD</button>
          </div>
        </form>
        {ok && <div className="alert ok">{ok}</div>}
        {err && <div className="alert error">{err}</div>}
      </div>
    </div>
  );
}
