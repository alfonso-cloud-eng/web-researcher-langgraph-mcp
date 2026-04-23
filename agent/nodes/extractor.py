"""
Extractor node: calls get_page_context() on the MCP server and updates
the state with the latest DOM snapshot.
"""
import json
from agent.state import AgentState


def _extract_text(result) -> str:
    """Normalize MCP tool output to a plain string regardless of return format."""
    if isinstance(result, str):
        return result
    if isinstance(result, list):
        parts = []
        for item in result:
            if isinstance(item, dict):
                parts.append(item.get("text", json.dumps(item)))
            elif hasattr(item, "text"):
                parts.append(item.text)
            else:
                parts.append(str(item))
        return "\n".join(parts)
    if hasattr(result, "content"):
        return _extract_text(result.content)
    return str(result)


async def extractor_node(state: AgentState, tools: dict) -> dict:
    get_ctx = tools.get("get_page_context")
    if get_ctx is None:
        return {"error_log": "get_page_context tool not available"}

    try:
        raw = await get_ctx.ainvoke({})
        text = _extract_text(raw)
        result = json.loads(text)

        # Convert string keys to int (JSON keys are always strings)
        elements = {int(k): v for k, v in result.get("elements", {}).items()}

        return {
            "page_content_markdown": result.get("markdown", ""),
            "interactive_elements": elements,
            "error_log": None,
        }
    except Exception as exc:
        return {"error_log": f"Extractor failed: {exc}"}
