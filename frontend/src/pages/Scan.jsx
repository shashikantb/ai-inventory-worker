import React, { useEffect, useRef, useState } from "react";
import { BrowserMultiFormatReader } from "@zxing/browser";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScanLine, Camera, Loader2, Upload, X, MapPin } from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Link } from "react-router-dom";

const readerRef = { current: null };

export default function Scan() {
  const [tab, setTab] = useState("barcode");
  const videoRef = useRef(null);
  const [scanning, setScanning] = useState(false);
  const [result, setResult] = useState(null);
  const [manual, setManual] = useState("");
  const [imgPreview, setImgPreview] = useState(null);
  const [imgResult, setImgResult] = useState(null);
  const [imgLoading, setImgLoading] = useState(false);

  const stopScan = async () => {
    setScanning(false);
    try {
      const stream = videoRef.current?.srcObject;
      stream?.getTracks?.().forEach(t => t.stop());
      if (videoRef.current) videoRef.current.srcObject = null;
    } catch {}
  };

  useEffect(() => () => { stopScan(); }, []);

  const startScan = async () => {
    setResult(null);
    setScanning(true);
    try {
      if (!readerRef.current) readerRef.current = new BrowserMultiFormatReader();
      const devices = await BrowserMultiFormatReader.listVideoInputDevices();
      const deviceId = devices.find(d => /back|rear|environment/i.test(d.label))?.deviceId || devices[0]?.deviceId;
      await readerRef.current.decodeFromVideoDevice(deviceId, videoRef.current, async (res, err, controls) => {
        if (res) {
          controls.stop();
          await lookup(res.getText());
          await stopScan();
        }
      });
    } catch (e) {
      toast.error("Camera error: " + e.message);
      setScanning(false);
    }
  };

  const lookup = async (code) => {
    try {
      const { data } = await api.get(`/scan/barcode/${encodeURIComponent(code)}`);
      setResult({ code, ...data });
      toast.success(`Found: ${data.product.name}`);
    } catch (e) {
      setResult({ code, notFound: true });
      toast.error(`No product for barcode ${code}`);
    }
  };

  const handleImgFile = async (file) => {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = async () => {
      const dataUrl = reader.result;
      setImgPreview(dataUrl);
      setImgResult(null);
      setImgLoading(true);
      try {
        const base64 = dataUrl.split(",")[1];
        const { data } = await api.post("/scan/image", { image_base64: base64 });
        setImgResult(data);
      } catch (e) {
        toast.error(e.response?.data?.detail || "Recognition failed");
      } finally { setImgLoading(false); }
    };
    reader.readAsDataURL(file);
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6" data-testid="scan-page">
      <div>
        <div className="text-xs font-mono uppercase tracking-widest text-primary mb-1">Scan</div>
        <h1 className="font-heading font-extrabold uppercase text-3xl sm:text-4xl tracking-tight">Scan a product</h1>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="grid grid-cols-2 w-full sm:w-96">
          <TabsTrigger value="barcode" data-testid="tab-barcode"><ScanLine className="w-4 h-4 mr-2" /> Barcode</TabsTrigger>
          <TabsTrigger value="image" data-testid="tab-image"><Camera className="w-4 h-4 mr-2" /> Photo ID</TabsTrigger>
        </TabsList>

        <TabsContent value="barcode" className="space-y-4 mt-6">
          <div className="tactical-card p-4">
            <div className="relative aspect-video max-h-96 bg-black rounded-lg overflow-hidden border border-border">
              <video ref={videoRef} className="w-full h-full object-cover" playsInline muted />
              {scanning && (
                <>
                  <div className="absolute inset-8 border-2 border-primary/70 rounded-lg pointer-events-none" />
                  <div className="absolute left-8 right-8 top-8 h-0.5 bg-primary scanner-laser shadow-[0_0_12px_hsl(var(--primary))]" />
                </>
              )}
              {!scanning && (
                <div className="absolute inset-0 flex flex-col items-center justify-center text-muted-foreground">
                  <ScanLine className="w-12 h-12 mb-2" />
                  <div className="text-sm">Camera off</div>
                </div>
              )}
            </div>
            <div className="mt-4 flex gap-2">
              {!scanning ? (
                <Button onClick={startScan} className="bg-primary text-primary-foreground h-12 flex-1" data-testid="start-scan-btn"><Camera className="w-4 h-4 mr-2" /> Start camera</Button>
              ) : (
                <Button onClick={stopScan} variant="outline" className="h-12 flex-1" data-testid="stop-scan-btn"><X className="w-4 h-4 mr-2" /> Stop</Button>
              )}
            </div>
          </div>

          <div className="tactical-card p-4">
            <div className="text-xs font-mono uppercase tracking-widest text-muted-foreground mb-2">Or enter manually</div>
            <div className="flex gap-2">
              <Input value={manual} onChange={e => setManual(e.target.value)} placeholder="Barcode / SKU" data-testid="manual-barcode-input" className="h-11" />
              <Button onClick={() => manual && lookup(manual)} className="h-11 bg-accent text-accent-foreground hover:bg-accent/90" data-testid="manual-lookup-btn">Look up</Button>
            </div>
          </div>

          {result && (
            <div className="tactical-card p-6" data-testid="scan-result">
              <div className="text-xs font-mono uppercase text-muted-foreground mb-1">Barcode: {result.code}</div>
              {result.notFound ? (
                <div className="text-destructive font-semibold">Product not found</div>
              ) : (
                <>
                  <h3 className="font-heading font-bold text-2xl uppercase">{result.product.name}</h3>
                  <div className="flex gap-2 flex-wrap mt-2">
                    <Badge variant="outline" className="font-mono">SKU {result.product.sku}</Badge>
                    {result.product.brand && <Badge variant="outline">{result.product.brand}</Badge>}
                    {result.product.category && <Badge variant="secondary">{result.product.category}</Badge>}
                  </div>
                  <div className="mt-4 space-y-2">
                    {result.inventory.map((i, idx) => (
                      <div key={idx} className="flex items-center justify-between p-3 rounded bg-secondary/60 border border-border">
                        <div className="flex items-start gap-2 min-w-0">
                          <MapPin className="w-4 h-4 text-primary mt-0.5 shrink-0" />
                          <div className="min-w-0">
                            <div className="font-semibold text-sm truncate">{i.warehouse_name}</div>
                            {i.location_path && <div className="text-xs font-mono text-muted-foreground truncate">{i.location_path}</div>}
                          </div>
                        </div>
                        <div className="text-right shrink-0 ml-3">
                          <div className="font-mono font-bold text-lg">{i.quantity}</div>
                          <div className="text-[10px] uppercase text-muted-foreground">units</div>
                        </div>
                      </div>
                    ))}
                  </div>
                  <Link to={`/app/products/${result.product.id}`}>
                    <Button variant="outline" className="mt-4 w-full" data-testid="view-product-btn">View product details</Button>
                  </Link>
                </>
              )}
            </div>
          )}
        </TabsContent>

        <TabsContent value="image" className="space-y-4 mt-6">
          <div className="tactical-card p-4">
            <label className="block cursor-pointer">
              <input type="file" accept="image/*" capture="environment" className="hidden" onChange={e => handleImgFile(e.target.files?.[0])} data-testid="image-upload-input" />
              <div className="border-2 border-dashed border-border rounded-lg aspect-video max-h-80 flex flex-col items-center justify-center text-muted-foreground hover:border-primary/50 transition-colors relative overflow-hidden">
                {imgPreview ? <img src={imgPreview} alt="preview" className="w-full h-full object-contain" /> : (
                  <>
                    <Upload className="w-10 h-10 mb-2" />
                    <div className="text-sm font-semibold">Tap to take a photo or upload</div>
                    <div className="text-xs mt-1">AI will identify the product</div>
                  </>
                )}
              </div>
            </label>
          </div>

          {imgLoading && (
            <div className="tactical-card p-6 flex items-center gap-3">
              <Loader2 className="w-5 h-5 animate-spin text-primary" />
              <div className="text-sm">Analyzing image with Gemini…</div>
            </div>
          )}

          {imgResult && (
            <div className="tactical-card p-6" data-testid="image-result">
              <div className="text-xs font-mono uppercase text-muted-foreground mb-1">AI Identification</div>
              <h3 className="font-heading font-bold text-2xl uppercase">{imgResult.identification?.identified_name}</h3>
              <div className="text-sm text-muted-foreground mt-1">{imgResult.identification?.notes}</div>
              <div className="mt-3 flex gap-2 flex-wrap">
                {imgResult.identification?.brand && <Badge variant="outline">{imgResult.identification.brand}</Badge>}
                {imgResult.identification?.category && <Badge variant="secondary">{imgResult.identification.category}</Badge>}
                <Badge className="bg-primary/20 text-primary border-primary/30">Confidence: {Math.round((imgResult.identification?.confidence || 0) * 100)}%</Badge>
              </div>
              {imgResult.matches?.length > 0 ? (
                <div className="mt-5">
                  <div className="text-xs font-mono uppercase text-muted-foreground mb-2">Possible catalog matches</div>
                  <div className="space-y-2">
                    {imgResult.matches.map((m, idx) => (
                      <Link key={idx} to={`/app/products/${m.product.id}`} className="flex items-center justify-between p-3 rounded bg-secondary/60 border border-border hover:border-primary/50" data-testid={`match-${idx}`}>
                        <div>
                          <div className="font-semibold text-sm">{m.product.name}</div>
                          <div className="text-xs font-mono text-muted-foreground">SKU {m.product.sku}</div>
                        </div>
                        <Badge variant="outline">{Math.round(m.confidence * 100)}%</Badge>
                      </Link>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="mt-4 text-sm text-muted-foreground">No catalog match found.</div>
              )}
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
