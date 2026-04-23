# Agent State

All state is defined in `agent/state.py` as a `TypedDict`. LangGraph persists and merges this dict between node calls. Every field listed here must be initialised in `main.py` before the graph starts.

```python
class AgentState(TypedDict):
    # Inputs
    question: str
    initial_url: str

    # Navigation
    current_url: str
    visited_urls: List[str]
    history: List[BaseMessage]
    reasoning_steps: List[str]

    # DOM snapshot (current page only — overwritten on every navigation)
    page_content_markdown: str
    interactive_elements: Dict[int, Dict[str, Any]]
    current_screenshot: Optional[str]

    # Notebook (persistent across all pages)
    notes: List[Dict[str, str]]

    # Per-turn trace (reset by Analyst each turn)
    last_turn_reasoning: Optional[str]
    last_turn_notes_added: int

    # Results & control
    proposed_answer: Optional[str]
    final_answer: Optional[str]
    error_log: Optional[str]
    loop_count: int
    next_action: Optional[str]
```

---

## Field reference

### Inputs

| Field | Type | Set by | Description |
|---|---|---|---|
| `question` | `str` | `main.py` (CLI arg) | The research question, unchanged for the entire run |
| `initial_url` | `str` | `main.py` (CLI arg) | The URL the browser navigated to before the graph started |

### Navigation

| Field | Type | Set by | Description |
|---|---|---|---|
| `current_url` | `str` | Navigator, Analyst | URL of the page currently in the browser |
| `visited_urls` | `List[str]` | Navigator, Analyst | All URLs visited during the run (deduplicated) |
| `history` | `List[BaseMessage]` | Analyst | Full LangChain message history: `HumanMessage`, `AIMessage`, `ToolMessage`. Passed to the LLM on every Analyst call. Grows throughout the run |
| `reasoning_steps` | `List[str]` | Analyst | Cumulative list of text snippets the LLM produced across turns (for audit/logging). Format: `"Step N: ..."` |

### DOM snapshot

These fields describe the **currently loaded page**. They are overwritten on every navigation (by the Navigator node calling the Extractor internally).

| Field | Type | Set by | Description |
|---|---|---|---|
| `page_content_markdown` | `str` | Extractor | Page body in Markdown, max 20 000 chars. Interactive elements appear as `[ID:N]` inline |
| `interactive_elements` | `Dict[int, Dict]` | Extractor | `{id: {type, text, selector}}` — the element map for the current page. IDs are reassigned fresh on every page load |
| `current_screenshot` | `Optional[str]` | — | Reserved for multimodal use; always `None` in current implementation |

> **Important:** `interactive_elements` IDs are ephemeral. They are valid only for the page that was loaded when `get_page_context` last ran. After any navigation, old IDs are meaningless. The Analyst must save URLs and titles to `notes` before navigating if it needs them later.

### Notebook

| Field | Type | Set by | Description |
|---|---|---|---|
| `notes` | `List[Dict[str, str]]` | Analyst (`save_note`) | Accumulated scratchpad. Each entry: `{"topic": str, "content": str, "source_url": str}`. Never overwritten — only appended. Survives across all page navigations |

### Per-turn trace

These fields are reset by the Analyst at the start of each turn and are used only by the logger in `main.py`.

| Field | Type | Description |
|---|---|---|
| `last_turn_reasoning` | `Optional[str]` | Reasoning text the LLM produced this turn. `None` if the model returned only tool calls with no text |
| `last_turn_notes_added` | `int` | Number of `save_note` calls made this turn. Used by the logger to show only the newly added notes |

### Results & control

| Field | Type | Set by | Description |
|---|---|---|---|
| `proposed_answer` | `Optional[str]` | Analyst | Answer produced by `submit_answer` (or plain text response). Reset to `None` after each Verifier rejection |
| `final_answer` | `Optional[str]` | Verifier | Set once the Verifier issues PASS. This is the value printed at the end |
| `error_log` | `Optional[str]` | Extractor, Analyst | Last error from a failed tool call. Shown in the prompt to the Analyst on the next turn |
| `loop_count` | `int` | Analyst | Incremented by 1 on every Analyst turn. When it exceeds `MAX_LOOPS` the graph terminates |
| `next_action` | `Optional[str]` | Analyst, Verifier | Routing signal. Valid values: `"act"`, `"noted"`, `"answer"`, `"give_up"`, `"pass"`, `"fail"` |

#### `next_action` routing table

| Value | Set by | Effect |
|---|---|---|
| `"act"` | Analyst | Routes to Navigator (browser tool was called) |
| `"noted"` | Analyst | Self-loop back to Analyst (only `save_note` was called) |
| `"answer"` | Analyst | Routes to Verifier |
| `"give_up"` | Analyst | Routes to END |
| `"pass"` | Verifier | Routes to END with `final_answer` set |
| `"fail"` | Verifier | Routes back to Analyst with feedback in `history` |
