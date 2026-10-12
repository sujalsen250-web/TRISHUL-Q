import { useState } from "react";
import { api } from "../api.js";

const EMPTY = { full_name: "", email: "", phone: "", aadhaar: "",
  department_id: "", department: "", gender: "" };

export default function RequestAdmin() {
  const [f, setF] = useState(EMPTY);
  const [err, setErr] = useState("");
  const [result, setResult] = useState(null);
  const [status, setStatus] = useState(null);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  async function submit(e) {
    e.preventDefault(); setErr(""); setResult(null);
    try { setResult(await api("/api/admin-requests", { method: "POST", body: f })); }
    catch (ex) { setErr(ex.message); }
  }

  async function check() {
    setErr(""); setStatus(null);
    try {
      setStatus(await api(`/api/admin-requests/status?email=${encodeURIComponent(f.email)}`));
    } catch (ex) { setErr(ex.message); }
  }

  return (
    <div className="center-wrap">
      <div className="card auth-card" style={{ width: "min(560px, 94vw)" }}>
        <h2 style={{ textAlign: "center" }}>Request Admin Access</h2>
        <p className="muted" style={{ textAlign: "center", fontSize: 13 }}>
          Submitted to the Super Admin for review. On approval you receive an Admin
          account (ID = email) with a generated password.
        </p>
        <form onSubmit={submit}>
          <label>Full name</label>
          <input value={f.full_name} onChange={set("full_name")} />
          <div className="row">
            <div style={{ flex: 1 }}>
              <label>Email</label>
              <input value={f.email} onChange={set("email")} />
            </div>
            <div style={{ flex: 1 }}>
              <label>Phone</label>
              <input value={f.phone} onChange={set("phone")} />
            </div>
          </div>
          <div className="row">
            <div style={{ flex: 1 }}>
              <label>Aadhaar</label>
              <input value={f.aadhaar} onChange={set("aadhaar")} />
            </div>
            <div style={{ flex: 1 }}>
              <label>Department ID</label>
              <input value={f.department_id} onChange={set("department_id")} />
            </div>
          </div>
          <div className="row">
            <div style={{ flex: 1 }}>
              <label>Department name</label>
              <input value={f.department} onChange={set("department")} />
            </div>
            <div style={{ flex: 1 }}>
              <label>Gender</label>
              <select value={f.gender} onChange={set("gender")}>
                <option value="">Prefer not to say</option>
                <option value="F">Female</option>
                <option value="M">Male</option>
                <option value="O">Other</option>
              </select>
            </div>
          </div>
          <div className="row" style={{ marginTop: 18 }}>
            <button className="btn primary" style={{ flex: 1 }}>SUBMIT REQUEST</button>
            <button type="button" className="btn" onClick={check}>Check status</button>
          </div>
        </form>
        {err && <div className="alert error">{err}</div>}
        {result && (
          <div className="alert ok">
            Request <b>{result.request_id}</b> submitted — status PENDING.
            Keep this ID to check progress.
          </div>
        )}
        {status && (
          <div className="alert warn">
            {status.request_id}: <b>{status.status}</b>{status.note ? ` — ${status.note}` : ""}
          </div>
        )}
      </div>
    </div>
  );
}
