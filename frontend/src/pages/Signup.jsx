import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ScanLine, Loader2 } from "lucide-react";
import { toast } from "sonner";

export default function Signup() {
  const { signup } = useAuth();
  const nav = useNavigate();
  const [form, setForm] = useState({ email: "", password: "", name: "", org_name: "" });
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await signup(form);
      toast.success("Account created");
      nav("/app/dashboard");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Signup failed");
    } finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-6 bg-background">
      <div className="w-full max-w-md">
        <div className="flex items-center gap-3 mb-8">
          <div className="w-11 h-11 rounded-lg bg-primary flex items-center justify-center">
            <ScanLine className="w-6 h-6 text-primary-foreground" strokeWidth={2.5} />
          </div>
          <div>
            <div className="font-heading font-extrabold text-xl uppercase leading-none">AI Inventory Worker</div>
            <div className="text-[10px] font-mono uppercase text-muted-foreground tracking-widest mt-1">Ask · Scan · Find · Act</div>
          </div>
        </div>
        <div className="tactical-card p-6 sm:p-8">
          <h1 className="font-heading font-bold text-2xl uppercase mb-1">Create your workspace</h1>
          <p className="text-sm text-muted-foreground mb-6">You become the org admin</p>
          <form onSubmit={submit} className="space-y-4">
            <div>
              <Label>Your name</Label>
              <Input value={form.name} onChange={e => setForm({...form, name: e.target.value})} required data-testid="signup-name-input" className="mt-1.5" />
            </div>
            <div>
              <Label>Organization name</Label>
              <Input value={form.org_name} onChange={e => setForm({...form, org_name: e.target.value})} required data-testid="signup-org-input" className="mt-1.5" />
            </div>
            <div>
              <Label>Email</Label>
              <Input type="email" value={form.email} onChange={e => setForm({...form, email: e.target.value})} required data-testid="signup-email-input" className="mt-1.5" />
            </div>
            <div>
              <Label>Password</Label>
              <Input type="password" value={form.password} onChange={e => setForm({...form, password: e.target.value})} required minLength={6} data-testid="signup-password-input" className="mt-1.5" />
            </div>
            <Button type="submit" disabled={loading} className="w-full bg-primary text-primary-foreground hover:bg-primary/90 h-11" data-testid="signup-submit-btn">
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Create workspace"}
            </Button>
          </form>
          <div className="mt-6 text-sm text-muted-foreground text-center">
            Have an account? <Link to="/login" className="text-primary font-semibold hover:underline" data-testid="signup-goto-login">Log in</Link>
          </div>
        </div>
      </div>
    </div>
  );
}
