import { createContext, useContext, useEffect, useState } from "react";
import { Routes, Route, Navigate, useNavigate } from "react-router-dom";
import { api } from "./api.js";
import Nav from "./components/Nav.jsx";
import Landing from "./pages/Landing.jsx";
import Login from "./pages/Login.jsx";
import Register from "./pages/Register.jsx";
import RequestAdmin from "./pages/RequestAdmin.jsx";
import ForgotPassword from "./pages/ForgotPassword.jsx";
import ResetPassword from "./pages/ResetPassword.jsx";
import ChangePassword from "./pages/ChangePassword.jsx";
import Sender from "./pages/Sender.jsx";
import Receiver from "./pages/Receiver.jsx";
import Admin from "./pages/Admin.jsx";

export const AuthContext = createContext({ me: null, refresh: () => {} });
export const useAuth = () => useContext(AuthContext);

function homeFor(me) {
  if (!me) return "/";
  if (me.role === "admin") return "/admin";
  return (me.capabilities || []).includes("receive") ? "/receiver" : "/sender";
}

function Protected({ children, require: req }) {
  const { me } = useAuth();
  if (me === undefined) return <div className="center-wrap muted">Loading…</div>;
  if (!me) return <Navigate to="/login" replace />;
  // forced first-login password change
  if (me.must_change_password) return <Navigate to="/change-password" replace />;
  if (req === "admin" && me.role !== "admin") return <Navigate to="/" replace />;
  if (req === "send" && !(me.capabilities || []).includes("send") && me.role !== "admin")
    return <Navigate to="/receiver" replace />;
  if (req === "receive" && !(me.capabilities || []).includes("receive") && me.role !== "admin")
    return <Navigate to="/sender" replace />;
  return children;
}

export default function App() {
  const [me, setMe] = useState(undefined);
  const navigate = useNavigate();

  async function refresh() {
    try { setMe(await api("/api/auth/me")); }
    catch (e) { setMe(null); }
  }
  useEffect(() => { refresh(); }, []);

  async function logout() {
    try { await api("/api/auth/logout", { method: "POST" }); } catch (e) { /* */ }
    setMe(null);
    navigate("/");
  }

  return (
    <AuthContext.Provider value={{ me, refresh }}>
      <Nav me={me} onLogout={logout} />
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/request-admin" element={<RequestAdmin />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="/reset-password" element={<ResetPassword />} />
        <Route path="/change-password" element={
          me ? <ChangePassword forced={!!me.must_change_password} /> : <Navigate to="/login" replace />
        } />
        <Route path="/sender" element={<Protected require="send"><Sender /></Protected>} />
        <Route path="/receiver" element={<Protected require="receive"><Receiver /></Protected>} />
        <Route path="/admin" element={<Protected require="admin"><Admin /></Protected>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthContext.Provider>
  );
}
