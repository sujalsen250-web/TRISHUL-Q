import { Link } from "react-router-dom";
import Trident from "../components/Trident.jsx";

const STEPS = [
  ["Sign", "The Sender writes a message; TRISHUL-Q prepares every signature qubit in a random Pauli eigenstate (|0⟩,|1⟩,|+⟩,|−⟩,|+i⟩,|−i⟩) and teleports it."],
  ["Transmit", "The signature + message travel over the normal network — no quantum hardware is required. Each signature is single-use and expires in 60 s."],
  ["Verify (Layer 2)", "The Receiver measures each qubit in a random X/Y/Z Pauli basis. Matching basis → deterministic eigenvalue checked; mismatch → discarded. Per-basis QBER is reported."],
  ["Score (Layer 3)", "A Hoeffding-bounded statistical deviation D = ½·Σ|P_exp − P_obs| is compared against adaptive thresholds → ACCEPT / FLAG / REJECT."],
  ["Respond", "The forgery-probability engine (P_forge, P_honest, detection-vs-intensity) and the live SOC feed surface every attack — including unauthorized verification."],
];

const TEAM = [
  ["Aarav Menon", "Team Lead", "B.Tech CSE · coordinates architecture, SIH documentation and demo flow."],
  ["Isha Verma", "Backend Developer", "FastAPI + PostgreSQL; sessions, roles and the QDS send/verify pipeline."],
  ["Rohan Gupta", "Frontend Developer", "React UI, live charts and the landing experience."],
  ["Dr. Neha Kulkarni", "Quantum Engineer", "Teleportation, Pauli-eigenstate protocol and forgery-probability analysis."],
  ["Karthik Iyer", "Security Analyst", "Threat modelling, unauthorized-verification handling and red-team checks."],
  ["Sara Khan", "Documentation", "Problem-statement alignment, feasibility study and the evaluation report."],
];

const FEATURES = [
  ["Three detection layers", "Teleportation integrity · Pauli X/Y/Z basis checks · statistical + forgery probability."],
  ["Pauli-eigenstate QDS", "Gottesman–Chuang / teleportation-based verification with per-qubit basis transparency."],
  ["Forgery-probability engine", "Closed-form no-cloning bound (1/2)^k plus a live Monte-Carlo 8-attack suite — no ML."],
  ["Unauthorized verification as a first-class event", "Recorded, rejected and shown in the live SOC feed."],
  ["PostgreSQL persistence", "Pooled connections, indexed hot tables, historical analysis snapshots."],
  ["Role separation", "Super Admin (localhost only) · Admin (online) · Sender / Receiver (capability-based)."],
];

