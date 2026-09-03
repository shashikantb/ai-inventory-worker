import React, { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ArrowLeft, Package, MapPin, Edit3 } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";

export default function ProductDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [adjOpen, setAdjOpen] = useState(false);
  const [adjForm, setAdjForm] = useState({ inventory_id: "", new_quantity: 0, reason: "" });

  const load = () => api.get(`/products/${id}`).then(r => setData(r.data));
  useEffect(() => { load(); }, [id]);

  const openAdjust = (inv) => { setAdjForm({ inventory_id: inv.id, new_quantity: inv.quantity, reason: "" }); setAdjOpen(true); };

  const submitAdjust = async (e) => {
    e.preventDefault();
    try {
      await api.post("/inventory/adjust", { ...adjForm, new_quantity: parseInt(adjForm.new_quantity, 10) });
      toast.success("Inventory updated");
      setAdjOpen(false);
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed");
    }
  };

  if (!data) return <div className="text-muted-foreground">Loading…</div>;
  const { product, inventory } = data;
  const canAdjust = ["org_admin", "manager", "worker"].includes(user?.role);

  return (
    <div className="max-w-4xl mx-auto space-y-6" data-testid="product-detail-page">
      <Link to="/app/products" className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="w-4 h-4" /> Back to products</Link>

      <div className="tactical-card p-6">
        <div className="flex items-start gap-4 flex-wrap">
          <div className="w-24 h-24 rounded-lg bg-secondary flex items-center justify-center shrink-0"><Package className="w-10 h-10 text-muted-foreground" /></div>
          <div className="flex-1 min-w-0">
            <div className="text-xs font-mono uppercase text-muted-foreground">SKU · {product.sku}</div>
            <h1 className="font-heading font-extrabold uppercase text-3xl tracking-tight mt-1">{product.name}</h1>
            <div className="flex gap-2 flex-wrap mt-3">
              {product.barcode && <Badge variant="outline" className="font-mono">Barcode {product.barcode}</Badge>}
              {product.brand && <Badge>{product.brand}</Badge>}
              {product.category && <Badge variant="secondary">{product.category}</Badge>}
              {product.model_number && <Badge variant="outline">Model {product.model_number}</Badge>}
            </div>
            {product.description && <p className="text-sm text-muted-foreground mt-3">{product.description}</p>}
          </div>
        </div>
      </div>

      <div>
        <h2 className="font-heading font-bold text-xl uppercase mb-3">Inventory & Locations</h2>
        <div className="space-y-2">
          {inventory.length === 0 && <div className="tactical-card p-6 text-center text-muted-foreground">No inventory records yet</div>}
          {inventory.map(inv => {
            const avail = inv.quantity - (inv.reserved_quantity || 0);
            const low = inv.quantity <= (inv.reorder_level || 10);
            return (
              <div key={inv.id} className="tactical-card p-4 flex items-center justify-between gap-4 flex-wrap" data-testid={`inv-row-${inv.id}`}>
                <div className="flex items-start gap-3 min-w-0">
                  <MapPin className="w-5 h-5 text-primary mt-0.5" />
                  <div className="min-w-0">
                    <div className="font-semibold">{inv.warehouse_name}</div>
                    {inv.location_path && <div className="text-xs font-mono text-muted-foreground">{inv.location_path}</div>}
                  </div>
                </div>
                <div className="flex items-center gap-4">
                  <div className="text-right">
                    <div className="kpi-value text-2xl">{inv.quantity}</div>
                    <div className="text-[10px] uppercase text-muted-foreground font-mono">{avail} available</div>
                  </div>
                  {low && <Badge variant="destructive">Low</Badge>}
                  {canAdjust && <Button size="sm" variant="outline" onClick={() => openAdjust(inv)} data-testid={`adjust-btn-${inv.id}`}><Edit3 className="w-3.5 h-3.5 mr-1.5" /> Adjust</Button>}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <Dialog open={adjOpen} onOpenChange={setAdjOpen}>
        <DialogContent className="bg-card">
          <DialogHeader><DialogTitle className="font-heading uppercase">Adjust inventory</DialogTitle></DialogHeader>
          <form onSubmit={submitAdjust} className="space-y-3">
            <div>
              <Label>New quantity</Label>
              <Input type="number" value={adjForm.new_quantity} onChange={e => setAdjForm({...adjForm, new_quantity: e.target.value})} required data-testid="adjust-qty-input" className="mt-1" />
            </div>
            <div>
              <Label>Reason</Label>
              <Textarea value={adjForm.reason} onChange={e => setAdjForm({...adjForm, reason: e.target.value})} required data-testid="adjust-reason-input" className="mt-1" />
            </div>
            <Button type="submit" className="w-full bg-primary text-primary-foreground" data-testid="adjust-submit-btn">Confirm adjustment</Button>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
