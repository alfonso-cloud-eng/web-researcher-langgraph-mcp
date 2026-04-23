"""
Analyst node: the LLM brain. Reads the current page and decides the next action.
It either calls a browser tool (ACT), submits a proposed answer (ANSWER), or
returns a terminal signal (GIVE_UP).
"""
import os
import json
from typing import Literal
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from agent.state import AgentState
from agent.prompts import ANALYST_SYSTEM


def build_submit_answer_tool():
    @tool
    def submit_answer(answer: str) -> str:
        """Call this tool when you have found a complete answer to the research question."""
        return answer

    return submit_answer


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
        page_content=state.get("page_content_markdown", "(page not yet loaded)"),
    )

    messages = [SystemMessage(content=system_prompt)] + list(state.get("history", []))

    # All browser tools + submit_answer
    submit_tool = build_submit_answer_tool()
    all_tools = llm_tools + [submit_tool]

    llm = ChatOpenAI(
        model=os.getenv("LLM_MODEL_ID", "google/gemma-4-31b-it:free"),
        openai_api_key=os.getenv("LLM_API_KEY"),
        openai_api_base=os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1"),
        temperature=0,
    ).bind_tools(all_tools)

    response: AIMessage = await llm.ainvoke(messages)

    new_history = list(state.get("history", [])) + [response]
    new_steps = list(state.get("reasoning_steps", []))

    # Extract the agent's reasoning if present in text content
    if isinstance(response.content, str) and response.content.strip():
        new_steps.append(f"Step {state['loop_count']}: {response.content.strip()[:300]}")
    elif isinstance(response.content, list):
        text_parts = [c["text"] for c in response.content if isinstance(c, dict) and c.get("type") == "text"]
        if text_parts:
            new_steps.append(f"Step {state['loop_count']}: {' '.join(text_parts)[:300]}")

    updates: dict = {
        "history": new_history,
        "reasoning_steps": new_steps,
        "loop_count": state["loop_count"] + 1,
        "proposed_answer": None,
    }

    if not response.tool_calls:
        # LLM responded without a tool call — treat as GIVE_UP
        updates["proposed_answer"] = response.content if isinstance(response.content, str) else str(response.content)
        updates["_next"] = "give_up"
        return updates

    # Check each tool call
    for tc in response.tool_calls:
        tool_name = tc["name"]
        tool_args = tc["args"]

        if tool_name == "submit_answer":
            updates["proposed_answer"] = tool_args.get("answer", "")
            updates["_next"] = "answer"
            # Add a ToolMessage so the history stays valid
            new_history.append(ToolMessage(content=updates["proposed_answer"], tool_call_id=tc["id"]))
            updates["history"] = new_history
            return updates

        # Browser tool call — execute it
        browser_fn = browser_tools.get(tool_name)
        if browser_fn is None:
            tool_result = f"ERROR: Tool '{tool_name}' not found."
        else:
            try:
                raw = await browser_fn.ainvoke(tool_args)
                tool_result = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)
            except Exception as exc:
                tool_result = f"ERROR: {exc}"

        new_history.append(ToolMessage(content=tool_result, tool_call_id=tc["id"]))

        # Update URL if a navigation happened
        if "Current URL:" in tool_result:
            url_part = tool_result.split("Current URL:")[-1].strip()
            updates["current_url"] = url_part
            visited = list(state.get("visited_urls", []))
            if url_part not in visited:
                visited.append(url_part)
            updates["visited_urls"] = visited

    updates["history"] = new_history
    updates["_next"] = "act"
    return updates
