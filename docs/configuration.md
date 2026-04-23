# Configuration & Setup

## Prerequisites

- Python 3.11+
- Node.js 18+
- An API key for an OpenAI-compatible LLM provider (OpenRouter, OpenAI, etc.)

---

## Installation

### 1. Python dependencies

```bash
pip install -r requirements.txt
```

### 2. Node dependencies & TypeScript build

```bash
cd mcp_browser_server
npm install
npm run build
```

### 3. Playwright browser binary (first time only)

```bash
npx playwright install chromium
```

### 4. Environment variables

```bash
cp .env.example .env
# edit .env with your values
```

---

## Environment variables

All variables are loaded from `.env` at startup via `python-dotenv`.

| Variable | Required | Default | Description |
|---|---|---|---|
| `LLM_API_KEY` | Yes | — | API key for the LLM provider |
| `LLM_BASE_URL` | Yes | — | Base URL of the OpenAI-compatible API endpoint |
| `LLM_MODEL_ID` | Yes | — | Model identifier string passed to the API |
| `MCP_SERVER_PATH` | No | `./mcp_browser_server/dist/index.js` | Path to the compiled MCP server entry point |
| `MAX_LOOPS` | No | `20` | Maximum number of Analyst turns before the graph force-terminates |

### Example `.env`

```env
LLM_API_KEY=sk-or-v1-...
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_MODEL_ID=minimax/minimax-m2-01

MCP_SERVER_PATH=./mcp_browser_server/dist/index.js
MAX_LOOPS=20
```

---

## Model selection

The agent uses a single model for both the Analyst and the Verifier nodes (configured by the three `LLM_*` variables). The provider must expose an OpenAI-compatible chat completions endpoint.

### Requirements for the model

- **Tool calling / function calling** support — mandatory. The Analyst calls `save_note`, `submit_answer`, and browser tools as structured tool calls.
- **Multi-turn conversation** — the full message history is sent on every Analyst turn.

### Tested models (via OpenRouter)

| Model | Tool use | Notes |
|---|---|---|
| `minimax/minimax-m2-01` | ✅ | Works well; follows the notebook protocol reliably |
| `google/gemini-2.0-flash-exp:free` | ✅ | Fast and free |
| `google/gemini-3.1-flash-lite` | ❌ | Requires `thought_signature` round-tripping not supported by the OpenAI-compat path |
| `openai/gpt-oss-120b:free` | ⚠️ | Does not reliably follow multi-step tool protocols |

### Using a different provider

Change `LLM_BASE_URL` and `LLM_API_KEY` accordingly. Any provider that speaks the OpenAI chat completions API with tool calling works without code changes.

---

## Running the agent

```bash
python -m agent.main \
  --url <starting-url> \
  --question "<research question>"
```

### Examples

```bash
# Simple single-page question
python -m agent.main \
  --url https://news.ycombinator.com \
  --question "What are the top 3 stories on Hacker News today?"

# Multi-page question requiring the notebook
python -m agent.main \
  --url https://news.ycombinator.com \
  --question "What are the top 3 stories on Hacker News today? Give me a summary of each."
```

The agent prints a structured log of every node turn to stdout. The final answer is printed between `===` separators at the end.

---

## Project structure

```
web-researcher-langgraph-mcp/
├── agent/
│   ├── main.py           # CLI entrypoint, MCP session management, logging
│   ├── graph.py          # LangGraph StateGraph assembly and routing
│   ├── state.py          # AgentState TypedDict
│   ├── mcp_client.py     # MultiServerMCPClient factory
│   ├── prompts.py        # System prompts for Analyst and Verifier
│   └── nodes/
│       ├── analyst.py    # LLM brain: notebook protocol, tool dispatch, routing
│       ├── extractor.py  # DOM snapshot via get_page_context
│       ├── navigator.py  # Post-navigation DOM refresh + URL tracking
│       └── verifier.py   # Independent answer judge
├── mcp_browser_server/
│   ├── src/
│   │   ├── browser.ts    # Playwright functions (one per MCP tool)
│   │   └── index.ts      # MCP server, tool registration, STDIO transport
│   ├── package.json
│   └── tsconfig.json
├── docs/                 # This documentation
├── requirements.txt
└── .env.example
```
