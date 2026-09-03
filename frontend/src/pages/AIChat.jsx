import React, { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { Sparkles, Send, Loader2, User, Wrench, Bot, Mic, MicOff, Volume2, VolumeX } from "lucide-react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api } from "@/lib/api";
import { toast } from "sonner";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const SUGGESTIONS = [
  "Where is Samsung Monitor 24M?",
  "Show low stock items",
  "How many N95 masks do we have?",
  "Find Dell laptops",
];

export default function AIChat() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const [model, setModel] = useState("claude");
  const [speak, setSpeak] = useState(() => localStorage.getItem("aiw_speak") === "1");
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const mediaRef = useRef(null);
  const chunksRef = useRef([]);
  const endRef = useRef(null);

  useEffect(() => { localStorage.setItem("aiw_speak", speak ? "1" : "0"); }, [speak]);
  const speakText = (text) => {
    try {
      const t = (text || "").trim(); if (!t) return;
      const u = new SpeechSynthesisUtterance(t);
      u.rate = 1.05; u.pitch = 1;
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(u);
    } catch {}
  };

  const startRec = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream);
      chunksRef.current = [];
      mr.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data); };
      mr.onstop = async () => {
        stream.getTracks().forEach(t => t.stop());
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        setTranscribing(true);
        try {
          const fd = new FormData();
          fd.append("file", blob, "voice.webm");
          const { data } = await api.post("/voice/transcribe", fd, { headers: { "Content-Type": "multipart/form-data" } });
          const text = (data.text || "").trim();
          if (text) send(text);
          else toast.error("Nothing transcribed");
        } catch (err) { toast.error(err.response?.data?.detail || "Transcription failed"); }
        finally { setTranscribing(false); }
      };
      mediaRef.current = mr;
      mr.start();
      setRecording(true);
    } catch (e) { toast.error("Microphone error: " + e.message); }
  };
  const stopRec = () => { mediaRef.current?.stop(); setRecording(false); };

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  const send = async (text) => {
    const q = (text ?? input).trim();
    if (!q || loading) return;
    setInput("");
    setMessages(m => [...m, { role: "user", content: q }, { role: "assistant", content: "", tools: [] }]);
    setLoading(true);
    try {
      const token = localStorage.getItem("aiw_token");
      const resp = await fetch(`${API}/ai/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ message: q, session_id: sessionId, model }),
      });
      if (!resp.ok || !resp.body) throw new Error("Chat request failed");
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split("\n\n");
        buf = lines.pop() || "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const data = JSON.parse(line.slice(6));
          if (data.type === "text") {
            setMessages(m => {
              const copy = [...m];
              copy[copy.length - 1] = { ...copy[copy.length - 1], content: copy[copy.length - 1].content + data.content };
              return copy;
            });
          } else if (data.type === "tool_start") {
            setMessages(m => {
              const copy = [...m];
              const last = copy[copy.length - 1];
              last.tools = [...(last.tools || []), { name: data.name, status: "running" }];
              return copy;
            });
          } else if (data.type === "tool_result") {
            setMessages(m => {
              const copy = [...m];
              const last = copy[copy.length - 1];
              const idx = last.tools?.findIndex(t => t.name === data.name && t.status === "running");
              if (idx > -1) last.tools[idx] = { name: data.name, status: "done", result: data.result };
              return copy;
            });
          } else if (data.type === "done") {
            setSessionId(data.session_id);
            if (speak) {
              setMessages(cur => { const last = cur[cur.length - 1]; if (last?.role === "assistant") speakText(last.content); return cur; });
            }
          } else if (data.type === "error") {
            toast.error(data.error);
          }
        }
      }
    } catch (e) {
      toast.error(e.message);
    } finally { setLoading(false); }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)] max-w-4xl mx-auto" data-testid="ai-chat-page">
      <div className="flex items-center justify-between mb-4">
        <div>
          <div className="text-xs font-mono uppercase tracking-widest text-primary mb-1">AI Assistant</div>
          <h1 className="font-heading font-extrabold uppercase text-3xl tracking-tight">Ask anything</h1>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => { setSpeak(!speak); if (speak) window.speechSynthesis?.cancel(); }} className={speak ? "border-primary/50 text-primary" : ""} data-testid="ai-speak-toggle">
            {speak ? <Volume2 className="w-4 h-4 mr-1.5" /> : <VolumeX className="w-4 h-4 mr-1.5" />}
            {speak ? "Voice on" : "Voice off"}
          </Button>
          <Select value={model} onValueChange={setModel}>
            <SelectTrigger className="w-40" data-testid="ai-model-select"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="claude">Claude Sonnet 4.6</SelectItem>
              <SelectItem value="gemini">Gemini 3 Flash</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto space-y-4 pb-4">
        {messages.length === 0 ? (
          <div className="text-center py-16">
            <div className="w-16 h-16 mx-auto rounded-2xl bg-primary/15 border border-primary/30 flex items-center justify-center mb-4">
              <Sparkles className="w-8 h-8 text-primary" />
            </div>
            <div className="font-heading font-bold uppercase text-xl mb-2">How can I help?</div>
            <p className="text-sm text-muted-foreground mb-6">Search products, check inventory, or find a location</p>
            <div className="grid sm:grid-cols-2 gap-2 max-w-lg mx-auto">
              {SUGGESTIONS.map(s => (
                <button key={s} onClick={() => send(s)} data-testid={`suggestion-${s.slice(0,10)}`} className="tactical-card p-3 text-sm text-left hover:border-primary/50">
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : messages.map((m, i) => (
          <div key={i} className={`flex gap-3 ${m.role === "user" ? "justify-end" : ""}`} data-testid={`msg-${i}`}>
            {m.role === "assistant" && <div className="w-8 h-8 rounded-lg bg-primary/15 border border-primary/30 flex items-center justify-center shrink-0"><Bot className="w-4 h-4 text-primary" /></div>}
            <div className={`max-w-[80%] ${m.role === "user" ? "bg-primary/15 border-primary/30" : "bg-card border-border"} border rounded-2xl p-4`}>
              {m.tools?.map((t, ti) => (
                <div key={ti} className="mb-2 text-xs font-mono uppercase text-muted-foreground flex items-center gap-1.5">
                  <Wrench className="w-3 h-3" />
                  <span>{t.name}</span>
                  {t.status === "running" ? <Loader2 className="w-3 h-3 animate-spin" /> : <span className="text-primary">✓</span>}
                </div>
              ))}
              <div className="whitespace-pre-wrap text-sm leading-relaxed">{m.content || (loading && m.role === "assistant" && i === messages.length - 1 ? <span className="text-muted-foreground">Thinking…</span> : "")}</div>
            </div>
            {m.role === "user" && <div className="w-8 h-8 rounded-lg bg-secondary border border-border flex items-center justify-center shrink-0"><User className="w-4 h-4" /></div>}
          </div>
        ))}
        <div ref={endRef} />
      </div>

      <form onSubmit={(e) => { e.preventDefault(); send(); }} className="flex gap-2 border-t border-border pt-4">
        <Input value={input} onChange={e => setInput(e.target.value)} placeholder={recording ? "Recording…" : (transcribing ? "Transcribing…" : "Ask about a product, inventory, or location…")} data-testid="ai-chat-input" className="h-12 text-base" disabled={loading || recording || transcribing} />
        <Button type="button" onClick={recording ? stopRec : startRec} disabled={loading || transcribing} className={`h-12 w-12 p-0 shrink-0 ${recording ? "bg-destructive text-destructive-foreground hover:bg-destructive/90 pulse-amber" : "bg-accent text-accent-foreground hover:bg-accent/90"}`} data-testid="ai-mic-btn" title={recording ? "Stop recording" : "Speak"}>
          {transcribing ? <Loader2 className="w-4 h-4 animate-spin" /> : recording ? <MicOff className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
        </Button>
        <Button type="submit" disabled={loading || !input.trim()} className="h-12 px-6 bg-primary text-primary-foreground hover:bg-primary/90" data-testid="ai-chat-send-btn">
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
        </Button>
      </form>
    </div>
  );
}
