# Architecture

## What the system does

The Deep Research Navigator is an autonomous agent that answers research questions by controlling a real browser. Given a starting URL and a question, it navigates the web, reads pages, accumulates facts in a notebook, and synthesises a final answer — all without human intervention.

## Technology stack

| Layer | Technology |
|---|---|
| Orchestrator | Python + LangGraph (stateful cyclic graph) |
| Browser control | TypeScript + Playwright, exposed as an MCP server |
| Python–Node bridge | Model Context Protocol over STDIO (`langchain-mcp-adapters`) |
| LLM | Any OpenAI-compatible endpoint (configured via env vars) |

## Graph

The agent is a LangGraph `StateGraph` compiled with an in-memory checkpointer. All state is carried in a single `AgentState` TypedDict (see [state.md](state.md)).

```
START
  │
  ▼
Extractor ──────────────────────────────────────► Analyst
                                                      │
                              next_action = "noted"   │  next_action = "act"
                          ◄───────────────────────────┤
                          (self-loop)                 │
                                                      │  next_action = "answer"
                                                      ▼
                                                  Verifier
                                                      │
                                    next_action =     │  next_action =
                                    "pass"            │  "fail"
                                      │               │
                                      ▼               ▼
                                     END           Analyst
                                                  (re-loop)

  Any node: loop_count > MAX_LOOPS ──────────────► END
```

### Entry point

`main.py` connects the Python agent to the MCP browser server, navigates to the initial URL, and starts the graph with `graph.astream()`.

---

## Nodes

### Extractor

**File:** `agent/nodes/extractor.py`

Calls `get_page_context` on the MCP server and updates the state with the current DOM snapshot. This node runs once at the very start and is not called again directly — the Navigator node calls it internally after every navigation.

`get_page_context` returns:
- `page_content_markdown`: the page body converted to Markdown (max 20 000 chars), with every interactive element annotated as `[ID:N]`
- `elements`: a map of `{id: {type, text, selector}}` for every clickable element

### Analyst

**File:** `agent/nodes/analyst.py`

The LLM brain. On every turn it receives the full notebook and the current page, and must follow this mandatory protocol:

1. **Extract** — save any new relevant facts from the current page to the notebook via `save_note`
2. **Check** — if the notebook already contains enough to answer the question, call `submit_answer`
3. **Navigate** — if more information is needed, call a browser tool

The Analyst has two categories of tools:

**Local tools** (handled inside the node, no browser call):
- `save_note(topic, content)` — appends a note to `state.notes`
- `submit_answer(answer)` — sets `proposed_answer` and routes to the Verifier

**Browser tools** (forwarded to the MCP server, see [mcp-server.md](mcp-server.md)):
- `goto`, `click_element`, `type_text`, `press_key`, `scroll_down`, `scroll_up`, `go_back`

The Analyst sets `next_action` to signal the router:

| `next_action` | Meaning | Next node |
|---|---|---|
| `"act"` | A browser tool was called | Navigator |
| `"noted"` | Only `save_note` was called | Analyst (self-loop) |
| `"answer"` | `submit_answer` called or plain text returned | Verifier |
| `"give_up"` | Reserved, triggers END | END |

On the first turn (empty history) a seed `HumanMessage` is injected into `history` to satisfy providers that require at least one user message (e.g. Gemini).

### Navigator

**File:** `agent/nodes/navigator.py`

Runs after every browser tool call. It:
1. Calls `get_current_url` to update `state.current_url` and `state.visited_urls`
2. Calls `extractor_node` internally to refresh the DOM snapshot in the state

The Navigator does not call the LLM.

### Verifier

**File:** `agent/nodes/verifier.py`

An independent LLM judge. It receives the notebook and the proposed answer, and replies with a JSON verdict:

```json
{"verdict": "PASS" | "FAIL", "reason": "...", "feedback": "..."}
```

- **PASS** → writes `proposed_answer` to `final_answer` and ends the graph
- **FAIL** → injects a `[Verifier feedback]` `HumanMessage` into history and routes back to Analyst

Safety valve: after `MAX_VERIFIER_FAILS = 2` consecutive rejections, the verifier accepts regardless, to prevent infinite FAIL loops.

The verifier judges **against the notebook**, not against the live page or its own world knowledge. This prevents it from rejecting correct answers just because it cannot independently verify web facts.

---

## Notebook memory

The core architectural idea is that `page_content_markdown` is ephemeral — it is overwritten on every navigation — while `notes` is persistent and only grows. The Analyst is instructed to save all relevant facts to the notebook **before** navigating away, because element IDs and page content are lost the moment a new page loads.

This solves the multi-page research problem: answers that require visiting several URLs (e.g. "summarise each of the top 3 articles") are built up incrementally across turns, with each visited page contributing notes.

See [state.md](state.md) for the full field definitions.
