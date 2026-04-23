"""
Assembles the LangGraph StateGraph for the Deep Research Navigator.
"""
import os
from typing import Literal
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from agent.state import AgentState
from agent.nodes.extractor import extractor_node
from agent.nodes.analyst import analyst_node
from agent.nodes.navigator import navigator_node
from agent.nodes.verifier import verifier_node


def build_graph(tools_by_name: dict, llm_tools: list) -> StateGraph:
    """
    tools_by_name: dict mapping tool name -> LangChain BaseTool (from MCP)
    llm_tools: list of BaseTool objects to bind to the LLM
    """
    max_loops = int(os.getenv("MAX_LOOPS", "20"))

    # ── Node wrappers (inject dependencies via closure) ───────────────────────

    async def _extractor(state: AgentState) -> dict:
        return await extractor_node(state, tools_by_name)

    async def _analyst(state: AgentState) -> dict:
        return await analyst_node(state, llm_tools, tools_by_name)

    async def _navigator(state: AgentState) -> dict:
        return await navigator_node(state, tools_by_name)

    async def _verifier(state: AgentState) -> dict:
        return await verifier_node(state)

    # ── Routing functions ─────────────────────────────────────────────────────

    def route_analyst(state: AgentState) -> Literal["navigator", "verifier", "analyst", "__end__"]:
        if state["loop_count"] > max_loops:
            return "__end__"
        next_action = state.get("next_action", "act")
        if next_action == "answer":
            return "verifier"
        if next_action == "give_up":
            return "__end__"
        if next_action == "noted":
            return "analyst"  # self-loop: only save_notes were called, keep thinking
        return "navigator"

    def route_verifier(state: AgentState) -> Literal["analyst", "__end__"]:
        return "__end__" if state.get("next_action") == "pass" else "analyst"

    # ── Graph assembly ────────────────────────────────────────────────────────

    graph = StateGraph(AgentState)

    graph.add_node("extractor", _extractor)
    graph.add_node("analyst", _analyst)
    graph.add_node("navigator", _navigator)
    graph.add_node("verifier", _verifier)

    graph.set_entry_point("extractor")

    graph.add_edge("extractor", "analyst")
    graph.add_conditional_edges("analyst", route_analyst, {
        "navigator": "navigator",
        "verifier": "verifier",
        "analyst": "analyst",  # self-loop for save_note-only turns
        "__end__": END,
    })
    graph.add_edge("navigator", "analyst")
    graph.add_conditional_edges("verifier", route_verifier, {
        "analyst": "analyst",
        "__end__": END,
    })

    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)
