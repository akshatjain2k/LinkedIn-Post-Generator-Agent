"use client";

import { useState } from "react";
import { Sparkles, ArrowRight, Loader2, FileText, Image as ImageIcon } from "lucide-react";

export default function Home() {
  const [topic, setTopic] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{
    text: string;
    pdfPath: string | null;
    base64Image: string | null;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!topic.trim()) return;

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const res = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic }),
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.error || "Failed to generate post");
      }

      // The MCP Tool returns a single text block which might contain:
      // "[PDF saved -> path]"
      // "--- Image Base64 Data ---"
      // "data:image/png;base64,..."
      
      let rawText = "";
      if (data.content && Array.isArray(data.content)) {
        rawText = data.content[0]?.text || "";
      } else {
        rawText = typeof data === 'string' ? data : JSON.stringify(data);
      }

      // Parse the rawText to extract post, pdf path, and base64
      let cleanText = rawText;
      let pdfPath = null;
      let base64Image = null;

      // Extract Base64
      const base64Match = rawText.match(/--- Image Base64 Data ---\n([\s\S]+?)\n-------------------------/);
      if (base64Match) {
        base64Image = base64Match[1].trim();
        cleanText = cleanText.replace(base64Match[0], "");
      }

      // Extract PDF Path
      const pdfMatch = cleanText.match(/\[PDF saved → (.*?)\]/);
      if (pdfMatch) {
        pdfPath = pdfMatch[1];
      }
      
      // Clean up the text
      cleanText = cleanText.replace(/\[PDF saved → .*?\]/g, "");
      cleanText = cleanText.replace(/\[Image saved → .*?\]/g, "");
      cleanText = cleanText.trim();

      setResult({
        text: cleanText,
        pdfPath,
        base64Image: base64Image?.startsWith("data:image") ? base64Image : `data:image/png;base64,${base64Image}`,
      });
    } catch (err: any) {
      setError(err.message || "An unexpected error occurred");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="container">
      <h1>AI Post Creator</h1>
      <p className="subtitle">
        Generate highly researched, developer-focused LinkedIn posts with dynamic architectural diagrams.
      </p>

      <div className="glass-panel input-wrapper">
        <form onSubmit={handleSubmit} style={{ display: 'flex', width: '100%', gap: '1rem' }}>
          <input
            type="text"
            className="glass-input"
            placeholder="What should the post be about? (e.g. Redis caching strategies)"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            disabled={loading}
          />
          <button type="submit" className="btn-primary" disabled={loading || !topic.trim()}>
            {loading ? (
              <>
                <div className="spinner" /> Generating...
              </>
            ) : (
              <>
                <Sparkles size={20} /> Generate <ArrowRight size={20} />
              </>
            )}
          </button>
        </form>
      </div>

      {error && (
        <div className="error-message">
          <strong>Error:</strong> {error}
        </div>
      )}

      {loading && (
        <div className="glass-panel" style={{ textAlign: 'center', padding: '4rem 2rem' }}>
          <div className="spinner" style={{ margin: '0 auto 1.5rem', width: '40px', height: '40px', borderWidth: '4px' }} />
          <h3 style={{ color: 'var(--text-primary)', marginBottom: '0.5rem' }}>Agent is Working</h3>
          <p style={{ color: 'var(--text-secondary)' }}>
            Researching, evaluating, and generating image... <br/>
            This typically takes about 60 seconds.
          </p>
        </div>
      )}

      {result && !loading && (
        <div className="result-container">
          {/* Post Text Column */}
          <div className="glass-panel result-card">
            <h3><FileText size={18} /> Generated Post</h3>
            <div className="post-text">{result.text}</div>
            
            {result.pdfPath && (
              <div style={{ marginTop: '2rem', padding: '1rem', background: 'rgba(255,255,255,0.05)', borderRadius: '8px', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                <strong>PDF Saved:</strong> {result.pdfPath}
              </div>
            )}
          </div>

          {/* Generated Image Column */}
          <div className="glass-panel result-card">
            <h3><ImageIcon size={18} /> Architectural Diagram</h3>
            {result.base64Image && !result.base64Image.includes("null") ? (
              <img 
                src={result.base64Image} 
                alt="Generated Diagram" 
                className="generated-image"
              />
            ) : (
              <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-secondary)', background: 'rgba(0,0,0,0.2)', borderRadius: '8px' }}>
                No image data received
              </div>
            )}
          </div>
        </div>
      )}
    </main>
  );
}
