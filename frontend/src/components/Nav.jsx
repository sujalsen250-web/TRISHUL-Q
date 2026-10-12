import { Link } from "react-router-dom";
import Trident from "./Trident.jsx";

export default function Nav({ me, onLogout }) {
  return (
    <nav className="nav">
      <div className="wrap nav-inner">
        <Link to="/" className="brand" style={{ textDecoration: "none", color: "inherit" }}>
          <Trident size={36} />
          <span>
            <span className="word">TRISHUL-Q</span>
            <br />
            <small>THREE LAYERS · ONE LOGIC</small>
          </span>
        </Link>
        <div className="nav-links">
          <Link to="/">Home</Link>
          <a href="/#about">About Project</a>
          <a href="/#how">How it Works</a>
          <a href="/#team">Team</a>
          <Link to="/request-admin">Request Admin Access</Link>
          {me ? (
            <>
              <Link to={me.role === "admin" ? "/admin" : (me.capabilities || []).includes("receive") ? "/receiver" : "/sender"} className="cta">
                {me.role === "admin" ? "Admin Console" : "My Console"}
              </Link>
              <button onClick={onLogout}>Logout</button>
            </>
          ) : (
            <Link to="/login" className="cta">Login</Link>
          )}
        </div>
      </div>
    </nav>
  );
}
