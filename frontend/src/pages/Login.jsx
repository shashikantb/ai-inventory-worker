import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ScanLine, Loader2 } from "lucide-react";
import { toast } from "sonner";

export default function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("borgavakarshashikant@gmail.com");
  const [password, setPassword] = useState("AdminPass@2026");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await login(email, password);
      toast.success("Welcome back");
      nav("/app/dashboard");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Login failed");
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
          <h1 className="font-heading font-bold text-2xl uppercase mb-1">Log in</h1>
          <p className="text-sm text-muted-foreground mb-6">Enter your credentials to continue</p>
          <form onSubmit={submit} className="space-y-4">
            <div>
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" value={email} onChange={e => setEmail(e.target.value)} required data-testid="login-email-input" className="mt-1.5" />
            </div>
            <div>
              <Label htmlFor="password">Password</Label>
              <Input id="password" type="password" value={password} onChange={e => setPassword(e.target.value)} required data-testid="login-password-input" className="mt-1.5" />
            </div>
            <Button type="submit" disabled={loading} className="w-full bg-primary text-primary-foreground hover:bg-primary/90 h-11" data-testid="login-submit-btn">
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Log in"}
            </Button>
          </form>
          <div className="mt-6 text-sm text-muted-foreground text-center">
            New here? <Link to="/signup" className="text-primary font-semibold hover:underline" data-testid="login-goto-signup">Create an account</Link>
          </div>
        </div>
      </div>
    </div>
  );
}
