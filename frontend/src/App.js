import React from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import Layout from "@/components/Layout";
import Login from "@/pages/Login";
import Signup from "@/pages/Signup";
import Dashboard from "@/pages/Dashboard";
import AIChat from "@/pages/AIChat";
import Scan from "@/pages/Scan";
import Products from "@/pages/Products";
import ProductDetail from "@/pages/ProductDetail";
import Inventory from "@/pages/Inventory";
import Warehouses from "@/pages/Warehouses";
import Users from "@/pages/Users";
import ImportPage from "@/pages/ImportPage";
import AuditLogs from "@/pages/AuditLogs";
import Landing from "@/pages/Landing";
import Connectors from "@/pages/Connectors";
import Approvals from "@/pages/Approvals";
import Settings from "@/pages/Settings";

const Protected = ({ children }) => {
  const { user, loading } = useAuth();
  if (loading) return <div className="min-h-screen flex items-center justify-center text-muted-foreground">Loading…</div>;
  if (!user) return <Navigate to="/login" replace />;
  return <Layout>{children}</Layout>;
};

const PublicOnly = ({ children }) => {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (user) return <Navigate to="/app/dashboard" replace />;
  return children;
};

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<PublicOnly><Login /></PublicOnly>} />
      <Route path="/signup" element={<PublicOnly><Signup /></PublicOnly>} />
      <Route path="/app" element={<Navigate to="/app/dashboard" replace />} />
      <Route path="/app/dashboard" element={<Protected><Dashboard /></Protected>} />
      <Route path="/app/ai" element={<Protected><AIChat /></Protected>} />
      <Route path="/app/scan" element={<Protected><Scan /></Protected>} />
      <Route path="/app/products" element={<Protected><Products /></Protected>} />
      <Route path="/app/products/:id" element={<Protected><ProductDetail /></Protected>} />
      <Route path="/app/inventory" element={<Protected><Inventory /></Protected>} />
      <Route path="/app/warehouses" element={<Protected><Warehouses /></Protected>} />
      <Route path="/app/users" element={<Protected><Users /></Protected>} />
      <Route path="/app/import" element={<Protected><ImportPage /></Protected>} />
      <Route path="/app/connectors" element={<Protected><Connectors /></Protected>} />
      <Route path="/app/approvals" element={<Protected><Approvals /></Protected>} />
      <Route path="/app/audit" element={<Protected><AuditLogs /></Protected>} />
      <Route path="/app/settings" element={<Protected><Settings /></Protected>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
