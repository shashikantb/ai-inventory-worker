import React, { useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Upload, FileSpreadsheet, CheckCircle2, AlertCircle } from "lucide-react";
import { toast } from "sonner";

export default function ImportPage() {
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  const upload = async () => {
    if (!file) return;
    setLoading(true);
    setResult(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post("/import/products", fd, { headers: { "Content-Type": "multipart/form-data" } });
      setResult(data);
      toast.success(`Imported ${data.imported} products`);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Import failed");
    } finally { setLoading(false); }
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6" data-testid="import-page">
      <div>
        <div className="text-xs font-mono uppercase tracking-widest text-primary mb-1">Bulk Import</div>
        <h1 className="font-heading font-extrabold uppercase text-3xl sm:text-4xl tracking-tight">CSV / Excel Import</h1>
        <p className="text-muted-foreground mt-2 text-sm">Upload your existing product catalog. Columns detected: <span className="font-mono">sku, name, barcode, brand, category, model_number, description</span></p>
      </div>

      <div className="tactical-card p-6">
        <label className="block cursor-pointer">
          <input type="file" accept=".csv,.xlsx,.xls" className="hidden" onChange={e => setFile(e.target.files?.[0])} data-testid="import-file-input" />
          <div className="border-2 border-dashed border-border rounded-lg p-10 text-center hover:border-primary/50 transition-colors">
            <FileSpreadsheet className="w-12 h-12 mx-auto text-muted-foreground mb-3" />
            <div className="font-semibold">{file ? file.name : "Choose CSV or Excel file"}</div>
            <div className="text-xs text-muted-foreground mt-1">Click to browse</div>
          </div>
        </label>
        <Button onClick={upload} disabled={!file || loading} className="w-full mt-4 bg-primary text-primary-foreground h-11" data-testid="import-upload-btn">
          {loading ? "Uploading…" : <><Upload className="w-4 h-4 mr-2" /> Import products</>}
        </Button>
      </div>

      {result && (
        <div className="tactical-card p-6" data-testid="import-result">
          <div className="flex items-center gap-2 mb-4">
            <CheckCircle2 className="w-5 h-5 text-emerald-400" />
            <div className="font-heading font-bold uppercase text-lg">Import complete</div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="p-3 rounded bg-secondary border border-border">
              <div className="text-xs font-mono uppercase text-muted-foreground">Imported</div>
              <div className="kpi-value text-3xl text-emerald-400">{result.imported}</div>
            </div>
            <div className="p-3 rounded bg-secondary border border-border">
              <div className="text-xs font-mono uppercase text-muted-foreground">Skipped</div>
              <div className="kpi-value text-3xl text-muted-foreground">{result.skipped}</div>
            </div>
          </div>
          {result.errors?.length > 0 && (
            <div className="mt-4">
              <div className="flex items-center gap-2 text-sm text-destructive mb-2"><AlertCircle className="w-4 h-4" /> Errors</div>
              <ul className="text-xs space-y-1 font-mono">{result.errors.map((e, i) => <li key={i}>· {e}</li>)}</ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
