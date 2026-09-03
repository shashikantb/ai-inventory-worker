import React, { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { ClipboardCheck, Check, X, User } from "lucide-react";
import { toast } from "sonner";

export default function Approvals() {
  const [items, setItems] = useState([]);
  const [tab, setTab] = useState("pending");
  const [decision, setDecision] = useState(null); // {id, action}
  const [note, setNote] = useState("");

  const load = (s = tab) => api.get(`/approvals?status_filter=${s}`).then(r => setItems(r.data));
  useEffect(() => { load(tab); }, [tab]);

  const submit = async () => {
    if (!decision) return;
    try {
      await api.post(`/approvals/${decision.id}/${decision.action}`, { reason: note });
      toast.success(decision.action === "approve" ? "Approved & applied" : "Rejected");
      setDecision(null); setNote(""); load();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };

  return (
    <div className="space-y-6" data-testid="approvals-page">
      <div>
        <div className="text-xs font-mono uppercase tracking-widest text-primary mb-1">Governance</div>
        <h1 className="font-heading font-extrabold uppercase text-3xl sm:text-4xl tracking-tight">Approvals Queue</h1>
        <p className="text-sm text-muted-foreground mt-2">Stock adjustments larger than 50 units by workers need a manager approval before they commit.</p>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="pending" data-testid="tab-pending"><ClipboardCheck className="w-3.5 h-3.5 mr-1.5" /> Pending</TabsTrigger>
          <TabsTrigger value="approved" data-testid="tab-approved">Approved</TabsTrigger>
          <TabsTrigger value="rejected" data-testid="tab-rejected">Rejected</TabsTrigger>
        </TabsList>

        <TabsContent value={tab} className="mt-4 space-y-2">
          {items.length === 0 && <div className="tactical-card p-10 text-center text-muted-foreground">No {tab} requests</div>}
          {items.map(a => (
            <div key={a.id} className="tactical-card p-5" data-testid={`approval-${a.id}`}>
              <div className="flex items-start justify-between flex-wrap gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <Badge className="bg-amber-500/20 text-amber-400 border-amber-500/30 uppercase font-mono text-[10px]">{a.type.replace("_", " ")}</Badge>
                    <div className="text-xs font-mono text-muted-foreground">{new Date(a.created_at).toLocaleString()}</div>
                  </div>
                  <div className="font-heading font-bold uppercase text-lg mt-2">{a.product_name} <span className="text-muted-foreground text-sm font-mono">· {a.product_sku}</span></div>
                  <div className="text-sm text-muted-foreground mt-1">{a.warehouse_name}</div>
                  <div className="mt-3 flex gap-6 flex-wrap items-center">
                    <div>
                      <div className="text-[10px] font-mono uppercase text-muted-foreground">Current</div>
                      <div className="kpi-value text-2xl">{a.payload?.current}</div>
                    </div>
                    <div className="text-2xl text-muted-foreground">→</div>
                    <div>
                      <div className="text-[10px] font-mono uppercase text-muted-foreground">Requested</div>
                      <div className="kpi-value text-2xl text-primary">{a.payload?.new_quantity}</div>
                    </div>
                    <div>
                      <div className="text-[10px] font-mono uppercase text-muted-foreground">Delta</div>
                      <div className="kpi-value text-2xl text-amber-400">{a.payload?.delta}</div>
                    </div>
                  </div>
                  <div className="mt-3 text-sm">
                    <div className="flex items-center gap-1.5 text-muted-foreground text-xs font-mono uppercase mb-1"><User className="w-3 h-3" /> {a.requested_by_name}</div>
                    <div className="italic text-muted-foreground">"{a.reason}"</div>
                    {a.resolver_note && <div className="mt-2 text-xs">Resolver note: <span className="italic">"{a.resolver_note}"</span> — {a.resolved_by}</div>}
                  </div>
                </div>
                {tab === "pending" && (
                  <div className="flex gap-2">
                    <Button size="sm" variant="outline" onClick={() => setDecision({ id: a.id, action: "reject" })} data-testid={`reject-${a.id}`}><X className="w-4 h-4 mr-1.5" /> Reject</Button>
                    <Button size="sm" className="bg-emerald-500 text-white hover:bg-emerald-600" onClick={() => setDecision({ id: a.id, action: "approve" })} data-testid={`approve-${a.id}`}><Check className="w-4 h-4 mr-1.5" /> Approve</Button>
                  </div>
                )}
              </div>
            </div>
          ))}
        </TabsContent>
      </Tabs>

      <Dialog open={!!decision} onOpenChange={(o) => !o && setDecision(null)}>
        <DialogContent className="bg-card">
          <DialogHeader><DialogTitle className="font-heading uppercase">{decision?.action === "approve" ? "Approve request" : "Reject request"}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div><Label>Note (optional)</Label><Textarea value={note} onChange={e => setNote(e.target.value)} className="mt-1" data-testid="approval-note-input" /></div>
            <Button onClick={submit} className={`w-full ${decision?.action === "approve" ? "bg-emerald-500 text-white hover:bg-emerald-600" : "bg-destructive text-destructive-foreground hover:bg-destructive/90"}`} data-testid="approval-confirm-btn">
              Confirm {decision?.action}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
