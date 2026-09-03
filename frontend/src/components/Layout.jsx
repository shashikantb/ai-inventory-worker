import React, { useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { LayoutDashboard, MessageSquare, ScanLine, Package, Warehouse, Users, Upload, ScrollText, LogOut, Menu, X, Sparkles, Boxes, Plug, ClipboardCheck } from "lucide-react";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";

const NAV = [
  { to: "/app/dashboard", label: "Dashboard", icon: LayoutDashboard, testid: "nav-dashboard" },
  { to: "/app/ai", label: "AI Assistant", icon: Sparkles, testid: "nav-ai" },
  { to: "/app/scan", label: "Scan", icon: ScanLine, testid: "nav-scan" },
  { to: "/app/products", label: "Products", icon: Package, testid: "nav-products" },
  { to: "/app/inventory", label: "Inventory", icon: Boxes, testid: "nav-inventory" },
  { to: "/app/warehouses", label: "Warehouses", icon: Warehouse, testid: "nav-warehouses" },
  { to: "/app/import", label: "Import", icon: Upload, testid: "nav-import" },
  { to: "/app/connectors", label: "Connectors", icon: Plug, testid: "nav-connectors", roles: ["org_admin"] },
  { to: "/app/approvals", label: "Approvals", icon: ClipboardCheck, testid: "nav-approvals", roles: ["org_admin", "manager"] },
  { to: "/app/users", label: "Users", icon: Users, testid: "nav-users", roles: ["org_admin", "manager"] },
  { to: "/app/audit", label: "Audit Logs", icon: ScrollText, testid: "nav-audit", roles: ["org_admin", "manager"] },
];

const SidebarBody = ({ user, onClose }) => (
  <div className="flex flex-col h-full bg-card border-r border-border">
    <div className="p-5 border-b border-border">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-lg bg-primary flex items-center justify-center pulse-amber">
          <ScanLine className="w-5 h-5 text-primary-foreground" strokeWidth={2.5} />
        </div>
        <div>
          <div className="font-heading font-extrabold text-lg uppercase tracking-wide leading-none">AI Inventory</div>
          <div className="text-[10px] font-mono uppercase text-muted-foreground tracking-widest mt-1">Worker · v1.0</div>
        </div>
      </div>
    </div>
    <nav className="flex-1 p-3 overflow-y-auto space-y-1">
      {NAV.filter(n => !n.roles || n.roles.includes(user?.role)).map((n) => (
        <NavLink
          key={n.to}
          to={n.to}
          onClick={onClose}
          data-testid={n.testid}
          className={({ isActive }) => `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${isActive ? "bg-primary/15 text-primary border border-primary/30" : "text-muted-foreground hover:bg-secondary hover:text-foreground border border-transparent"}`}
        >
          <n.icon className="w-4 h-4" />
          <span>{n.label}</span>
        </NavLink>
      ))}
    </nav>
    <div className="p-4 border-t border-border">
      <div className="text-xs text-muted-foreground mb-1 font-mono uppercase tracking-wider">Signed in</div>
      <div className="text-sm font-semibold truncate" data-testid="sidebar-user-name">{user?.name}</div>
      <div className="text-xs text-muted-foreground truncate mb-2">{user?.email}</div>
      <Badge variant="outline" className="text-[10px] font-mono uppercase mb-3">{user?.role?.replace("_", " ")}</Badge>
      <div className="text-xs font-mono text-muted-foreground truncate">{user?.org_name}</div>
    </div>
  </div>
);

export default function Layout({ children }) {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);

  return (
    <div className="min-h-screen flex bg-background">
      <aside className="hidden lg:block w-64 shrink-0 sticky top-0 h-screen">
        <SidebarBody user={user} onClose={() => {}} />
      </aside>

      <div className="flex-1 flex flex-col min-w-0">
        <header className="sticky top-0 z-30 bg-background/80 backdrop-blur-md border-b border-border">
          <div className="flex items-center justify-between px-4 lg:px-6 h-14">
            <div className="flex items-center gap-3">
              <Sheet open={open} onOpenChange={setOpen}>
                <SheetTrigger asChild>
                  <Button variant="ghost" size="icon" className="lg:hidden" data-testid="mobile-menu-btn">
                    <Menu className="w-5 h-5" />
                  </Button>
                </SheetTrigger>
                <SheetContent side="left" className="p-0 w-72">
                  <SidebarBody user={user} onClose={() => setOpen(false)} />
                </SheetContent>
              </Sheet>
              <div className="font-mono text-xs uppercase tracking-widest text-muted-foreground hidden sm:block">
                Ask · Scan · Find · Act
              </div>
            </div>
            <Button variant="ghost" size="sm" onClick={() => { logout(); nav("/login"); }} data-testid="logout-btn">
              <LogOut className="w-4 h-4 mr-2" /> Log out
            </Button>
          </div>
        </header>
        <main className="flex-1 p-4 lg:p-8">{children}</main>
      </div>
    </div>
  );
}
