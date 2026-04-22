"""
Extractor node: calls get_page_context() on the MCP server and updates
the state with the latest DOM snapshot.
"""
from langchain_core.messages import ToolMessage
from agent.state import AgentState


async def extractor_node(state: AgentState, tools: dict) -> dict:
    get_ctx = tools.get("get_page_context")
    if get_ctx is None:
        return {"error_log": "get_page_context tool not available"}

    try:
        result = await get_ctx.ainvoke({})
        # result is a dict: {"markdown": "...", "elements": {1: {...}, ...}}
        if isinstance(result, str):
            import json
            result = json.loads(result)

        # Convert string keys to int (JSON keys are always strings)
        elements = {int(k): v for k, v in result.get("elements", {}).items()}

        return {
            "page_content_markdown": result.get("markdown", ""),
            "interactive_elements": elements,
            "error_log": None,
        }
    except Exception as exc:
        return {"error_log": f"Extractor failed: {exc}"}
