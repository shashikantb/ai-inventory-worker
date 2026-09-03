import React, { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Plus, User as UserIcon, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";

export default function Users() {
  const { user } = useAuth();
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ email: "", password: "", name: "", role: "worker" });

  const load = () => api.get("/users").then(r => setItems(r.data));
  useEffect(() => { load(); }, []);

  const create = async (e) => {
    e.preventDefault();
    try { await api.post("/users", form); toast.success("User created"); setOpen(false); setForm({ email: "", password: "", name: "", role: "worker" }); load(); }
    catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };
  const del = async (id) => {
    if (!window.confirm("Deactivate this user?")) return;
    await api.delete(`/users/${id}`); toast.success("Deactivated"); load();
  };

  return (
    <div className="space-y-6" data-testid="users-page">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="text-xs font-mono uppercase tracking-widest text-primary mb-1">Team</div>
          <h1 className="font-heading font-extrabold uppercase text-3xl sm:text-4xl tracking-tight">Users & Roles</h1>
        </div>
        {user?.role === "org_admin" && (
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild><Button className="bg-primary text-primary-foreground" data-testid="add-user-btn"><Plus className="w-4 h-4 mr-2" /> Invite user</Button></DialogTrigger>
            <DialogContent className="bg-card">
              <DialogHeader><DialogTitle className="font-heading uppercase">New user</DialogTitle></DialogHeader>
              <form onSubmit={create} className="space-y-3">
                <div><Label>Name</Label><Input value={form.name} onChange={e => setForm({...form, name: e.target.value})} required data-testid="user-name-input" className="mt-1" /></div>
                <div><Label>Email</Label><Input type="email" value={form.email} onChange={e => setForm({...form, email: e.target.value})} required data-testid="user-email-input" className="mt-1" /></div>
                <div><Label>Temporary password</Label><Input type="password" minLength={6} value={form.password} onChange={e => setForm({...form, password: e.target.value})} required data-testid="user-password-input" className="mt-1" /></div>
                <div><Label>Role</Label>
                  <Select value={form.role} onValueChange={v => setForm({...form, role: v})}>
                    <SelectTrigger className="mt-1" data-testid="user-role-select"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="worker">Worker</SelectItem>
                      <SelectItem value="manager">Manager</SelectItem>
                      <SelectItem value="org_admin">Org Admin</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <Button type="submit" className="w-full bg-primary text-primary-foreground" data-testid="user-save-btn">Create user</Button>
              </form>
            </DialogContent>
          </Dialog>
        )}
      </div>

      <div className="tactical-card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-secondary/60 border-b border-border">
            <tr>{["User", "Email", "Role", "Status", ""].map(h => <th key={h} className="text-left px-4 py-3 font-mono uppercase text-xs tracking-widest text-muted-foreground">{h}</th>)}</tr>
          </thead>
          <tbody>
            {items.map(u => (
              <tr key={u.id} className="border-b border-border hover:bg-secondary/30" data-testid={`user-row-${u.email}`}>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <div className="w-8 h-8 rounded-full bg-secondary flex items-center justify-center"><UserIcon className="w-4 h-4 text-muted-foreground" /></div>
                    <span className="font-semibold">{u.name}</span>
                  </div>
                </td>
                <td className="px-4 py-3 text-muted-foreground">{u.email}</td>
                <td className="px-4 py-3"><Badge variant="outline" className="uppercase font-mono text-[10px]">{u.role.replace("_", " ")}</Badge></td>
                <td className="px-4 py-3">{u.active !== false ? <Badge className="bg-emerald-500/20 text-emerald-400 border-emerald-500/30">Active</Badge> : <Badge variant="destructive">Inactive</Badge>}</td>
                <td className="px-4 py-3 text-right">
                  {user?.role === "org_admin" && u.id !== user.id && u.active !== false && (
                    <Button size="sm" variant="ghost" onClick={() => del(u.id)} data-testid={`delete-user-${u.email}`}><Trash2 className="w-4 h-4 text-destructive" /></Button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
