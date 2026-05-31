# GenAI Agents

A collection of AI agent projects built with modern LLM frameworks and orchestration tools.

## Projects

### [ganesh-agentops](./ganesh-agentops/)

**AI Agent Orchestration Platform for Payment Operations**

A production-grade multi-agent workflow platform that investigates payment failures, routes work through a configurable agent pipeline, and surfaces every step in a real-time dashboard. Optionally accepts queries from a Telegram bot.

| | |
|---|---|
| **Stack** | FastAPI · LangGraph · Next.js 14 · SQLite · Telegram |
| **Agents** | Support Intake → Payment Investigator → Risk & Compliance → Resolution |
| **Tests** | 226 passing · zero API keys required |
| **Demo** | One-click Payment Failure Investigation with live SSE event stream |

```bash
cd ganesh-agentops
cp .env.example .env
docker compose up --build
# Frontend: http://localhost:3000  ·  API: http://localhost:8000
```

→ [Full documentation](./ganesh-agentops/README.md)

---

*Ganesh Lande · ganeshlande@gmail.com*
