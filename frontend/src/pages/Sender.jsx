import { useEffect, useState } from "react";
import { api } from "../api.js";
import { useAuth } from "../App.jsx";

export default function Sender() {
  const { me } = useAuth();
  const [dir, setDir] = useState([]);
  const [message, setMessage] = useState("");
  const [recipient, setRecipient] = useState("");
  const [file, setFile] = useState(null);
  const [sig, setSig] = useState(null);
  const [sent, setSent] = useState([]);
  const [log, setLog] = useState([]);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const note = (m) => setLog((l) => [m, ...l].slice(0, 8));

  async function loadDir() {
    try {
      const d = await api("/api/users/directory");
      setDir(d.directory.filter((u) => (u.capabilities || "").includes("receive") || u.role === "admin"));
    } catch (e) { /* */ }
  }
  async function loadSent() {
    try { setSent((await api("/api/messages/sent")).messages); } catch (e) { /* */ }
  }
  useEffect(() => { loadDir(); loadSent(); }, []);

  async function genSig() {
    setErr(""); setSig(null);
    if (!message.trim()) { setErr("Write a message first"); return; }
    try {
      const s = await api("/api/signature/generate", { method: "POST", body: { message } });
      setSig(s);
      note(`Signature ${s.signature_id} generated (${s.n_qubits} qubits, QRNG ${s.qrng_source}).`);
    } catch (ex) { setErr(ex.message); }
  }

  async function send() {
    setErr("");
    if (!sig) { setErr("Generate a signature first"); return; }
    if (!recipient) { setErr("Choose a recipient"); return; }
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("message", message);
      fd.append("signature_id", sig.signature_id);
      fd.append("nonce", sig.nonce);
      fd.append("receiver_username", recipient);
      if (file) fd.append("file", file);
      const res = await api("/api/send", { method: "POST", body: fd });
      note(`Sent ${res.message_id} → ${res.verdict.classification} (D=${res.verdict.deviation}).`);
      setSig(null);
      loadSent();
    } catch (ex) { setErr(ex.message); }
    finally { setBusy(false); }
  }

  return (
    <div className="wrap" style={{ paddingTop: 26, paddingBottom: 40 }}>
      <h2>Sender Console</h2>
      <p className="muted">Signed in as <b>{me?.full_name}</b> · {me?.department}</p>

      <div className="grid g2">
        <div className="card">
          <h3>Compose &amp; sign</h3>
          <label>Message</label>
          <textarea value={message} onChange={(e) => setMessage(e.target.value)} placeholder="Type the message to sign…" />
          <div className="row">
            <div style={{ flex: 1 }}>
              <label>Recipient</label>
              <select value={recipient} onChange={(e) => setRecipient(e.target.value)}>
                <option value="">— choose —</option>
                {dir.map((u) => (
                  <option key={u.username} value={u.username}>
                    {u.full_name} ({u.department}) {u.online ? "· online" : ""}
                  </option>
                ))}
              </select>
            </div>
            <div style={{ flex: 1 }}>
              <label>Attachment (optional)</label>
              <input type="file" onChange={(e) => setFile(e.target.files[0])} />
            </div>
          </div>
          <div className="row" style={{ marginTop: 16 }}>
            <button className="btn" onClick={genSig}>GENERATE QDS SIGNATURE</button>
            <button className="btn primary" onClick={send} disabled={busy || !sig}>
              {busy ? "Sending…" : "SEND SECURE MESSAGE"}
            </button>
          </div>
          {err && <div className="alert error">{err}</div>}
        </div>

        <div className="card">
          <h3>Signature · Pauli key</h3>
          {!sig ? <p className="muted">No active signature. Signatures expire in 60 s.</p> : (
            <>
              <div className="grid g2">
                <div className="kpi"><div className="v mono" style={{ fontSize: 16 }}>{sig.signature_id}</div><div className="l">Signature id</div></div>
                <div className="kpi"><div className="v mono" style={{ fontSize: 16 }}>{sig.nonce}</div><div className="l">Nonce</div></div>
              </div>
              <p className="muted" style={{ marginTop: 10 }}>
                Bell state {sig.bell_symbol} · {sig.n_qubits} qubits · QRNG: {sig.qrng_source}
              </p>
              <div className="row" style={{ marginTop: 6 }}>
                {["X", "Y", "Z"].map((b) => (
                  <span className="chip" key={b}>Pauli-{b}: {sig.pauli_basis_counts?.[b] ?? 0}</span>
                ))}
              </div>
              <h4 style={{ marginTop: 14 }}>Per-qubit prepared basis</h4>
              <table>
                <thead><tr><th>Qubit</th><th>Basis</th><th>State</th></tr></thead>
                <tbody>
                  {(sig.pauli_key_preview || []).map((q) => (
                    <tr key={q.qubit}><td className="mono">{q.qubit}</td><td>{q.basis}</td><td className="mono">{q.state}</td></tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </div>
      </div>

      <div className="card">
        <h3>Sent messages</h3>
        <table>
          <thead><tr><th>ID</th><th>To</th><th>Status</th><th>D</th><th>Delivery</th><th>Signature</th></tr></thead>
          <tbody>
            {sent.map((m) => (
              <tr key={m.message_id}>
                <td className="mono">{m.message_id}</td>
                <td>{m.receiver_name || m.receiver_id}</td>
                <td><span className={`badge ${m.status}`}>{m.status}</span></td>
                <td className="mono">{m.deviation}</td>
                <td>{m.delivery_status}</td>
                <td className="mono">{m.signature_id}</td>
              </tr>
            ))}
            {!sent.length && <tr><td colSpan="6" className="muted">No messages yet.</td></tr>}
          </tbody>
        </table>
      </div>

      {log.length > 0 && (
        <div className="card">
          <h3>Activity</h3>
          <ul className="muted" style={{ margin: 0, paddingLeft: 18 }}>
            {log.map((l, i) => <li key={i} style={{ marginBottom: 4 }}>{l}</li>)}
          </ul>
        </div>
      )}
    </div>
  );
}
