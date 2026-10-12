import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api.js";

export default function Register() {
  const [params] = useSearchParams();
  // When arriving from a Google sign-in that has no TRISHUL-Q account yet, the
  // server redirects here with ?google=1&email=…&name=…. We prefill those so
  // the user simply chooses their account type and finishes creating it.
  const fromGoogle = params.get("google") === "1";
  const gEmail = (params.get("email") || "").trim();
  const gName = (params.get("name") || "").trim();
  const gUser = gEmail ? gEmail.split("@")[0].replace(/[^a-zA-Z0-9_]/g, "_").slice(0, 24) : "";

  const [f, setF] = useState({ capability: "send", full_name: gName, username: gUser,
    department: "", password: "", email: gEmail, security_question: "", security_answer: "" });
  const [err, setErr] = useState("");
  const [ok, setOk] = useState("");
  const nav = useNavigate();
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  async function submit(e) {
    e.preventDefault(); setErr(""); setOk("");
    try {
      await api("/api/auth/register", { method: "POST", body: f });
      setOk("Account created! Redirecting to sign in…");
      setTimeout(() => nav("/login"), 1400);
    } catch (ex) { setErr(ex.message); }
  }

  return (
    <div className="center-wrap">
      <div className="card auth-card">
        <h2 style={{ textAlign: "center" }}>Create Account</h2>
        <p className="muted" style={{ textAlign: "center", fontSize: 13 }}>Sender / Receiver account</p>
        {fromGoogle && (
          <div className="alert" style={{ background: "rgba(230,162,60,.12)", color: "#ffd79a" }}>
            No account exists for <b>{gEmail}</b> yet. Please create one below —
            choose whether you are a Sender, a Receiver, or Both.
          </div>
        )}
        <form onSubmit={submit}>
          <label>Account type</label>
          <select value={f.capability} onChange={set("capability")}>
            <option value="send">Sender — signs and sends</option>
            <option value="receive">Receiver — receives and verifies</option>
            <option value="both">Both</option>
          </select>
          <label>Full name</label>
          <input value={f.full_name} onChange={set("full_name")} />
          <div className="row">
            <div style={{ flex: 1 }}>
              <label>Username</label>
              <input value={f.username} onChange={set("username")} className="mono" />
            </div>
            <div style={{ flex: 1 }}>
              <label>Department</label>
              <input value={f.department} onChange={set("department")} />
            </div>
          </div>
          <label>Email {fromGoogle ? "" : "(optional)"}</label>
          <input value={f.email} onChange={set("email")} />
          <label>Password (min 6)</label>
          <input type="password" value={f.password} onChange={set("password")} />
          <label>Security question</label>
          <input value={f.security_question} onChange={set("security_question")} />
          <label>Security answer</label>
          <input value={f.security_answer} onChange={set("security_answer")} />
          <div style={{ marginTop: 18 }}>
            <button className="btn primary" style={{ width: "100%" }}>REGISTER</button>
          </div>
        </form>
        {err && <div className="alert error">{err}</div>}
        {ok && <div className="alert ok">{ok}</div>}
        <p className="muted" style={{ textAlign: "center", fontSize: 12, marginTop: 12 }}>
          <Link to="/login">Back to sign in</Link>
        </p>
      </div>
    </div>
  );
}
