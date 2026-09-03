import React, { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";

export default function AuditLogs() {
  const [items, setItems] = useState([]);
  useEffect(() => { api.get("/audit-logs").then(r => setItems(r.data)); }, []);

  return (
    <div className="space-y-6" data-testid="audit-page">
      <div>
        <div className="text-xs font-mono uppercase tracking-widest text-primary mb-1">Compliance</div>
        <h1 className="font-heading font-extrabold uppercase text-3xl sm:text-4xl tracking-tight">Audit Logs</h1>
      </div>
      <div className="tactical-card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-secondary/60 border-b border-border">
            <tr>{["When", "User", "Action", "Entity", "Details"].map(h => <th key={h} className="text-left px-4 py-3 font-mono uppercase text-xs tracking-widest text-muted-foreground">{h}</th>)}</tr>
          </thead>
          <tbody>
            {items.map(a => (
              <tr key={a.id} className="border-b border-border hover:bg-secondary/30">
                <td className="px-4 py-3 font-mono text-xs text-muted-foreground whitespace-nowrap">{new Date(a.timestamp).toLocaleString()}</td>
                <td className="px-4 py-3 font-semibold">{a.user_name}</td>
                <td className="px-4 py-3"><Badge variant="outline" className="uppercase text-[10px] font-mono">{a.action}</Badge></td>
                <td className="px-4 py-3 font-mono text-xs">{a.entity}</td>
                <td className="px-4 py-3 text-xs text-muted-foreground max-w-md truncate">
                  {a.reason && <span className="italic">{a.reason} · </span>}
                  {a.before && <span>from {JSON.stringify(a.before)}</span>}{" "}
                  {a.after && <span>to {JSON.stringify(a.after)}</span>}
                </td>
              </tr>
            ))}
            {items.length === 0 && <tr><td colSpan={5} className="text-center py-16 text-muted-foreground">No audit entries yet</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
