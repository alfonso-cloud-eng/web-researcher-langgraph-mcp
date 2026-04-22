from typing import TypedDict, List, Dict, Any, Optional
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    # ── Inputs ────────────────────────────────────────────────────────────────
    question: str
    initial_url: str

    # ── Navigation & memory ───────────────────────────────────────────────────
    current_url: str
    visited_urls: List[str]
    history: List[BaseMessage]
    reasoning_steps: List[str]

    # ── Current DOM snapshot ──────────────────────────────────────────────────
    page_content_markdown: str
    # {1: {"type": "link", "text": "Docs", "selector": "[data-mcp-id='1']"}, ...}
    interactive_elements: Dict[int, Dict[str, Any]]
    current_screenshot: Optional[str]

    # ── Results & control ─────────────────────────────────────────────────────
    proposed_answer: Optional[str]
    final_answer: Optional[str]
    error_log: Optional[str]
    loop_count: int
