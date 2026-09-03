import React, { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Plus, Warehouse as WhIcon, MapPin } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";

export default function Warehouses() {
  const { user } = useAuth();
  const [items, setItems] = useState([]);
  const [locs, setLocs] = useState([]);
  const [open, setOpen] = useState(false);
  const [locOpen, setLocOpen] = useState(false);
  const [form, setForm] = useState({ name: "", code: "", address: "" });
  const [locForm, setLocForm] = useState({ warehouse_id: "", parent_id: "", type: "zone", name: "", code: "" });

  const load = async () => {
    const [w, l] = await Promise.all([api.get("/warehouses"), api.get("/locations")]);
    setItems(w.data); setLocs(l.data);
  };
  useEffect(() => { load(); }, []);

  const create = async (e) => {
    e.preventDefault();
    try { await api.post("/warehouses", form); toast.success("Warehouse added"); setOpen(false); setForm({ name: "", code: "", address: "" }); load(); }
    catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };

  const createLoc = async (e) => {
    e.preventDefault();
    try {
      const payload = { ...locForm, parent_id: locForm.parent_id || null };
      await api.post("/locations", payload);
      toast.success("Location added"); setLocOpen(false);
      setLocForm({ warehouse_id: locForm.warehouse_id, parent_id: "", type: "zone", name: "", code: "" });
      load();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };

  const canEdit = ["org_admin", "manager"].includes(user?.role);

  return (
    <div className="space-y-6" data-testid="warehouses-page">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="text-xs font-mono uppercase tracking-widest text-primary mb-1">Facilities</div>
          <h1 className="font-heading font-extrabold uppercase text-3xl sm:text-4xl tracking-tight">Warehouses</h1>
        </div>
        {canEdit && (
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild><Button className="bg-primary text-primary-foreground" data-testid="add-warehouse-btn"><Plus className="w-4 h-4 mr-2" /> Add warehouse</Button></DialogTrigger>
            <DialogContent className="bg-card">
              <DialogHeader><DialogTitle className="font-heading uppercase">New warehouse</DialogTitle></DialogHeader>
              <form onSubmit={create} className="space-y-3">
                <div><Label>Name</Label><Input value={form.name} onChange={e => setForm({...form, name: e.target.value})} required data-testid="wh-name-input" className="mt-1" /></div>
                <div><Label>Code</Label><Input value={form.code} onChange={e => setForm({...form, code: e.target.value})} required data-testid="wh-code-input" className="mt-1" /></div>
                <div><Label>Address</Label><Input value={form.address} onChange={e => setForm({...form, address: e.target.value})} data-testid="wh-addr-input" className="mt-1" /></div>
                <Button type="submit" className="w-full bg-primary text-primary-foreground" data-testid="wh-save-btn">Save</Button>
              </form>
            </DialogContent>
          </Dialog>
        )}
      </div>

      <div className="grid md:grid-cols-2 gap-4">
        {items.map(w => {
          const wlocs = locs.filter(l => l.warehouse_id === w.id);
          return (
            <div key={w.id} className="tactical-card p-5" data-testid={`wh-card-${w.code}`}>
              <div className="flex items-start gap-3">
                <div className="w-11 h-11 rounded-lg bg-primary/15 border border-primary/30 flex items-center justify-center"><WhIcon className="w-5 h-5 text-primary" /></div>
                <div className="flex-1 min-w-0">
                  <div className="font-heading font-bold uppercase text-xl">{w.name}</div>
                  <div className="text-xs font-mono text-muted-foreground">Code · {w.code}</div>
                  {w.address && <div className="text-sm text-muted-foreground mt-1">{w.address}</div>}
                </div>
                {canEdit && (
                  <Button size="sm" variant="outline" onClick={() => { setLocForm({ ...locForm, warehouse_id: w.id }); setLocOpen(true); }} data-testid={`add-loc-${w.code}`}>
                    <Plus className="w-3.5 h-3.5" />
                  </Button>
                )}
              </div>
              <div className="mt-4 space-y-1 max-h-40 overflow-y-auto">
                {wlocs.length === 0 && <div className="text-xs text-muted-foreground italic">No locations yet</div>}
                {wlocs.map(l => (
                  <div key={l.id} className="text-xs font-mono flex items-center gap-2 py-1">
                    <MapPin className="w-3 h-3 text-muted-foreground" />
                    <span className="uppercase text-muted-foreground">{l.type}</span>
                    <span className="font-semibold">{l.name}</span>
                    <span className="text-muted-foreground">· {l.code}</span>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
        {items.length === 0 && <div className="col-span-full text-center py-16 text-muted-foreground">No warehouses yet</div>}
      </div>

      <Dialog open={locOpen} onOpenChange={setLocOpen}>
        <DialogContent className="bg-card">
          <DialogHeader><DialogTitle className="font-heading uppercase">New location</DialogTitle></DialogHeader>
          <form onSubmit={createLoc} className="space-y-3">
            <div><Label>Type</Label>
              <Select value={locForm.type} onValueChange={v => setLocForm({...locForm, type: v})}>
                <SelectTrigger className="mt-1" data-testid="loc-type-select"><SelectValue /></SelectTrigger>
                <SelectContent>{["zone", "aisle", "rack", "shelf", "bin"].map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div><Label>Parent (optional)</Label>
              <Select value={locForm.parent_id || "none"} onValueChange={v => setLocForm({...locForm, parent_id: v === "none" ? "" : v})}>
                <SelectTrigger className="mt-1" data-testid="loc-parent-select"><SelectValue placeholder="Top level" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">Top level</SelectItem>
                  {locs.filter(l => l.warehouse_id === locForm.warehouse_id).map(l =>
                    <SelectItem key={l.id} value={l.id}>{l.type} · {l.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div><Label>Name</Label><Input value={locForm.name} onChange={e => setLocForm({...locForm, name: e.target.value})} required data-testid="loc-name-input" className="mt-1" /></div>
            <div><Label>Code</Label><Input value={locForm.code} onChange={e => setLocForm({...locForm, code: e.target.value})} required data-testid="loc-code-input" className="mt-1" /></div>
            <Button type="submit" className="w-full bg-primary text-primary-foreground" data-testid="loc-save-btn">Save</Button>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
