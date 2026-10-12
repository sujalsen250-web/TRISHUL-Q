import { useEffect, useState } from "react";
import { api } from "../api.js";
import { useAuth } from "../App.jsx";

export default function Receiver() {
  const { me } = useAuth();
  const [inbox, setInbox] = useState([]);
  const [detail, setDetail] = useState(null);
  const [err, setErr] = useState("");

  async function load() {
    try { setInbox((await api("/api/messages/received")).messages); } catch (e) { /* */ }
  }
  useEffect(() => { load(); }, []);

  async function open(id) {
    setErr(""); setDetail(null);
    try { setDetail(await api(`/api/messages/${id}`)); }
    catch (ex) { setErr(ex.message); }
  }
  async function reverify(id) {
    try { const r = await api(`/api/verify/${id}`, { method: "POST" }); setDetail((d) => ({ ...d, verdict: r.verdict })); load(); }
    catch (ex) { setErr(ex.message); }
  }
  async function ack(id, status) {
    try { await api(`/api/messages/${id}/ack`, { method: "POST", body: { status } }); load(); }
    catch (ex) { setErr(ex.message); }
  }

  const pv = detail?.verdict?.pauli_verification;

  return (
    <div className="wrap" style={{ paddingTop: 26, paddingBottom: 40 }}>
      <h2>Receiver Console</h2>
      <p className="muted">Signed in as <b>{me?.full_name}</b> · {me?.department}</p>
      {err && <div className="alert error">{err}</div>}

      <div className="grid g2">
        <div className="card">
          <h3>Inbox</h3>
          <table>
            <thead><tr><th>ID</th><th>From</th><th>Status</th><th>D</th><th></th></tr></thead>
            <tbody>
              {inbox.map((m) => (
                <tr key={m.message_id}>
                  <td className="mono">{m.message_id}</td>
                  <td>{m.sender_name || m.sender_id}</td>
                  <td><span className={`badge ${m.status}`}>{m.status}</span></td>
                  <td className="mono">{m.deviation}</td>
                  <td><button className="btn sm" onClick={() => open(m.message_id)}>Open</button></td>
                </tr>
              ))}
              {!inbox.length && <tr><td colSpan="5" className="muted">Inbox empty.</td></tr>}
            </tbody>
          </table>
        </div>

        <div className="card">
          <h3>Verification view</h3>
          {!detail ? <p className="muted">Open a message to inspect its three detection layers.</p> : (
            <>
              <div className="row">
                <span className={`badge ${detail.verdict?.classification}`}>{detail.verdict?.classification}</span>
                <span className="chip">Action: {detail.verdict?.action}</span>
                <span className="chip">D = {detail.verdict?.deviation}</span>
                <span className="chip">Bell {detail.verdict?.bell_symbol}</span>
              </div>
              <p style={{ marginTop: 12 }}>{detail.message?.message}</p>

              {pv && (
                <>
                  <h4 style={{ marginTop: 12 }}>Pauli X/Y/Z checks (Layer 2)</h4>
                  <table>
                    <thead><tr><th>Basis</th><th>Checks</th><th>Mismatches</th><th>QBER</th></tr></thead>
                    <tbody>
                      {["X", "Y", "Z"].map((b) => (
                        <tr key={b}>
                          <td>Pauli-{b}</td>
                          <td className="mono">{pv.bases?.[b]?.checks ?? 0}</td>
                          <td className="mono">{pv.bases?.[b]?.mismatches ?? 0}</td>
                          <td className="mono">{pv.bases?.[b]?.qber ?? "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <p className="muted" style={{ marginTop: 8 }}>
                    Checked {pv.checked} · discarded {pv.discarded} · mismatch rate {pv.mismatch_rate}
                    {" "}(threshold {pv.threshold}) · {pv.passed ? "PASSED" : "FAILED"}
                  </p>
                </>
              )}

              <div className="row" style={{ marginTop: 12 }}>
                <button className="btn sm" onClick={() => reverify(detail.message.message_id)}>Re-verify</button>
                <button className="btn sm" onClick={() => ack(detail.message.message_id, "READ")}>Mark read</button>
                <button className="btn sm" onClick={() => ack(detail.message.message_id, "FAILED")}>Report failed</button>
                {detail.message?.file_name && (
                  <a className="btn sm" href={`/api/messages/${detail.message.message_id}/file`}>Download attachment</a>
                )}
              </div>

              {detail.verdict?.reasons?.length > 0 && (
                <div className="alert warn" style={{ marginTop: 12 }}>
                  {detail.verdict.reasons.map((r, i) => <div key={i}>• {r}</div>)}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
