"""
Navigator node: after the Analyst calls a browser tool, we need to
refresh the page context. This node calls get_page_context and updates
current_url.
"""
from agent.state import AgentState
from agent.nodes.extractor import extractor_node, _extract_text


async def navigator_node(state: AgentState, tools: dict) -> dict:
    # Fetch latest URL
    get_url = tools.get("get_current_url")
    url_update = {}
    if get_url:
        try:
            raw = await get_url.ainvoke({})
            url = _extract_text(raw).strip()
            visited = list(state.get("visited_urls", []))
            if url not in visited:
                visited.append(url)
            url_update = {"current_url": url, "visited_urls": visited}
        except Exception:
            pass

    # Re-extract the page after navigation
    dom_update = await extractor_node(state, tools)

    return {**url_update, **dom_update}
