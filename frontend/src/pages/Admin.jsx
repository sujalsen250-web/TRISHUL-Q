import { useEffect, useRef, useState } from "react";
import { api, fmtTime } from "../api.js";
import { useAuth } from "../App.jsx";
import { Line, MultiLine, Bars, COLORS } from "../components/Chart.jsx";

const TABS = ["Dashboard", "Senders", "Security Analysis", "Users", "Security Events", "Settings", "Messages"];

export default function Admin() {
  const { me } = useAuth();
  const [tab, setTab] = useState("Dashboard");
  const [err, setErr] = useState("");
  return (
    <div className="wrap" style={{ paddingTop: 24, paddingBottom: 40 }}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h2>Admin Console</h2>
        <span className="chip"><span className="dot" style={{ background: "var(--warn)" }} />{me?.full_name} · online admin</span>
      </div>
      <div className="tabs" style={{ marginTop: 12 }}>
        {TABS.map((t) => (
          <button key={t} className={tab === t ? "active" : ""} onClick={() => setTab(t)}>{t}</button>
        ))}
      </div>
      {err && <div className="alert error">{err}</div>}
      {tab === "Dashboard" && <Dashboard setErr={setErr} />}
      {tab === "Senders" && <Senders setErr={setErr} />}
      {tab === "Security Analysis" && <Analysis setErr={setErr} />}
      {tab === "Users" && <Users setErr={setErr} />}
      {tab === "Security Events" && <Events setErr={setErr} />}
      {tab === "Settings" && <Settings setErr={setErr} />}
      {tab === "Messages" && <Messages setErr={setErr} />}
    </div>
  );
}

