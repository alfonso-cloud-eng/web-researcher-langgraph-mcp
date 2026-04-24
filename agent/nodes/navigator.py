"""
Navigator node: after the Analyst calls a browser tool, this node refreshes
the page context, updates the URL bookkeeping, and detects semantic loops
(returning to a URL without making progress since the last visit).
"""
from langchain_core.messages import HumanMessage
from agent.state import AgentState
from agent.nodes.extractor import extractor_node, _extract_text


async def navigator_node(state: AgentState, tools: dict) -> dict:
    updates: dict = {}

    # Fetch the latest URL from the browser
    get_url = tools.get("get_current_url")
    new_url = state.get("current_url", "")
    if get_url:
        try:
            raw = await get_url.ainvoke({})
            new_url = _extract_text(raw).strip()
        except Exception:
            pass

    visited = list(state.get("visited_urls", []))
    if new_url and new_url not in visited:
        visited.append(new_url)

    # ── Semantic loop detection ───────────────────────────────────────────────
    # If we've already been on this URL and the notebook hasn't grown since
    # the previous visit, we're going in circles. Inject a notice so the
    # Analyst sees it on its next turn.
    visit_log = list(state.get("visit_log", []))
    notes_count_now = len(state.get("notes", []))

    prior_visits = [v for v in visit_log if v.get("url") == new_url]
    loop_notice = None
    if prior_visits:
        last_count = prior_visits[-1].get("notes_count", 0)
        if notes_count_now <= last_count:
            loop_notice = (
                f"[System notice] You have returned to {new_url} without adding "
                f"any new notes since the previous visit. Either try a different "
                f"approach (visit a new URL, or extract new facts from a page you "
                f"haven't fully read yet) or call submit_answer with the information "
                f"already in your notebook."
            )

    visit_log.append({"url": new_url, "notes_count": notes_count_now})
    updates["current_url"] = new_url
    updates["visited_urls"] = visited
    updates["visit_log"] = visit_log

    if loop_notice:
        new_history = list(state.get("history", [])) + [HumanMessage(content=loop_notice)]
        updates["history"] = new_history

    # Refresh the DOM snapshot after navigation
    dom_update = await extractor_node(state, tools)
    updates.update(dom_update)

    return updates
