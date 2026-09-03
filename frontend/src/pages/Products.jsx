import React, { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Link } from "react-router-dom";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { Search, Plus, Package } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";

export default function Products() {
  const { user } = useAuth();
  const [items, setItems] = useState([]);
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ sku: "", name: "", barcode: "", brand: "", category: "", model_number: "" });

  const load = async (query = q) => {
    const { data } = await api.get("/products", { params: { q: query || undefined } });
    setItems(data);
  };
  useEffect(() => { load(""); }, []);

  const create = async (e) => {
    e.preventDefault();
    try {
      await api.post("/products", form);
      toast.success("Product created");
      setOpen(false);
      setForm({ sku: "", name: "", barcode: "", brand: "", category: "", model_number: "" });
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed");
    }
  };

  const canCreate = ["org_admin", "manager"].includes(user?.role);

  return (
    <div className="space-y-6" data-testid="products-page">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="text-xs font-mono uppercase tracking-widest text-primary mb-1">Catalog</div>
          <h1 className="font-heading font-extrabold uppercase text-3xl sm:text-4xl tracking-tight">Products</h1>
        </div>
        {canCreate && (
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild><Button className="bg-primary text-primary-foreground" data-testid="add-product-btn"><Plus className="w-4 h-4 mr-2" /> Add product</Button></DialogTrigger>
            <DialogContent className="bg-card">
              <DialogHeader><DialogTitle className="font-heading uppercase">New product</DialogTitle></DialogHeader>
              <form onSubmit={create} className="space-y-3">
                {["sku", "name", "barcode", "brand", "category", "model_number"].map(f => (
                  <div key={f}>
                    <Label className="capitalize">{f.replace("_", " ")}{["sku","name"].includes(f) && " *"}</Label>
                    <Input value={form[f]} onChange={e => setForm({...form, [f]: e.target.value})} required={["sku","name"].includes(f)} data-testid={`product-${f}-input`} className="mt-1" />
                  </div>
                ))}
                <Button type="submit" className="w-full bg-primary text-primary-foreground" data-testid="product-save-btn">Save</Button>
              </form>
            </DialogContent>
          </Dialog>
        )}
      </div>

      <div className="flex gap-2">
        <div className="relative flex-1 max-w-lg">
          <Search className="absolute left-3 top-3 w-4 h-4 text-muted-foreground" />
          <Input value={q} onChange={e => setQ(e.target.value)} onKeyDown={e => e.key === "Enter" && load()} placeholder="Search by name, SKU, barcode, brand…" className="pl-10 h-11" data-testid="product-search-bar" />
        </div>
        <Button onClick={() => load()} variant="outline" className="h-11" data-testid="search-btn">Search</Button>
      </div>

      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {items.map(p => (
          <Link key={p.id} to={`/app/products/${p.id}`} className="tactical-card p-4 hover:border-primary/50 transition-colors" data-testid={`product-card-${p.sku}`}>
            <div className="w-full aspect-video rounded bg-secondary flex items-center justify-center mb-3">
              <Package className="w-8 h-8 text-muted-foreground" />
            </div>
            <div className="font-heading font-bold uppercase text-lg leading-tight">{p.name}</div>
            <div className="text-xs font-mono text-muted-foreground mt-1">SKU {p.sku}</div>
            <div className="flex gap-1.5 flex-wrap mt-3">
              {p.brand && <Badge variant="outline" className="text-[10px]">{p.brand}</Badge>}
              {p.category && <Badge variant="secondary" className="text-[10px]">{p.category}</Badge>}
            </div>
          </Link>
        ))}
        {items.length === 0 && <div className="col-span-full text-center py-16 text-muted-foreground">No products yet</div>}
      </div>
    </div>
  );
}
