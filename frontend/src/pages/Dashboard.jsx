import React, { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Package, Warehouse, AlertTriangle, Boxes, Sparkles, ScanLine, Camera, Search } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, ResponsiveContainer, CartesianGrid, Tooltip } from "recharts";
import { Link } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";

const StatCard = ({ icon: Icon, label, value, accent = "primary", testid }) => (
  <div className="tactical-card p-5" data-testid={testid}>
    <div className="flex items-start justify-between">
      <div>
        <div className="text-xs font-mono uppercase tracking-widest text-muted-foreground mb-2">{label}</div>
        <div className="kpi-value text-4xl">{value ?? "—"}</div>
      </div>
      <div className={`w-10 h-10 rounded-lg flex items-center justify-center bg-${accent}/15 border border-${accent}/30`}>
        <Icon className={`w-5 h-5 text-${accent}`} />
      </div>
    </div>
  </div>
);

const QuickAction = ({ to, icon: Icon, label, testid }) => (
  <Link to={to} data-testid={testid} className="tactical-card p-5 flex flex-col items-start gap-3 hover:border-primary/50 transition-colors group">
    <div className="w-11 h-11 rounded-lg bg-primary/15 border border-primary/30 flex items-center justify-center group-hover:bg-primary/25">
      <Icon className="w-5 h-5 text-primary" />
    </div>
    <div>
      <div className="font-heading font-bold uppercase text-lg leading-tight">{label}</div>
      <div className="text-xs text-muted-foreground font-mono uppercase tracking-widest mt-0.5">Open →</div>
    </div>
  </Link>
);

export default function Dashboard() {
  const { user } = useAuth();
  const [stats, setStats] = useState(null);

  useEffect(() => {
    api.get("/dashboard/stats").then(r => setStats(r.data));
  }, []);

  return (
    <div className="space-y-8" data-testid="dashboard-page">
      <div>
        <div className="text-xs font-mono uppercase tracking-widest text-primary mb-2">Command Center</div>
        <h1 className="font-heading font-extrabold uppercase text-4xl sm:text-5xl tracking-tight">Welcome, {user?.name?.split(" ")[0]}</h1>
        <p className="text-muted-foreground mt-2">{user?.org_name} · Live snapshot of your inventory</p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard icon={Package} label="Products" value={stats?.total_products} testid="stat-products" />
        <StatCard icon={Boxes} label="Total Units" value={stats?.total_units} accent="accent" testid="stat-units" />
        <StatCard icon={AlertTriangle} label="Low Stock" value={stats?.low_stock} accent="destructive" testid="stat-low-stock" />
        <StatCard icon={Warehouse} label="Warehouses" value={stats?.total_warehouses} accent="accent" testid="stat-warehouses" />
      </div>

      <div>
        <h2 className="font-heading font-bold text-xl uppercase mb-4">Quick Actions</h2>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <QuickAction to="/app/ai" icon={Sparkles} label="Ask AI" testid="quick-ai" />
          <QuickAction to="/app/scan" icon={ScanLine} label="Scan Barcode" testid="quick-scan" />
          <QuickAction to="/app/scan" icon={Camera} label="Photo ID" testid="quick-photo" />
          <QuickAction to="/app/products" icon={Search} label="Find Product" testid="quick-find" />
        </div>
      </div>

      <div className="grid lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-2 bg-card border-border">
          <CardHeader>
            <CardTitle className="font-heading uppercase text-lg">Stock by Warehouse</CardTitle>
          </CardHeader>
          <CardContent>
            {stats?.stock_by_warehouse?.length ? (
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={stats.stock_by_warehouse}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.4} />
                    <XAxis dataKey="name" stroke="hsl(var(--muted-foreground))" fontSize={12} />
                    <YAxis stroke="hsl(var(--muted-foreground))" fontSize={12} />
                    <Tooltip contentStyle={{ background: "hsl(var(--popover))", border: "1px solid hsl(var(--border))", borderRadius: 8 }} />
                    <Bar dataKey="units" fill="hsl(var(--primary))" radius={[6, 6, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <div className="text-muted-foreground text-sm py-16 text-center">No warehouse data yet</div>
            )}
          </CardContent>
        </Card>

        <Card className="bg-card border-border">
          <CardHeader>
            <CardTitle className="font-heading uppercase text-lg">Recent Activity</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {stats?.recent_activity?.length ? stats.recent_activity.map((a) => (
              <div key={a.id} className="flex items-start gap-2 text-sm p-2 rounded hover:bg-secondary/50">
                <Badge variant="outline" className="text-[10px] font-mono uppercase shrink-0">{a.action}</Badge>
                <div className="min-w-0 flex-1">
                  <div className="font-medium truncate">{a.entity} · {a.user_name}</div>
                  <div className="text-xs text-muted-foreground font-mono">{new Date(a.timestamp).toLocaleString()}</div>
                </div>
              </div>
            )) : <div className="text-muted-foreground text-sm py-8 text-center">No activity yet</div>}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
