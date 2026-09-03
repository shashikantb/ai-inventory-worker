import React, { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Plug, Plus, Trash2, RefreshCw, PlayCircle, CheckCircle2, XCircle } from "lucide-react";
import { toast } from "sonner";

const KIND_LABELS = { rest: "REST API", postgresql: "PostgreSQL", mysql: "MySQL" };

const restDefaults = { url: "", auth_header: "", auth_value: "", data_path: "", field_map: { sku: "sku", name: "name", barcode: "barcode", brand: "brand", category: "category", model_number: "model_number" } };
const dbDefaults = { host: "", port: "", user: "", password: "", database: "", table: "products", query: "", field_map: { sku: "sku", name: "name", barcode: "barcode", brand: "brand", category: "category", model_number: "model_number" } };

export default function Connectors() {
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", kind: "rest", config: { ...restDefaults } });
  const [testRes, setTestRes] = useState({});
  const [busy, setBusy] = useState({});

  const load = () => api.get("/connectors").then(r => setItems(r.data));
  useEffect(() => { load(); }, []);

  const changeKind = (k) => setForm({ ...form, kind: k, config: k === "rest" ? { ...restDefaults } : { ...dbDefaults } });
  const setCfg = (k, v) => setForm({ ...form, config: { ...form.config, [k]: v } });
  const setMap = (std, src) => setForm({ ...form, config: { ...form.config, field_map: { ...form.config.field_map, [std]: src } } });

  const save = async (e) => {
    e.preventDefault();
    try {
      await api.post("/connectors", form);
      toast.success("Connector saved");
      setOpen(false);
      setForm({ name: "", kind: "rest", config: { ...restDefaults } });
      load();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };

  const test = async (id) => {
    setBusy({ ...busy, [id]: "test" });
    try {
      const { data } = await api.post(`/connectors/${id}/test`);
      setTestRes({ ...testRes, [id]: data });
      if (data.ok) toast.success(`Fetched ${data.count} sample rows`);
      else toast.error(data.error);
    } catch (err) { toast.error(err.response?.data?.detail || "Test failed"); }
    finally { setBusy({ ...busy, [id]: null }); }
  };

  const sync = async (id) => {
    if (!window.confirm("Sync now? This will import/update products.")) return;
    setBusy({ ...busy, [id]: "sync" });
    try {
      const { data } = await api.post(`/connectors/${id}/sync`);
      toast.success(`Imported ${data.imported}, updated ${data.updated}, skipped ${data.skipped}`);
      load();
    } catch (err) { toast.error(err.response?.data?.detail || "Sync failed"); }
    finally { setBusy({ ...busy, [id]: null }); }
  };

  const del = async (id) => {
    if (!window.confirm("Delete this connector?")) return;
    await api.delete(`/connectors/${id}`);
    toast.success("Deleted"); load();
  };

  const stdFields = ["sku", "name", "barcode", "brand", "category", "model_number", "description"];

  return (
    <div className="space-y-6" data-testid="connectors-page">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="text-xs font-mono uppercase tracking-widest text-primary mb-1">Integrations</div>
          <h1 className="font-heading font-extrabold uppercase text-3xl sm:text-4xl tracking-tight">ERP Connectors</h1>
          <p className="text-sm text-muted-foreground mt-2 max-w-2xl">Sync your existing REST API, PostgreSQL, or MySQL catalog into AIW. Map their fields to ours — no ERP replacement needed.</p>
        </div>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild><Button className="bg-primary text-primary-foreground" data-testid="add-connector-btn"><Plus className="w-4 h-4 mr-2" /> New connector</Button></DialogTrigger>
          <DialogContent className="bg-card max-w-lg max-h-[85vh] overflow-y-auto">
            <DialogHeader><DialogTitle className="font-heading uppercase">New connector</DialogTitle></DialogHeader>
            <form onSubmit={save} className="space-y-3">
              <div><Label>Name</Label><Input value={form.name} onChange={e => setForm({...form, name: e.target.value})} required data-testid="conn-name-input" className="mt-1" /></div>
              <div><Label>Kind</Label>
                <Select value={form.kind} onValueChange={changeKind}>
                  <SelectTrigger className="mt-1" data-testid="conn-kind-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="rest">REST API</SelectItem>
                    <SelectItem value="postgresql">PostgreSQL</SelectItem>
                    <SelectItem value="mysql">MySQL</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {form.kind === "rest" ? (
                <>
                  <div><Label>Endpoint URL *</Label><Input value={form.config.url} onChange={e => setCfg("url", e.target.value)} placeholder="https://api.example.com/products" required data-testid="conn-url-input" className="mt-1" /></div>
                  <div className="grid grid-cols-2 gap-2">
                    <div><Label>Auth header</Label><Input value={form.config.auth_header} onChange={e => setCfg("auth_header", e.target.value)} placeholder="Authorization" className="mt-1" /></div>
                    <div><Label>Auth value</Label><Input value={form.config.auth_value} onChange={e => setCfg("auth_value", e.target.value)} placeholder="Bearer xxx" className="mt-1" /></div>
                  </div>
                  <div><Label>JSON data path (optional)</Label><Input value={form.config.data_path} onChange={e => setCfg("data_path", e.target.value)} placeholder="data.items" className="mt-1" /></div>
                </>
              ) : (
                <>
                  <div className="grid grid-cols-3 gap-2">
                    <div className="col-span-2"><Label>Host *</Label><Input value={form.config.host} onChange={e => setCfg("host", e.target.value)} required className="mt-1" /></div>
                    <div><Label>Port</Label><Input type="number" value={form.config.port} onChange={e => setCfg("port", e.target.value)} placeholder={form.kind === "postgresql" ? "5432" : "3306"} className="mt-1" /></div>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div><Label>User *</Label><Input value={form.config.user} onChange={e => setCfg("user", e.target.value)} required className="mt-1" /></div>
                    <div><Label>Password *</Label><Input type="password" value={form.config.password} onChange={e => setCfg("password", e.target.value)} required className="mt-1" /></div>
                  </div>
                  <div><Label>Database *</Label><Input value={form.config.database} onChange={e => setCfg("database", e.target.value)} required className="mt-1" /></div>
                  <div><Label>Table</Label><Input value={form.config.table} onChange={e => setCfg("table", e.target.value)} placeholder="products" className="mt-1" /></div>
                  <div><Label>Custom SQL (optional, overrides table)</Label><Textarea value={form.config.query} onChange={e => setCfg("query", e.target.value)} placeholder="SELECT sku, name, barcode FROM products WHERE active=1" className="mt-1 font-mono text-xs" rows={3} /></div>
                </>
              )}

              <div>
                <Label>Field mapping (AIW field → your source column)</Label>
                <div className="mt-2 space-y-2 border border-border rounded p-3">
                  {stdFields.map(f => (
                    <div key={f} className="grid grid-cols-2 gap-2 items-center">
                      <div className="text-xs font-mono uppercase text-muted-foreground">{f}</div>
                      <Input value={form.config.field_map?.[f] || ""} onChange={e => setMap(f, e.target.value)} placeholder="source column" className="h-8 text-xs font-mono" />
                    </div>
                  ))}
                </div>
              </div>
              <Button type="submit" className="w-full bg-primary text-primary-foreground" data-testid="conn-save-btn">Save connector</Button>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      <div className="space-y-3">
        {items.map(c => (
          <div key={c.id} className="tactical-card p-5" data-testid={`connector-${c.name}`}>
            <div className="flex items-start justify-between flex-wrap gap-3">
              <div className="flex items-start gap-3 min-w-0 flex-1">
                <div className="w-11 h-11 rounded-lg bg-primary/15 border border-primary/30 flex items-center justify-center"><Plug className="w-5 h-5 text-primary" /></div>
                <div className="min-w-0">
                  <div className="font-heading font-bold uppercase text-lg">{c.name}</div>
                  <div className="flex gap-2 flex-wrap mt-1">
                    <Badge variant="outline" className="font-mono text-[10px] uppercase">{KIND_LABELS[c.kind]}</Badge>
                    {c.last_sync ? <Badge className="bg-emerald-500/20 text-emerald-400 border-emerald-500/30">Synced {new Date(c.last_sync).toLocaleString()}</Badge> : <Badge variant="secondary">Never synced</Badge>}
                  </div>
                  <div className="text-xs font-mono text-muted-foreground mt-1 truncate">
                    {c.kind === "rest" ? c.config?.url : `${c.config?.host}/${c.config?.database}`}
                  </div>
                </div>
              </div>
              <div className="flex gap-2">
                <Button size="sm" variant="outline" onClick={() => test(c.id)} disabled={busy[c.id]} data-testid={`test-${c.name}`}><PlayCircle className="w-3.5 h-3.5 mr-1.5" /> Test</Button>
                <Button size="sm" className="bg-primary text-primary-foreground" onClick={() => sync(c.id)} disabled={busy[c.id]} data-testid={`sync-${c.name}`}><RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${busy[c.id] === "sync" ? "animate-spin" : ""}`} /> Sync</Button>
                <Button size="sm" variant="ghost" onClick={() => del(c.id)} data-testid={`del-${c.name}`}><Trash2 className="w-4 h-4 text-destructive" /></Button>
              </div>
            </div>
            {testRes[c.id] && (
              <div className="mt-4 p-3 rounded bg-secondary/60 border border-border text-xs font-mono">
                {testRes[c.id].ok ? (
                  <><div className="text-emerald-400 flex items-center gap-1"><CheckCircle2 className="w-3.5 h-3.5" /> Fetched {testRes[c.id].count} rows</div>
                  <pre className="mt-2 overflow-x-auto text-muted-foreground">{JSON.stringify(testRes[c.id].sample, null, 2)}</pre></>
                ) : (
                  <div className="text-destructive flex items-center gap-1"><XCircle className="w-3.5 h-3.5" /> {testRes[c.id].error}</div>
                )}
              </div>
            )}
          </div>
        ))}
        {items.length === 0 && <div className="tactical-card p-10 text-center text-muted-foreground">No connectors yet. Add one to sync your existing ERP/database.</div>}
      </div>
    </div>
  );
}