function Dashboard({ setErr }) {
  const [d, setD] = useState(null);
  const [m, setM] = useState({ current: {}, series: [] });
  async function load() {
    try { setD(await api("/api/admin/dashboard")); } catch (e) { setErr(e.message); }
    try { setM(await api("/api/admin/metrics?limit=60")); } catch (e) { /* */ }
  }
  useEffect(() => { load(); const t = setInterval(load, 8000); return () => clearInterval(t); }, []);
  if (!d) return <p className="muted">Loading dashboard…</p>;
  const s = d.senders || {}, msg = d.messages || {}, se = d.security_events || {};
  return (
    <>
      <div className="grid g4">
        <div className="kpi"><div className="v">{s.total ?? 0}</div><div className="l">Total Senders</div></div>
        <div className="kpi"><div className="v">{s.active ?? 0}</div><div className="l">Active Senders</div></div>
        <div className="kpi"><div className="v">{msg.total ?? 0}</div><div className="l">Messages</div></div>
        <div className="kpi"><div className="v">{se.unauthorized_verifications ?? 0}</div><div className="l">Unauthorized</div></div>
      </div>
      <div className="grid g2" style={{ marginTop: 16 }}>
        <div className="card" style={{ margin: 0 }}>
          <h3>Verification status</h3>
          <div className="grid g3">
            <div className="kpi"><div className="v">{msg.verified ?? 0}</div><div className="l">Verified</div></div>
            <div className="kpi"><div className="v">{msg.suspicious ?? 0}</div><div className="l">Suspicious</div></div>
            <div className="kpi"><div className="v">{msg.rejected ?? 0}</div><div className="l">Rejected</div></div>
          </div>
        </div>
        <div className="card" style={{ margin: 0 }}>
          <h3>Account &amp; server</h3>
          <p className="muted">
            {d.account?.full_name} · {d.account?.department}<br />
            status: {d.account?.is_active ? "active" : "disabled"} · last login {fmtTime(d.account?.last_login)}<br />
            uptime {d.server?.uptime_seconds ?? 0}s · sessions {d.server?.active_sessions ?? 0} ·
            avg {d.server?.avg_response_ms ?? 0} ms
          </p>
        </div>
      </div>
      <div className="grid g2" style={{ marginTop: 16 }}>
        <div className="card" style={{ margin: 0 }}>
          <h3>CPU % (live)</h3>
          <div className="chartbox"><Line values={m.series.map((x) => x.cpu_percent || 0)} color={COLORS.cyan} max={100} /></div>
        </div>
        <div className="card" style={{ margin: 0 }}>
          <h3>Memory % (live)</h3>
          <div className="chartbox"><Line values={m.series.map((x) => x.mem_percent || 0)} color={COLORS.accent} max={100} /></div>
        </div>
      </div>
      <div className="card">
        <h3>Recent activity</h3>
        <table>
          <thead><tr><th>Action</th><th>Actor</th><th>Target</th><th>When</th></tr></thead>
          <tbody>
            {(d.recent_activity || []).map((a, i) => (
              <tr key={i}><td>{a.action}</td><td className="mono">{a.actor}</td>
                <td className="mono">{a.target || "—"}</td><td className="mono">{fmtTime(a.created_at)}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="card">
        <h3>Recent security events</h3>
        <table>
          <thead><tr><th>Type</th><th>Severity</th><th>Description</th></tr></thead>
          <tbody>
            {(d.recent_events || []).map((e, i) => (
              <tr key={i}><td><span className={`badge ${e.severity}`}>{e.event_type}</span></td>
                <td>{e.severity}</td><td className="muted">{e.description}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function Senders({ setErr }) {
  const [list, setList] = useState({ senders: [], total: 0, active: 0 });
  const [f, setF] = useState({ full_name: "", username: "", department: "", email: "", capability: "send" });
  const [created, setCreated] = useState(null);
  const [err, setErr2] = useState("");
  async function load() { try { setList(await api("/api/admin/senders")); } catch (e) { setErr(e.message); } }
  useEffect(() => { load(); }, []);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  async function create() {
    setErr2(""); setCreated(null);
    try {
      const r = await api("/api/admin/senders", { method: "POST", body: f });
      setCreated(r); load();
      setF({ full_name: "", username: "", department: "", email: "", capability: "send" });
    } catch (e) { setErr2(e.message); }
  }
  async function act(u, a) {
    try { await api(`/api/admin/senders/${u}/${a}`, { method: "POST" }); load(); }
    catch (e) { setErr(e.message); }
  }
  return (
    <div className="grid g2">
      <div className="card">
        <h3>Create Sender</h3>
        <label>Full name</label><input value={f.full_name} onChange={set("full_name")} />
        <div className="row">
          <div style={{ flex: 1 }}><label>Username</label>
            <input value={f.username} onChange={set("username")} className="mono" /></div>
          <div style={{ flex: 1 }}><label>Department</label>
            <input value={f.department} onChange={set("department")} /></div>
        </div>
        <label>Email</label><input value={f.email} onChange={set("email")} />
        <label>Capability</label>
        <select value={f.capability} onChange={set("capability")}>
          <option value="send">Sender (send)</option>
          <option value="both">Sender + Receiver</option>
          <option value="receive">Receiver (receive)</option>
        </select>
        <button className="btn primary" style={{ marginTop: 14 }} onClick={create}>CREATE SENDER</button>
        {created && (
          <div className="alert ok">
            Created <b>{created.sender.username}</b> — password: <span className="mono">{created.password}</span>
          </div>
        )}
        {err && <div className="alert error">{err}</div>}
      </div>
      <div className="card">
        <h3>Senders ({list.active}/{list.total} active)</h3>
        <table>
          <thead><tr><th>Username</th><th>Name</th><th>Dept</th><th>Active</th><th></th></tr></thead>
          <tbody>
            {list.senders.map((s) => (
              <tr key={s.username}>
                <td className="mono">{s.username}</td><td>{s.full_name}</td><td>{s.department}</td>
                <td>{s.is_active ? "yes" : "no"}</td>
                <td>
                  <button className="btn sm" onClick={() => act(s.username, "enable")}>Enable</button>{" "}
                  <button className="btn sm" onClick={() => act(s.username, "disable")}>Disable</button>
                </td>
              </tr>
            ))}
            {!list.senders.length && <tr><td colSpan="5" className="muted">No senders yet.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Analysis({ setErr }) {
  const [a, setA] = useState(null);
  const [n, setN] = useState(48);
  async function load() {
    setErr("");
    try { setA(await api(`/api/security/analysis?n_qubits=${n}&trials=120`)); }
    catch (e) { setErr(e.message); }
  }
  useEffect(() => { load(); }, [n]);
  if (!a) return <p className="muted">Computing live analysis…</p>;
  const pf = a.p_forge_vs_n_qubits || [];
  const suite = a.suite?.attacks || [];
  const palette = ["#5b6cff", "#2fb8d8", "#2fbf71", "#e6a23c", "#e5484d", "#c77dff", "#ff9770", "#4aa3e0"];
  return (
    <>
      <div className="grid g4">
        <div className="kpi"><div className="v">{a.honest?.p_honest}</div><div className="l">P_honest</div></div>
        <div className="kpi"><div className="v">{a.p_forge_closed_form}</div><div className="l">P_forge (closed form)</div></div>
        <div className="kpi"><div className="v">{a.checks}</div><div className="l">checks / signature</div></div>
        <div className="kpi"><div className="v">{a.n_qubits}</div><div className="l">n_qubits</div></div>
      </div>
      <div className="card">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <h3>P_forge vs n_qubits (no-cloning bound)</h3>
          <div className="row">
            <label style={{ margin: 0 }}>n_qubits</label>
            <input type="number" style={{ width: 110 }} value={n} onChange={(e) => setN(+e.target.value)} />
            <button className="btn sm" onClick={load}>Recalc</button>
          </div>
        </div>
        <div className="chartbox"><Line values={pf.map((p) => p.p_forge)} color={COLORS.bad} max={1} /></div>
        <p className="muted">x-axis: n_qubits = {pf.map((p) => p.n_qubits).join(", ")}</p>
      </div>
      <div className="card">
        <h3>Detection rate vs intensity — 8-attack suite</h3>
        <div className="chartbox" style={{ height: 300 }}>
          <MultiLine
            labels={a.suite?.intensities || []}
            series={suite.map((s, i) => ({ label: s.attack, color: palette[i % palette.length], data: s.detection }))}
          />
        </div>
      </div>
      <div className="card">
        <h3>Attack table</h3>
        <table>
          <thead><tr><th>Attack</th><th>Detection @1.0</th><th>P_forge @1.0</th></tr></thead>
          <tbody>
            {suite.map((s) => (
              <tr key={s.attack}>
                <td>{s.label}</td>
                <td className="mono">{s.detection[s.detection.length - 1]}</td>
                <td className="mono">{s.p_forge[s.p_forge.length - 1]}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted">Live DB: {JSON.stringify(a.live)}</p>
      </div>
    </>
  );
}

function Users({ setErr }) {
  const [rows, setRows] = useState([]);
  useEffect(() => { api("/api/admin/users").then((d) => setRows(d.users)).catch((e) => setErr(e.message)); }, []);
  return (
    <div className="card">
      <h3>Users</h3>
      <table>
        <thead><tr><th>Username</th><th>Role</th><th>Name</th><th>Department</th><th>Last seen</th><th>Active</th></tr></thead>
        <tbody>
          {rows.map((u) => (
            <tr key={u.username}>
              <td className="mono">{u.username}</td><td>{u.role}</td>
              <td>{u.full_name}</td><td>{u.department}</td>
              <td className="mono">{fmtTime(u.last_seen)}</td><td>{u.is_active ? "yes" : "no"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Events({ setErr }) {
  const [events, setEvents] = useState([]);
  const esRef = useRef(null);
  async function load() {
    try { setEvents((await api("/api/security/events?limit=200")).events); } catch (e) { setErr(e.message); }
  }
  useEffect(() => {
    load();
    try {
      const es = new EventSource("/api/events/stream");
      es.onmessage = (m) => {
        const ev = JSON.parse(m.data);
        if (ev.event_type !== "STREAM_CONNECTED") setEvents((prev) => [ev, ...prev].slice(0, 200));
      };
      esRef.current = es;
    } catch (e) { /* */ }
    return () => esRef.current && esRef.current.close();
  }, []);
  return (
    <div className="card">
      <h3>Security events (live SOC feed)</h3>
      <table>
        <thead><tr><th>Time</th><th>Type</th><th>Severity</th><th>Description</th></tr></thead>
        <tbody>
          {events.map((e, i) => (
            <tr key={i}>
              <td className="mono">{fmtTime(e.timestamp)}</td>
              <td><span className={`badge ${e.severity}`}>{e.event_type}</span></td>
              <td>{e.severity}</td>
              <td className="muted">{e.description}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Settings({ setErr }) {
  const [s, setS] = useState({});
  const [msg, setMsg] = useState("");
  useEffect(() => { api("/api/settings").then((d) => setS(d.settings)).catch((e) => setErr(e.message)); }, []);
  async function save() {
    setErr(""); setMsg("");
    try { const r = await api("/api/settings", { method: "PUT", body: s }); setS(r.settings); setMsg("Saved."); }
    catch (e) { setErr(e.message); }
  }
  async function calibrate() {
    try { const r = await api("/api/thresholds/calibrate", { method: "POST", body: { apply: true } });
      setS((x) => ({ ...x, threshold_suspicious: r.threshold_suspicious, threshold_threat: r.threshold_threat }));
      setMsg(`Calibrated: t_susp=${r.threshold_suspicious}, t_threat=${r.threshold_threat}`); }
    catch (e) { setErr(e.message); }
  }
  return (
    <div className="card">
      <h3>Detection settings</h3>
      {Object.entries(s).map(([k, v]) => (
        <div key={k}>
          <label>{k}</label>
          <input value={v} onChange={(e) => setS({ ...s, [k]: e.target.value })} className="mono" />
        </div>
      ))}
      <div className="row" style={{ marginTop: 16 }}>
        <button className="btn primary" onClick={save}>SAVE</button>
        <button className="btn" onClick={calibrate}>3-sigma auto-calibrate</button>
      </div>
      {msg && <div className="alert ok">{msg}</div>}
    </div>
  );
}

function Messages({ setErr }) {
  const [thread, setThread] = useState([]);
  const [text, setText] = useState("");
  const [threads, setThreads] = useState([]);
  async function load() {
    try { setThread((await api("/api/admin/messages")).messages); } catch (e) { /* */ }
    try { setThreads((await api("/api/support/threads")).threads); } catch (e) { /* */ }
  }
  useEffect(() => { load(); }, []);
  async function send() {
    if (!text.trim()) return;
    try { await api("/api/admin/message-superadmin", { method: "POST", body: { body: text } }); setText(""); load(); }
    catch (e) { setErr(e.message); }
  }
  return (
    <div className="grid g2">
      <div className="card">
        <h3>Super Admin conversation</h3>
        <div style={{ maxHeight: 260, overflow: "auto" }}>
          {thread.map((m, i) => (
            <div key={i} style={{ marginBottom: 8 }}>
              <span className="mono muted">{m.from_user}</span>: {m.body}
            </div>
          ))}
          {!thread.length && <p className="muted">No messages yet.</p>}
        </div>
        <textarea value={text} onChange={(e) => setText(e.target.value)} placeholder="Message the Super Admin…" />
        <button className="btn primary" style={{ marginTop: 8 }} onClick={send}>SEND</button>
      </div>
      <div className="card">
        <h3>User support threads</h3>
        <table>
          <thead><tr><th>User</th><th>Department</th><th>Unread</th></tr></thead>
          <tbody>
            {threads.map((t) => (
              <tr key={t.username}><td>{t.full_name || t.username}</td><td>{t.department}</td><td>{t.unread}</td></tr>
            ))}
            {!threads.length && <tr><td colSpan="3" className="muted">No threads.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
