"""
Analyst node: the LLM brain. Reads the notebook + current page and decides the next action.
Possible outcomes per turn:
  - ACT       : called a browser tool → route to Navigator (DOM refresh)
  - NOTED     : only saved notes (no navigation) → self-loop back to Analyst
  - ANSWER    : called submit_answer OR produced plain text → route to Verifier
  - GIVE_UP   : (reserved for future use)
"""
import os
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from agent.state import AgentState
from agent.prompts import ANALYST_SYSTEM
from agent.nodes.extractor import _extract_text


def format_notes(notes: list) -> str:
    if not notes:
        return "[Empty — you haven't taken any notes yet.]"
    lines = []
    for i, n in enumerate(notes, 1):
        lines.append(f"  [{i}] topic: {n.get('topic', '(untitled)')}")
        lines.append(f"      content: {n.get('content', '')}")
        src = n.get("source_url")
        if src:
            lines.append(f"      source: {src}")
    return "\n".join(lines)


def build_local_tools():
    @tool
    def submit_answer(answer: str) -> str:
        """Call this tool ONLY when your notebook contains enough information to fully answer
        the research question. The answer must synthesize the facts already in your notebook."""
        return answer

    @tool
    def save_note(topic: str, content: str) -> str:
        """Save a fact from the current page to your research notebook. Use a short, descriptive
        topic and concise content. Write only what is necessary to answer the user's question.
        You can call this multiple times in one turn, and you can combine it with a navigation
        tool call in the same response."""
        return f"Saved note: [{topic}]"

    return submit_answer, save_note


async def analyst_node(state: AgentState, llm_tools: list, browser_tools: dict) -> dict:
    max_loops = int(os.getenv("MAX_LOOPS", "20"))

    error_context = ""
    if state.get("error_log"):
        error_context = f"⚠️ Last action failed: {state['error_log']}\nPlease try a different approach.\n\n"

    system_prompt = ANALYST_SYSTEM.format(
        question=state["question"],
        current_url=state.get("current_url", state["initial_url"]),
        loop_count=state["loop_count"],
        max_loops=max_loops,
        error_context=error_context,
        notes_section=format_notes(state.get("notes", [])),
        page_content=state.get("page_content_markdown", "(page not yet loaded)"),
    )

    history = list(state.get("history", []))

    # Gemini and some other providers require at least one user message in the request.
    # If the history is empty (first turn), seed it with a HumanMessage to kick things off.
    if not history:
        history.append(HumanMessage(content=f"Please start researching to answer: {state['question']}"))

    messages = [SystemMessage(content=system_prompt)] + history

    submit_tool, save_note_tool = build_local_tools()
    all_tools = llm_tools + [submit_tool, save_note_tool]

    llm = ChatOpenAI(
        model=os.getenv("LLM_MODEL_ID", "google/gemma-4-31b-it:free"),
        openai_api_key=os.getenv("LLM_API_KEY"),
        openai_api_base=os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1"),
        temperature=0,
    ).bind_tools(all_tools)

    response: AIMessage = await llm.ainvoke(messages)

    # Preserve any seeded HumanMessage in the persisted history
    new_history = list(history) + [response]

    # Extract any new reasoning text the LLM produced this turn
    turn_reasoning = None
    if isinstance(response.content, str) and response.content.strip():
        turn_reasoning = response.content.strip()
    elif isinstance(response.content, list):
        text_parts = [c["text"] for c in response.content if isinstance(c, dict) and c.get("type") == "text"]
        if text_parts:
            turn_reasoning = " ".join(text_parts).strip()

    notes = list(state.get("notes", []))
    updates: dict = {
        "history": new_history,
        "loop_count": state["loop_count"] + 1,
        "proposed_answer": None,
        "notes": notes,  # will be mutated in-place below
        "last_turn_reasoning": turn_reasoning,  # None if model only returned tool_calls
        "last_turn_notes_added": 0,  # will be incremented below if save_notes happen
    }

    if not response.tool_calls:
        # Model replied with plain text → treat as proposed answer
        updates["proposed_answer"] = response.content if isinstance(response.content, str) else str(response.content)
        updates["next_action"] = "answer"
        return updates

    browser_call_made = False
    notes_added = 0

    for tc in response.tool_calls:
        tool_name = tc["name"]
        tool_args = tc["args"]

        if tool_name == "submit_answer":
            updates["proposed_answer"] = tool_args.get("answer", "")
            updates["next_action"] = "answer"
            new_history.append(ToolMessage(content=updates["proposed_answer"], tool_call_id=tc["id"]))
            updates["history"] = new_history
            return updates

        if tool_name == "save_note":
            topic = tool_args.get("topic", "(untitled)")
            content = tool_args.get("content", "")
            source = state.get("current_url", "")
            notes.append({"topic": topic, "content": content, "source_url": source})
            notes_added += 1
            updates["last_turn_notes_added"] = notes_added
            new_history.append(ToolMessage(content=f"Saved note: [{topic}]", tool_call_id=tc["id"]))
            continue

        # Browser tool call — execute it
        browser_call_made = True
        browser_fn = browser_tools.get(tool_name)
        if browser_fn is None:
            tool_result = f"ERROR: Tool '{tool_name}' not found."
        else:
            try:
                raw = await browser_fn.ainvoke(tool_args)
                tool_result = _extract_text(raw)
            except Exception as exc:
                tool_result = f"ERROR: {exc}"

        new_history.append(ToolMessage(content=tool_result, tool_call_id=tc["id"]))

        if "Current URL:" in tool_result:
            url_part = tool_result.split("Current URL:")[-1].strip()
            updates["current_url"] = url_part
            visited = list(state.get("visited_urls", []))
            if url_part not in visited:
                visited.append(url_part)
            updates["visited_urls"] = visited

    updates["history"] = new_history
    updates["notes"] = notes

    # Route:
    # - if any browser tool was called → navigator (refresh DOM)
    # - else (only save_notes) → self-loop to analyst to keep thinking
    updates["next_action"] = "act" if browser_call_made else "noted"
    return updates
