# FAQ Bot — portfolio piece #1

A deployable FAQ chatbot for small businesses: keyword + semantics retrieval,
chat UI included, ZERO pip dependencies (pure Python stdlib). Built to be the
first thing you show a client.

## Run it

    cd freelance/portfolio/faq-bot
    python3 server.py          # -> http://localhost:8000

Test:

    curl -X POST localhost:8000/api/chat \
      -H 'Content-Type: application/json' \
      -d '{"message":"how long does shipping take?"}'

Output: {reply, matched, confidence}. Unknown questions get a graceful
fallback with a human-contact handoff.

## Upgrade to real semantic search (2 minutes)

    export OPENAI_API_KEY=sk-...     # then restart
    python3 server.py

On first start it embeds all FAQs (OpenAI text-embedding-3-small, cached in
faqs_emb.json) and retrieval becomes vector-similarity instead of keywords.
Cost: pennies for a 20-question FAQ.

## Make it yours

- Edit faqs.json — same shape: [{category, q, a}]. Any business: plumbing,
  SaaS, clinic, law firm, coffee shop. ~15-25 Q&As is plenty.
- Delete faqs_emb.json if you change the FAQ content.
- The chat UI theme/brand text live at the top of server.py (PAGE string).

## Deploy it live in one click (free)

Repo: https://github.com/code-khodeir/faq-bot-demo

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/code-khodeir/faq-bot-demo)

Click the button, connect the repo in the Render dialog, and the bot goes
live with a public URL in ~2 minutes (S0 plan = free forever, no card).

Other options:

- Render/Railway free tier: new web service, start command `python3 server.py`,
  env PORT is set automatically. 10 minutes.
- PythonAnywhere: upload, run as a web app with a WSGI shim.
- Client's own VPS: scp the folder, run with systemd. One-liner service file
  in this folder if needed.

## Why this wins clients

- It answers the exact job posts people are paying $300-700 for today
  ("train a chatbot on our FAQs and embed it on our website" style gigs).
- Works offline, no API keys needed for the demo, no install friction.
- The "matched" line under each answer builds trust — prospects can see the
  bot is grounded, not hallucinating.
- Show the OPENAI_API_KEY upgrade live: "2 minutes to semantic search."

## Next portfolio pieces (in order of market value)

1. This bot, branded for a real niche + demo video (60s) — done next
2. An n8n/API lead-capture automation (form -> CRM -> AI follow-up email)
3. A browser-automation script (one clean, safe use case: report scraping)
4. An AI receptionist / call-handler prototype using a TTS/STT provider