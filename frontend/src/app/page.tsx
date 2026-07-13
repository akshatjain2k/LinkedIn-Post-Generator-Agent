"use client";

import { useState, useEffect } from "react";
import { Sparkles, ArrowRight, FileText, Image as ImageIcon, Sun, Moon, ImageOff, Download, Maximize2, X, Copy, Check, Send } from "lucide-react";

export default function Home() {
  const [topic, setTopic] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{
    text: string;
    pdfPath: string | null;
    base64Image: string | null;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [theme, setTheme] = useState<"light" | "dark">("dark");
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    document.body.setAttribute("data-theme", theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme(prev => prev === "dark" ? "light" : "dark");
  };

  const handleCopy = () => {
    if (result?.text) {
      navigator.clipboard.writeText(result.text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handlePostToLinkedIn = () => {
    if (result?.text) {
      navigator.clipboard.writeText(result.text);
      setToast("Post copied! Paste it in the new tab.");
      setTimeout(() => setToast(null), 4000);
      window.open("https://www.linkedin.com/feed/", "_blank");
    }
  };

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

      let rawText = "";
      if (data.content && Array.isArray(data.content)) {
        rawText = data.content[0]?.text || "";
      } else {
        rawText = typeof data === 'string' ? data : JSON.stringify(data);
      }

      let cleanText = rawText;
      let pdfPath = null;
      let base64Image = null;

      if (rawText.includes("--- Image Base64 Data ---")) {
        const parts = rawText.split("--- Image Base64 Data ---\n");
        if (parts.length > 1) {
          const b64Part = parts[1].split("\n-------------------------")[0];
          base64Image = b64Part.trim();
          cleanText = parts[0].trim();
        }
      }

      const pdfMatch = cleanText.match(/\[PDF saved → (.*?)\]/);
      if (pdfMatch) {
        pdfPath = pdfMatch[1];
      }
      
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

  // Extract hashtags from the end of the text block
  const parsePostContent = (text: string) => {
    const match = text.match(/(?:#[\w\d_]+\s*)+$/);
    let hashtags: string[] = [];
    let mainText = text;

    if (match) {
      hashtags = match[0].match(/#[\w\d_]+/g) || [];
      mainText = text.slice(0, match.index).trim();
    }

    return { mainText, hashtags };
  };

  const renderTypewriterText = (text: string) => {
    return text.split('\n').map((paragraph, index) => {
      if (!paragraph.trim()) return null;
      return (
        <div 
          key={index} 
          className="post-paragraph"
          style={{ animationDelay: `${index * 150}ms` }}
        >
          {paragraph}
        </div>
      );
    });
  };

  let wordCount = 0;
  let charCount = 0;
  let readTime = 0;
  let mainText = "";
  let hashtags: string[] = [];

  if (result) {
    const parsed = parsePostContent(result.text);
    mainText = parsed.mainText;
    hashtags = parsed.hashtags;
    wordCount = mainText.split(/\s+/).filter(w => w.length > 0).length;
    charCount = mainText.length;
    readTime = Math.ceil(wordCount / 200);
  }

  return (
    <>
      <main className="container">
        {toast && (
          <div className="toast-notification">
            <Check size={16} /> {toast}
          </div>
        )}

        <button className="theme-toggle" onClick={toggleTheme} aria-label="Toggle Theme">
          {theme === "dark" ? <Sun size={20} /> : <Moon size={20} />}
        </button>

        <h1>AI Post Creator</h1>
        <p className="subtitle">
          Generate highly researched, developer-focused LinkedIn posts with dynamic architectural diagrams in a single click.
        </p>

        <div className="glass-panel input-wrapper">
          <form onSubmit={handleSubmit} style={{ display: 'flex', width: '100%', gap: '1rem', flexWrap: 'wrap' }}>
            <input
              type="text"
              className="glass-input"
              placeholder="What should the post be about? (e.g. LLM routing strategies)"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              disabled={loading}
            />
            <button type="submit" className={`btn-primary ${loading ? 'thinking' : ''}`} disabled={loading || !topic.trim()}>
              {loading ? (
                <>
                  <Sparkles size={18} className="spin" style={{ animation: "spinSlow 2s linear infinite" }} /> Generating...
                </>
              ) : (
                <>
                  <Sparkles size={18} /> Generate <ArrowRight size={18} />
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

        {(loading || result) && (
          <div className="result-container">
            {/* Post Text Column */}
            <div className="glass-panel result-card animate-enter-1" style={{ display: 'flex', flexDirection: 'column', maxHeight: '75vh' }}>
              <div className="card-header" style={{ flexShrink: 0 }}>
                <h3><FileText size={20} /> Generated Post</h3>
                {result && (
                  <button onClick={handleCopy} className="btn-icon" title="Copy to clipboard">
                    {copied ? <Check size={16} className="text-success" /> : <Copy size={16} />}
                  </button>
                )}
              </div>
              
              <div className="scrollable-panel" style={{ flex: 1, paddingRight: '1rem' }}>
                {loading ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                    <div className="skeleton-box" style={{ height: '20px', width: '80%' }} />
                    <div className="skeleton-box" style={{ height: '20px', width: '100%' }} />
                    <div className="skeleton-box" style={{ height: '20px', width: '90%' }} />
                    <div className="skeleton-box" style={{ height: '20px', width: '70%' }} />
                    <div className="skeleton-box" style={{ height: '20px', width: '85%' }} />
                    <br/>
                    <div className="skeleton-box" style={{ height: '20px', width: '95%' }} />
                    <div className="skeleton-box" style={{ height: '20px', width: '100%' }} />
                    <div className="skeleton-box" style={{ height: '20px', width: '60%' }} />
                  </div>
                ) : (
                  <>
                    <div className="metrics-bar">
                      <span>{wordCount} words</span>
                      <span className="divider">•</span>
                      <span className={charCount > 3000 ? "text-warning" : ""}>
                        {charCount.toLocaleString()} / 3,000 chars
                      </span>
                      <span className="divider">•</span>
                      <span>~{readTime} min read</span>
                    </div>

                    <div className="post-text">{renderTypewriterText(mainText)}</div>
                    
                    {hashtags.length > 0 && (
                      <div className="hashtag-container">
                        {hashtags.map((tag, idx) => (
                          <span key={idx} className="hashtag-chip" style={{ animationDelay: `${idx * 100}ms` }}>
                            {tag}
                          </span>
                        ))}
                      </div>
                    )}
                  </>
                )}
              </div>

              {!loading && (
                <div className="actions-footer" style={{ flexShrink: 0 }}>
                  <button onClick={handlePostToLinkedIn} className="btn-linkedin">
                    <Send size={16} /> Post to LinkedIn
                  </button>
                  {result?.pdfPath && (
                    <a href={`/api/download?file=${encodeURIComponent(result.pdfPath)}`} className="btn-secondary" download>
                      <Download size={14} /> PDF
                    </a>
                  )}
                </div>
              )}
            </div>

            {/* Generated Image Column */}
            <div className="glass-panel result-card animate-enter-2" style={{ display: 'flex', flexDirection: 'column', maxHeight: '75vh' }}>
              <h3 style={{ flexShrink: 0, marginBottom: '2rem' }}><ImageIcon size={20} /> Architectural Diagram</h3>
              
              <div className="scrollable-panel" style={{ flex: 1, paddingRight: '0.5rem', display: 'flex', flexDirection: 'column' }}>
                {loading ? (
                  <div className="skeleton-box" style={{ minHeight: '300px', height: '100%', flex: 1 }} />
                ) : result?.base64Image && !result.base64Image.includes("null") ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', flex: 1 }}>
                    <div className="design-canvas">
                      <div 
                        className="image-wrapper canvas-image" 
                        onClick={() => setIsModalOpen(true)}
                      >
                        <img 
                          src={result.base64Image} 
                          alt="Generated Diagram" 
                          className="generated-image"
                        />
                        <div className="maximize-btn">
                          <Maximize2 size={16} />
                        </div>
                      </div>
                    </div>
                    
                    <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 'auto' }}>
                      <a href={result.base64Image} className="btn-secondary" download="Architectural_Diagram.png">
                        <Download size={14} /> Download Image
                      </a>
                    </div>
                  </div>
                ) : (
                  <div className="empty-state design-canvas">
                    <ImageOff size={48} />
                    <p>Diagram generation failed.<br/>Try tweaking your prompt!</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </main>

      {/* Full Screen Image Modal (Lightbox) */}
      {isModalOpen && result?.base64Image && (
        <div className="modal-overlay" onClick={() => setIsModalOpen(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <button className="modal-close" onClick={() => setIsModalOpen(false)} aria-label="Close image">
              <X size={20} />
            </button>
            <img src={result.base64Image} alt="Large Diagram" className="modal-image" />
          </div>
        </div>
      )}
    </>
  );
}
