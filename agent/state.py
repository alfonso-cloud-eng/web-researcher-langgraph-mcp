from typing import TypedDict, List, Dict, Any, Optional
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    # ── Inputs ────────────────────────────────────────────────────────────────
    question: str
    initial_url: str

    # ── Navigation & memory ───────────────────────────────────────────────────
    current_url: str
    visited_urls: List[str]
    # Ordered log of every navigation: [{"url": str, "notes_count": int}]
    # Used to detect semantic loops (returning to a URL without progress).
    visit_log: List[Dict[str, Any]]
    history: List[BaseMessage]

    # ── Current DOM snapshot ──────────────────────────────────────────────────
    page_content_markdown: str
    # {1: {"type": "link", "text": "Docs", "selector": "[data-mcp-id='1']"}, ...}
    interactive_elements: Dict[int, Dict[str, Any]]

    # ── Notebook (accumulated scratchpad across pages) ────────────────────────
    # each note: {"topic": str, "content": str, "source_url": str}
    notes: List[Dict[str, str]]

    # ── Per-turn trace (used for logging / UI, reset every Analyst turn) ──────
    last_turn_reasoning: Optional[str]
    last_turn_notes_added: int

    # ── Results & control ─────────────────────────────────────────────────────
    proposed_answer: Optional[str]
    final_answer: Optional[str]
    error_log: Optional[str]
    loop_count: int
    next_action: Optional[str]  # "act" | "noted" | "answer" | "give_up" | "pass" | "fail"
