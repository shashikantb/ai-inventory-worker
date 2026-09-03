import React, { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { AlertTriangle, Package } from "lucide-react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";

export default function Inventory() {
  const [items, setItems] = useState([]);
  const [tab, setTab] = useState("all");

  const load = (lowOnly) => api.get("/inventory", { params: lowOnly ? { low_stock: true } : {} }).then(r => setItems(r.data));
  useEffect(() => { load(tab === "low"); }, [tab]);

  return (
    <div className="space-y-6" data-testid="inventory-page">
      <div>
        <div className="text-xs font-mono uppercase tracking-widest text-primary mb-1">Stock</div>
        <h1 className="font-heading font-extrabold uppercase text-3xl sm:text-4xl tracking-tight">Inventory</h1>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="all" data-testid="tab-all-inv">All stock</TabsTrigger>
          <TabsTrigger value="low" data-testid="tab-low-stock"><AlertTriangle className="w-3.5 h-3.5 mr-1.5" /> Low stock</TabsTrigger>
        </TabsList>

        <TabsContent value={tab} className="mt-4">
          <div className="tactical-card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-secondary/60 border-b border-border">
                  <tr>
                    {["Product", "SKU", "Warehouse", "Qty", "Available", "Reorder", "Status"].map(h =>
                      <th key={h} className="text-left px-4 py-3 font-mono uppercase text-xs tracking-widest text-muted-foreground">{h}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {items.map(inv => {
                    const avail = inv.quantity - (inv.reserved_quantity || 0);
                    const low = inv.quantity <= (inv.reorder_level || 10);
                    const out = inv.quantity === 0;
                    return (
                      <tr key={inv.id} className="border-b border-border hover:bg-secondary/30" data-testid={`inv-${inv.id}`}>
                        <td className="px-4 py-3">
                          <Link to={`/app/products/${inv.product_id}`} className="font-semibold hover:text-primary flex items-center gap-2">
                            <Package className="w-4 h-4 text-muted-foreground" />
                            {inv.product?.name || "—"}
                          </Link>
                        </td>
                        <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{inv.product?.sku}</td>
                        <td className="px-4 py-3">{inv.warehouse_name}</td>
                        <td className="px-4 py-3 font-mono font-bold">{inv.quantity}</td>
                        <td className="px-4 py-3 font-mono">{avail}</td>
                        <td className="px-4 py-3 font-mono text-muted-foreground">{inv.reorder_level || 10}</td>
                        <td className="px-4 py-3">
                          {out ? <Badge variant="destructive">Out</Badge> : low ? <Badge className="bg-amber-500/20 text-amber-400 border-amber-500/30">Low</Badge> : <Badge variant="outline" className="text-emerald-400 border-emerald-500/40">OK</Badge>}
                        </td>
                      </tr>
                    );
                  })}
                  {items.length === 0 && <tr><td colSpan={7} className="text-center py-16 text-muted-foreground">No inventory records</td></tr>}
                </tbody>
              </table>
            </div>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
