#!/usr/bin/env python3
"""
faq-bot — a small-business FAQ chatbot portfolio piece.
Pure Python stdlib (http.server + sqlite FTS5). No pip installs needed.

Run:   python3 server.py            -> http://localhost:8000
Test:  curl -X POST localhost:8000/api/chat -d '{"message":"how long does shipping take?"}'

Optional upgrade path (real semantic search):
  export OPENAI_API_KEY=sk-...     # embeddings fetched automatically on first run
  Then retrieval becomes vector-based (text-embedding-3-small) instead of keyword.

Swap the business by editing faqs.json. Keep the same shape:
  [{"category": "...", "q": "...", "a": "..."}, ...]
"""

import json
import math
import os
import re
import sqlite3
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("PORT", "8000"))
FAQ_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "faqs.json")
EMB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "faqs_emb.json")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
EMB_MODEL = "text-embedding-3-small"

STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "to", "for", "of", "in",
    "on", "with", "and", "or", "what", "where", "when", "how", "does", "do",
    "did", "can", "could", "would", "should", "i", "my", "me", "you", "your",
    "it", "its", "this", "that", "there", "about", "get", "got", "have",
}


def tokenize(text):
    return [t for t in re.findall(r"[a-z0-9']+", text.lower()) if t not in STOPWORDS]


def load_faqs():
    with open(FAQ_FILE, encoding="utf-8") as f:
        return json.load(f)


def build_index(faqs):
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.execute("CREATE VIRTUAL TABLE faqs USING fts5(question, answer, category)")
    conn.executemany(
        "INSERT INTO faqs(question, answer, category) VALUES (?, ?, ?)",
        [(f["q"], f["a"], f.get("category", "")) for f in faqs],
    )
    conn.commit()
    return conn


QUERY_LOCK = threading.Lock()


def fts_query(conn, text):
    """Top-3 FAQ rows by keyword match, plus a token-overlap confidence in [0,1]."""
    tokens = tokenize(text)
    if not tokens:
        return []
    match_expr = " AND ".join('"' + t.replace('"', "") + '"' for t in tokens)
    try:
        with QUERY_LOCK:
            rows = conn.execute(
                "SELECT question, answer, category, bm25(faqs) AS score "
                "FROM faqs WHERE faqs MATCH ? ORDER BY score LIMIT 3",
                (match_expr,),
            ).fetchall()
    except sqlite3.OperationalError:
        rows = []
    out = []
    q_tokens = set(tokens)
    for question, answer, category, _score in rows:
        overlap = len(q_tokens & set(tokenize(question))) / len(q_tokens)
        out.append({"q": question, "a": answer, "category": category, "confidence": overlap})
    return out


# ---- optional semantic retrieval via OpenAI embeddings --------------------

def embed(texts):
    payload = json.dumps({
        "model": EMB_MODEL,
        "input": texts,
    }).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/embeddings",
        data=payload,
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    return [item["embedding"] for item in data["data"]]


def ensure_embeddings(faqs):
    """Cache FAQ embeddings to faqs_emb.json; call once at startup."""
    if os.path.exists(EMB_FILE):
        with open(EMB_FILE, encoding="utf-8") as f:
            return json.load(f)
    cached = []
    for i in range(0, len(faqs), 64):
        batch = [faqs[j]["q"] + " " + faqs[j]["a"] for j in range(i, i + 64)]
        cached.extend(embed(batch))
    with open(EMB_FILE, "w", encoding="utf-8") as f:
        json.dump(cached, f)
    return cached


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb + 1e-9)


def semantic_search(faq_embs, text):
    q_emb = embed([text])[0]
    scored = sorted(
        ((cosine(q_emb, e), i) for i, e in enumerate(faq_embs)),
        reverse=True,
    )
    return scored


# ---- app state -------------------------------------------------------------

FAQS = load_faqs()
CONN = build_index(FAQS)
FAQ_EMBS = ensure_embeddings(FAQS) if OPENAI_API_KEY else None
SEMANTIC = FAQ_EMBS is not None


def answer(message):
    message = (message or "").strip()
    if not message:
        return {"reply": "Ask me anything about ordering, shipping, subscriptions or refunds.", "matched": None, "confidence": 0}

    if SEMANTIC:
        scored = semantic_search(FAQ_EMBS, message)
        best, idx = scored[0]
        if best >= 0.35:
            f = FAQS[idx]
            return {"reply": f["a"], "matched": f["q"], "confidence": round(best, 2)}
    else:
        hits = fts_query(CONN, message)
        if hits and hits[0]["confidence"] >= 0.34:
            h = hits[0]
            # blend: prefer high overlap even if a later row is also good
            extras = " ".join("- " + x["q"] for x in hits[1:] if x["confidence"] > 0)
            reply = h["a"] + (f"\n\nRelated: {extras}" if extras else "")
            return {"reply": reply, "matched": h["q"], "confidence": round(h["confidence"], 2)}

    return {
        "reply": "I'm not sure about that one yet. Try rephrasing, or email support@example.com "
                 "and we'll get back to you within a few hours.",
        "matched": None,
        "confidence": 0,
    }