export default function Landing() {
  return (
    <div>
      <header className="wrap hero">
        <div className="grid g2" style={{ alignItems: "center" }}>
          <div>
            <div className="eyebrow">Threat Recognition, Identification &amp; Signature Handling under Unified Logic — Quantum</div>
            <h1>
              Teleportation-based <span className="grad">Quantum Digital Signatures</span>, secured by <span className="grad">teen shool</span>.
            </h1>
            <p className="lead">
              TRISHUL-Q signs, transmits and independently verifies messages with
              Bell-state teleportation, Pauli-eigenstate X/Y/Z verification and a
              Hoeffding-bounded forgery-probability engine. A pure software
              simulation — no quantum hardware, no ML, no fake statistics.
            </p>
            <div className="row" style={{ marginTop: 18 }}>
              <Link to="/login" className="btn primary">Sign in</Link>
              <Link to="/register" className="btn">Create account</Link>
              <Link to="/request-admin" className="btn">Request Admin Access</Link>
            </div>
            <div className="row" style={{ marginTop: 18 }}>
              <span className="chip"><span className="dot" />Sender</span>
              <span className="chip"><span className="dot ok" />Receiver</span>
              <span className="chip"><span className="dot" style={{ background: "var(--warn)" }} />Admin</span>
              <span className="chip"><span className="dot" style={{ background: "var(--bad)" }} />Super Admin · localhost</span>
            </div>
          </div>
          <div className="card" style={{ textAlign: "center" }}>
            <div style={{ display: "grid", placeItems: "center", gap: 14 }}>
              <Trident size={120} />
              <div style={{ fontWeight: 800, fontSize: 22, letterSpacing: 1 }}>TRISHUL-Q</div>
              <div className="muted" style={{ fontSize: 13 }}>
                Three prongs — three detection layers, one unified QDS logic.
              </div>
              <div className="grid g3" style={{ width: "100%", marginTop: 8 }}>
                <div className="kpi"><div className="v">1/2<sup>k</sup></div><div className="l">P_forge bound</div></div>
                <div className="kpi"><div className="v">X·Y·Z</div><div className="l">Pauli bases</div></div>
                <div className="kpi"><div className="v">3p²−2p³</div><div className="l">QEC logical</div></div>
              </div>
            </div>
          </div>
        </div>
      </header>

      <section id="how" className="wrap section">
        <h2>How it Works</h2>
        <p className="muted">Five steps, three of them detection layers.</p>
        <div className="grid" style={{ gap: 12 }}>
          {STEPS.map(([t, d], i) => (
            <div className="card step" key={t} style={{ margin: 0 }}>
              <div className="n">{i + 1}</div>
              <div>
                <b>{t}</b>
                <div className="muted" style={{ fontSize: 14 }}>{d}</div>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section id="about" className="wrap section">
        <div className="grid g2">
          <div className="card">
            <h2>Project overview</h2>
            <p className="muted">
              Quantum Digital Signatures (QDS) promise signature security rooted in
              the no-cloning theorem rather than computational hardness. TRISHUL-Q is a
              deployable, LAN/public-domain implementation of a teleportation-based QDS
              verification protocol, wrapped in an operations console: a public landing
              page, capability-based Sender/Receiver consoles, an online Admin console
              and a strictly localhost Super Admin panel.
            </p>
            <p className="muted">
              It is a <b>software simulation</b>: quantum states, teleportation, Pauli
              corrections, measurement statistics and error correction are simulated
              with exact linear algebra (NumPy). No quantum hardware is claimed.
            </p>
          </div>
          <div className="card">
            <h2>Working principle</h2>
            <p className="muted">
              Alice prepares each signature qubit in a random Pauli eigenstate and
              teleports it to Bob over a shared Bell pair. Bob measures every qubit in a
              randomly chosen Pauli basis: when his basis matches Alice's the outcome is
              the deterministic eigenvalue (a real check); when it differs the qubit is
              discarded. A forger without the states can only guess, succeeding with
              probability 1/2 per checked qubit — so P_forge = (1/2)<sup>k</sup> falls
              exponentially in the number of checks.
            </p>
          </div>
        </div>
      </section>

      <section className="wrap section">
        <h2>Important technical details</h2>
        <div className="grid g3">
          {FEATURES.map(([t, d]) => (
            <div className="card" key={t} style={{ margin: 0 }}>
              <b>{t}</b>
              <div className="muted" style={{ fontSize: 14, marginTop: 6 }}>{d}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="wrap section">
        <div className="card">
          <h2>High-level SIH alignment</h2>
          <p className="muted">
            Directly addresses the SIH QDS problem statement: teleportation-based
            verification, Pauli-eigenstate basis checking, forgery-probability analysis,
            unauthorized verification as a named attack, honest acceptance (P_honest ≈ 1),
            FPR/FNR behaviour versus attack intensity, and an honest, live-data-only
            security-analytics panel. Every number in the panel is produced by the live
            engine or read from PostgreSQL — nothing is hard-coded.
          </p>
        </div>
      </section>

      <section id="team" className="wrap section">
        <h2>Team</h2>
        <p className="muted">Six members (experimental placeholders — replace with your team).</p>
        <div className="grid g3">
          {TEAM.map(([name, role, bio]) => (
            <div className="card team-card" key={name} style={{ margin: 0 }}>
              <div className="avatar">{name.split(" ").map((w) => w[0]).slice(0, 2).join("")}</div>
              <b>{name}</b>
              <div style={{ color: "var(--accent-2)", fontWeight: 700, fontSize: 13 }}>{role}</div>
              <div className="muted" style={{ fontSize: 13, marginTop: 6 }}>{bio}</div>
            </div>
          ))}
        </div>
      </section>

      <footer className="site">
        <div className="wrap grid g3">
          <div>
            <div className="row"><Trident size={30} /><b style={{ fontSize: 16 }}>TRISHUL-Q</b></div>
            <p className="muted" style={{ marginTop: 8 }}>
              Threat Recognition, Identification &amp; Signature Handling under Unified Logic — Quantum.
            </p>
          </div>
          <div>
            <b>Platform</b>
            <div className="muted" style={{ marginTop: 6, lineHeight: 1.9 }}>
              <div><Link to="/login">Login</Link></div>
              <div><Link to="/register">Register</Link></div>
              <div><Link to="/request-admin">Request Admin Access</Link></div>
            </div>
          </div>
          <div>
            <b>Notes</b>
            <p className="muted" style={{ marginTop: 6 }}>
              Software simulation · no quantum hardware · no ML.
              Super Admin panel is localhost-only.
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}
