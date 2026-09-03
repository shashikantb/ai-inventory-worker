import React, { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Save, Plus, Trash2, Shield, Sticker } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";

export default function Settings() {
  const { user } = useAuth();
  const [tpl, setTpl] = useState({ org_line: "", logo_url: "", show_brand: true, show_sku: true, show_price: false, show_expiry: false, footer: "" });
  const [rules, setRules] = useState([]);
  const [defaultThreshold, setDefaultThreshold] = useState(50);
  const [warehouses, setWarehouses] = useState([]);
  const [newRule, setNewRule] = useState({ warehouse_id: "any", category: "", threshold: 100 });

  const load = async () => {
    const [t, r, w] = await Promise.all([api.get("/label-template"), api.get("/approval-rules"), api.get("/warehouses")]);
    setTpl(t.data);
    setRules(r.data.rules || []);
    setDefaultThreshold(r.data.default_threshold ?? 50);
    setWarehouses(w.data);
  };
  useEffect(() => { load(); }, []);

  const saveTemplate = async () => {
    try { await api.put("/label-template", tpl); toast.success("Label template saved"); }
    catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  const saveDefault = async () => {
    try { await api.put("/org-settings", { default_threshold: parseInt(defaultThreshold, 10) }); toast.success("Default threshold updated"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  const addRule = async () => {
    try {
      const payload = {
        warehouse_id: newRule.warehouse_id === "any" ? null : newRule.warehouse_id,
        category: newRule.category.trim() || null,
        threshold: parseInt(newRule.threshold, 10),
      };
      await api.post("/approval-rules", payload);
      toast.success("Rule added");
      setNewRule({ warehouse_id: "any", category: "", threshold: 100 });
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  const delRule = async (id) => {
    if (!window.confirm("Delete this rule?")) return;
    await api.delete(`/approval-rules/${id}`); toast.success("Deleted"); load();
  };

  const canEdit = user?.role === "org_admin";

  return (
    <div className="max-w-4xl mx-auto space-y-6" data-testid="settings-page">
      <div>
        <div className="text-xs font-mono uppercase tracking-widest text-primary mb-1">Configuration</div>
        <h1 className="font-heading font-extrabold uppercase text-3xl sm:text-4xl tracking-tight">Settings</h1>
      </div>

      <Tabs defaultValue="labels">
        <TabsList>
          <TabsTrigger value="labels" data-testid="tab-labels"><Sticker className="w-3.5 h-3.5 mr-1.5" /> Label templates</TabsTrigger>
          <TabsTrigger value="approvals" data-testid="tab-approvals"><Shield className="w-3.5 h-3.5 mr-1.5" /> Approval rules</TabsTrigger>
        </TabsList>

        <TabsContent value="labels" className="mt-6">
          <div className="tactical-card p-6 space-y-4">
            <div>
              <Label>Header line (defaults to org name)</Label>
              <Input value={tpl.org_line} onChange={e => setTpl({ ...tpl, org_line: e.target.value })} placeholder={user?.org_name} className="mt-1" data-testid="tpl-orgline-input" />
            </div>
            <div>
              <Label>Logo URL (optional)</Label>
              <Input value={tpl.logo_url} onChange={e => setTpl({ ...tpl, logo_url: e.target.value })} placeholder="https://..." className="mt-1" />
            </div>
            <div>
              <Label>Footer / disclaimer</Label>
              <Input value={tpl.footer} onChange={e => setTpl({ ...tpl, footer: e.target.value })} placeholder="Handle with care · Made in India" className="mt-1" data-testid="tpl-footer-input" />
            </div>
            <div className="grid sm:grid-cols-2 gap-3 pt-2">
              {[
                ["show_sku", "Show SKU"], ["show_brand", "Show brand"],
                ["show_price", "Show price"], ["show_expiry", "Show expiry date"],
              ].map(([k, lbl]) => (
                <div key={k} className="flex items-center justify-between p-3 rounded border border-border">
                  <div className="text-sm font-medium">{lbl}</div>
                  <Switch checked={!!tpl[k]} onCheckedChange={v => setTpl({ ...tpl, [k]: v })} data-testid={`tpl-${k}`} />
                </div>
              ))}
            </div>
            <div className="tactical-card p-4 bg-secondary/40">
              <div className="text-xs font-mono uppercase text-muted-foreground mb-2">Preview (schematic)</div>
              <div className="flex items-start justify-between border border-border/60 rounded p-3 bg-background/40">
                <div className="text-xs space-y-0.5">
                  <div className="font-bold uppercase">{tpl.org_line || user?.org_name}</div>
                  <div className="text-sm font-bold">Sample Product Name</div>
                  {tpl.show_sku && <div className="font-mono text-muted-foreground">SKU SAMPLE-01</div>}
                  {tpl.show_price && <div className="font-bold">₹ 499.00</div>}
                  {tpl.show_expiry && <div className="text-muted-foreground">EXP 2027-01-31</div>}
                  {tpl.show_brand && <div className="text-muted-foreground italic mt-2">Sample Brand</div>}
                  {tpl.footer && <div className="text-[10px] italic text-muted-foreground mt-2">{tpl.footer}</div>}
                </div>
                <div className="w-24 h-16 border border-border rounded flex items-center justify-center font-mono text-[10px] text-muted-foreground">|||||||||||</div>
              </div>
            </div>
            <Button onClick={saveTemplate} disabled={!canEdit && user?.role !== "manager"} className="bg-primary text-primary-foreground" data-testid="save-template-btn"><Save className="w-4 h-4 mr-2" /> Save template</Button>
            <div className="text-xs text-muted-foreground">Tip: pass <span className="font-mono">?price=499&amp;expiry=2027-01-31</span> when opening the label PDF to include those fields.</div>
          </div>
        </TabsContent>

        <TabsContent value="approvals" className="mt-6 space-y-4">
          <div className="tactical-card p-6">
            <div className="text-xs font-mono uppercase text-muted-foreground mb-2">Default org-wide threshold</div>
            <div className="flex items-center gap-2">
              <Input type="number" value={defaultThreshold} onChange={e => setDefaultThreshold(e.target.value)} className="max-w-[160px]" data-testid="default-threshold-input" />
              <span className="text-sm text-muted-foreground">units — workers exceeding this need approval</span>
              <Button onClick={saveDefault} disabled={!canEdit} className="bg-primary text-primary-foreground ml-auto" data-testid="save-default-threshold-btn"><Save className="w-4 h-4 mr-2" /> Save</Button>
            </div>
          </div>

          <div className="tactical-card p-6">
            <div className="font-heading font-bold uppercase mb-3">Per-warehouse / category rules</div>
            <p className="text-xs text-muted-foreground mb-4">Rules with a more specific match (warehouse + category) win over less specific ones.</p>
            <div className="space-y-2 mb-4">
              {rules.length === 0 && <div className="text-sm text-muted-foreground italic">No custom rules yet — using default of {defaultThreshold} units.</div>}
              {rules.map(r => {
                const wh = warehouses.find(w => w.id === r.warehouse_id);
                return (
                  <div key={r.id} className="flex items-center justify-between p-3 rounded border border-border bg-secondary/40" data-testid={`rule-${r.id}`}>
                    <div className="flex gap-2 flex-wrap items-center">
                      <Badge variant="outline" className="uppercase text-[10px] font-mono">Warehouse</Badge>
                      <span className="font-semibold text-sm">{wh?.name || "Any"}</span>
                      <Badge variant="outline" className="uppercase text-[10px] font-mono">Category</Badge>
                      <span className="font-semibold text-sm">{r.category || "Any"}</span>
                      <Badge className="bg-primary/15 text-primary border-primary/30 font-mono">≤ {r.threshold} units auto-apply</Badge>
                    </div>
                    {canEdit && <Button size="sm" variant="ghost" onClick={() => delRule(r.id)}><Trash2 className="w-4 h-4 text-destructive" /></Button>}
                  </div>
                );
              })}
            </div>
            {canEdit && (
              <div className="grid grid-cols-1 sm:grid-cols-4 gap-2 items-end">
                <div><Label className="text-xs">Warehouse</Label>
                  <Select value={newRule.warehouse_id} onValueChange={v => setNewRule({ ...newRule, warehouse_id: v })}>
                    <SelectTrigger className="mt-1" data-testid="rule-wh-select"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="any">Any</SelectItem>
                      {warehouses.map(w => <SelectItem key={w.id} value={w.id}>{w.name}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div><Label className="text-xs">Category (optional)</Label>
                  <Input value={newRule.category} onChange={e => setNewRule({ ...newRule, category: e.target.value })} placeholder="Electronics" className="mt-1" data-testid="rule-cat-input" />
                </div>
                <div><Label className="text-xs">Threshold (units)</Label>
                  <Input type="number" value={newRule.threshold} onChange={e => setNewRule({ ...newRule, threshold: e.target.value })} className="mt-1" data-testid="rule-threshold-input" />
                </div>
                <Button onClick={addRule} className="bg-primary text-primary-foreground" data-testid="add-rule-btn"><Plus className="w-4 h-4 mr-2" /> Add rule</Button>
              </div>
            )}
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