# ---- HTTP layer ------------------------------------------------------------

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Brew &amp; Bean Co. — Support</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family:'Segoe UI', system-ui, sans-serif; background:#0f172a; color:#e2e8f0;
         min-height:100vh; display:flex; flex-direction:column; }
  header { padding:1.2rem 1.5rem; border-bottom:1px solid #1e293b; display:flex;
           align-items:center; gap:.75rem; }
  .dot { width:10px; height:10px; border-radius:50%; background:#34d399;
         box-shadow:0 0 8px #34d399; }
  header h1 { font-size:1.05rem; font-weight:600; }
  header span { color:#64748b; font-size:.85rem; }
  main { flex:1; width:min(720px, 100%); margin:0 auto; padding:1.5rem;
         display:flex; flex-direction:column; gap:1rem; overflow-y:auto; }
  .msg { max-width:80%; padding:.75rem 1rem; border-radius:12px; font-size:.95rem;
         line-height:1.45; white-space:pre-wrap; }
  .user { align-self:flex-end; background:#155e75; border-bottom-right-radius:3px; }
  .bot { align-self:flex-start; background:#1e293b; border-bottom-left-radius:3px; }
  .src { display:block; margin-top:.4rem; font-size:.72rem; color:#22d3ee; }
  .chip { border:1px solid #334155; color:#94a3b8; background:transparent; border-radius:999px;
          padding:.4rem .85rem; font-size:.8rem; cursor:pointer; }
  .chip:hover { border-color:#22d3ee; color:#22d3ee; }
  form { display:flex; gap:.6rem; padding:1rem 1.5rem; border-top:1px solid #1e293b; }
  input { flex:1; background:#0b1220; border:1px solid #334155; border-radius:8px;
          padding:.8rem 1rem; color:#e2e8f0; font-size:.95rem; outline:none; }
  input:focus { border-color:#22d3ee; }
  button { background:#22d3ee; color:#082f49; border:0; border-radius:8px; padding:0 1.3rem;
           font-weight:700; cursor:pointer; }
  button:disabled { opacity:.5; cursor:wait; }
  .typing { color:#64748b; font-size:.85rem; padding:.25rem .5rem; }
</style>
</head>
<body>
<header>
  <div class="dot"></div>
  <h1>Brew &amp; Bean Co. — Support</h1>
  <span>answers from our FAQ</span>
</header>
<main id="chat">
  <div class="msg bot">Hi! I'm the Brew &amp; Bean assistant. Ask me about ordering, shipping,
    subscriptions, or refunds.</div>
  <div style="display:flex; gap:.5rem; flex-wrap:wrap" id="chips"></div>
</main>
<form id="f">
  <input id="in" placeholder="Type your question…" autocomplete="off">
  <button id="send">Ask</button>
</form>
<script>
  const chips = ["How long does shipping take?","When is my next roast shipped?",
                 "Can I pause my plan?","What's your refund policy?","Do you offer decaf?"];
  const chipBox = document.getElementById('chips');
  chips.forEach(c => { const b = document.createElement('button');
    b.className = 'chip'; b.textContent = c;
    b.onclick = () => { document.getElementById('in').value = c; ask(); }; chipBox.appendChild(b); });

  const chat = document.getElementById('chat'), form = document.getElementById('f'),
        input = document.getElementById('in'), send = document.getElementById('send');
  function addMsg(text, cls) { const d = document.createElement('div');
    d.className = 'msg ' + cls; d.textContent = text; chat.appendChild(d);
    chat.scrollTop = chat.scrollHeight; return d; }
  async function ask() {
    const m = input.value.trim(); if (!m) return;
    addMsg(m, 'user'); input.value = '';
    const t = addMsg('…', 'bot'); t.classList.add('typing'); t.textContent = 'thinking…';
    send.disabled = true;
    try {
      const r = await fetch('/api/chat', { method:'POST',
        headers:{'Content-Type':'application/json'}, body: JSON.stringify({message:m}) });
      const d = await r.json();
      t.classList.remove('typing'); t.textContent = d.reply;
      if (d.matched) { const s = document.createElement('span');
        s.className = 'src'; s.textContent = 'matched: ' + d.matched; t.appendChild(s); }
    } catch (e) { t.textContent = 'Sorry, something broke. Try again.'; }
    send.disabled = false; input.focus();
  }
  form.addEventListener('submit', e => { e.preventDefault(); ask(); });
</script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/health":
            return self._send(200, {"ok": True, "semantic": SEMANTIC, "faqs": len(FAQS)})
        return self._send(200, PAGE.encode("utf-8"), "text/html")

    def do_POST(self):
        if self.path != "/api/chat":
            return self._send(404, {"error": "not found"})
        try:
            length = int(self.headers.get("Content-Length", 0))
            message = json.loads(self.rfile.read(length) or b"{}").get("message", "")
            self._send(200, answer(message))
        except Exception as exc:  # keep the API honest for the demo
            self._send(500, {"error": str(exc)})


if __name__ == "__main__":
    mode = "semantic (OpenAI embeddings)" if SEMANTIC else "keyword (FTS5)"
    print(f"faq-bot on http://localhost:{PORT}  |  mode: {mode}  |  faqs: {len(FAQS)}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()