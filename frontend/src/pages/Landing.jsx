import React from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { ScanLine, Sparkles, Package, Zap, Mic, Camera, ArrowRight, CheckCircle2 } from "lucide-react";

export default function Landing() {
  return (
    <div className="min-h-screen bg-background text-foreground overflow-hidden">
      <nav className="border-b border-border/60 backdrop-blur-md bg-background/70 sticky top-0 z-40">
        <div className="max-w-7xl mx-auto flex items-center justify-between px-6 h-16">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-primary flex items-center justify-center">
              <ScanLine className="w-5 h-5 text-primary-foreground" strokeWidth={2.5} />
            </div>
            <div className="font-heading font-extrabold text-lg uppercase tracking-wide">AI Inventory Worker</div>
          </div>
          <div className="flex items-center gap-2">
            <Link to="/login"><Button variant="ghost" data-testid="landing-login-btn">Log in</Button></Link>
            <Link to="/signup"><Button data-testid="landing-signup-btn" className="bg-primary text-primary-foreground hover:bg-primary/90">Get started</Button></Link>
          </div>
        </div>
      </nav>

      <section className="relative">
        <div className="grid-overlay absolute inset-0" />
        <div className="max-w-7xl mx-auto px-6 pt-16 pb-24 lg:pt-28 lg:pb-32 relative">
          <div className="grid lg:grid-cols-12 gap-12 items-center">
            <div className="lg:col-span-7">
              <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-primary/10 border border-primary/30 mb-6">
                <Sparkles className="w-3.5 h-3.5 text-primary" />
                <span className="text-xs font-mono uppercase tracking-widest text-primary">Powered by Claude &amp; Gemini</span>
              </div>
              <h1 className="font-heading font-black uppercase tracking-tight text-5xl sm:text-6xl lg:text-7xl leading-[0.95]">
                Ask. Scan.
                <br />
                <span className="text-primary">Find. Act.</span>
              </h1>
              <p className="mt-6 text-lg text-muted-foreground max-w-xl leading-relaxed">
                An AI frontline worker that sits on top of your inventory. Talk to it, scan a barcode, snap a photo — get instant answers, exact locations, and safe stock actions.
              </p>
              <div className="mt-8 flex flex-wrap gap-3">
                <Link to="/signup">
                  <Button size="lg" className="bg-primary text-primary-foreground hover:bg-primary/90 h-12 px-6 text-base" data-testid="hero-start-btn">
                    Start free — no card <ArrowRight className="w-4 h-4 ml-2" />
                  </Button>
                </Link>
                <Link to="/login">
                  <Button size="lg" variant="outline" className="h-12 px-6 text-base" data-testid="hero-login-btn">
                    Log in
                  </Button>
                </Link>
              </div>
              <div className="mt-8 flex flex-wrap gap-x-6 gap-y-2 text-sm text-muted-foreground">
                {["Multi-tenant SaaS", "Barcode + Image scan", "Voice queries", "Full audit log"].map(f => (
                  <div key={f} className="flex items-center gap-2"><CheckCircle2 className="w-4 h-4 text-primary" /> {f}</div>
                ))}
              </div>
            </div>
            <div className="lg:col-span-5">
              <div className="relative">
                <div className="tactical-card p-6 glow-primary">
                  <div className="flex items-center gap-2 mb-4">
                    <div className="w-2 h-2 rounded-full bg-red-500" />
                    <div className="w-2 h-2 rounded-full bg-amber-500" />
                    <div className="w-2 h-2 rounded-full bg-emerald-500" />
                    <span className="ml-auto text-xs font-mono uppercase text-muted-foreground">Live · Session</span>
                  </div>
                  <div className="space-y-3 font-mono text-sm">
                    <div className="p-3 rounded bg-secondary border border-border">
                      <span className="text-muted-foreground">You:</span> Where is Samsung Monitor 24M?
                    </div>
                    <div className="p-3 rounded bg-primary/10 border border-primary/30">
                      <span className="text-primary font-bold">AIW:</span> Found <span className="text-foreground">SM-XYZ-2026</span> — 24 units available.
                      <div className="mt-2 text-foreground text-xs">
                        📍 Pune Warehouse → Zone B → Aisle 4 → Rack 12 → Shelf 3
                      </div>
                    </div>
                    <div className="p-3 rounded bg-secondary border border-border">
                      <span className="text-muted-foreground">You:</span> Show low stock in Pune
                    </div>
                    <div className="p-3 rounded bg-primary/10 border border-primary/30">
                      <span className="text-primary font-bold">AIW:</span> 3 items below reorder level. Want a stock request?
                    </div>
                  </div>
                </div>
                <div className="absolute -bottom-6 -right-6 tactical-card p-4 hidden sm:block">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-accent/20 flex items-center justify-center">
                      <ScanLine className="w-5 h-5 text-accent" />
                    </div>
                    <div>
                      <div className="text-xs text-muted-foreground font-mono uppercase">Barcode</div>
                      <div className="font-mono font-bold text-sm">8901234567890</div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="border-t border-border/60 py-20">
        <div className="max-w-7xl mx-auto px-6">
          <div className="max-w-2xl mb-12">
            <div className="text-xs font-mono uppercase tracking-widest text-primary mb-3">Modules</div>
            <h2 className="font-heading font-bold text-3xl sm:text-4xl lg:text-5xl uppercase tracking-tight">Everything the frontline needs</h2>
          </div>
          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-4">
            {[
              { icon: Sparkles, title: "AI Chat", desc: "Natural language queries with real tool-calling into your catalog." },
              { icon: ScanLine, title: "Barcode Scan", desc: "Camera-based EAN/UPC/QR scan, instant product + location." },
              { icon: Camera, title: "Image Recognition", desc: "Snap a photo — AI identifies brand, model, and matches SKU." },
              { icon: Package, title: "Hierarchy Locations", desc: "Warehouse → Zone → Aisle → Rack → Shelf → Bin." },
              { icon: Mic, title: "Voice Ready", desc: "Multilingual voice queries — hands-free warehouse ops." },
              { icon: Zap, title: "Actions with Approval", desc: "Adjust, transfer, request — every change fully audited." },
            ].map((f) => (
              <div key={f.title} className="tactical-card p-5">
                <div className="w-10 h-10 rounded-lg bg-primary/15 border border-primary/30 flex items-center justify-center mb-4">
                  <f.icon className="w-5 h-5 text-primary" />
                </div>
                <div className="font-heading font-bold uppercase text-lg mb-1">{f.title}</div>
                <div className="text-sm text-muted-foreground">{f.desc}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <footer className="border-t border-border/60 py-8">
        <div className="max-w-7xl mx-auto px-6 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="font-mono text-xs uppercase tracking-widest text-muted-foreground">© 2026 AI Inventory Worker</div>
          <Link to="/signup">
            <Button size="sm" className="bg-primary text-primary-foreground" data-testid="footer-cta-btn">Start free <ArrowRight className="w-3.5 h-3.5 ml-1.5" /></Button>
          </Link>
        </div>
      </footer>
    </div>
  );
}
