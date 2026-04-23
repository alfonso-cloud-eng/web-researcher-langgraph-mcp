"""
CLI entrypoint for the Deep Research Navigator.

Usage:
    python -m agent.main --url https://example.com --question "What is X?"
"""
import asyncio
import argparse
import os
import json
from dotenv import load_dotenv

load_dotenv()

DIVIDER = "─" * 60


def _print_step(node_name: str, output: dict) -> None:
    from langchain_core.messages import AIMessage, HumanMessage

    loop = output.get("loop_count", "?")
    icons = {"extractor": "📄", "analyst": "🧠", "navigator": "🌐", "verifier": "🔍"}
    icon = icons.get(node_name, "•")

    print(f"\n{DIVIDER}")
    print(f"{icon}  [{node_name.upper()}]  step {loop}")
    print(DIVIDER)

    if node_name == "extractor":
        md = output.get("page_content_markdown", "")
        n_elements = len(output.get("interactive_elements", {}))
        preview = md[:300].replace("\n", " ") if md else "(empty)"
        print(f"  Page snapshot: {preview}...")
        print(f"  Interactive elements found: {n_elements}")
        if output.get("error_log"):
            print(f"  ⚠️  {output['error_log']}")

    elif node_name == "analyst":
        # Reasoning text from THIS turn only (None if model only returned tool_calls)
        reasoning = output.get("last_turn_reasoning")
        if reasoning:
            # wrap long text nicely
            print(f"  💭 Reasoning: {reasoning[:400]}{'...' if len(reasoning) > 400 else ''}")

        # Show what tools were called in this turn, and preview the notes that were saved
        history = output.get("history", [])
        all_notes = output.get("notes", [])
        notes_added = output.get("last_turn_notes_added", 0)
        new_notes = all_notes[-notes_added:] if notes_added else []
        save_note_idx = 0

        for msg in reversed(history):
            if isinstance(msg, AIMessage) and msg.tool_calls:
                for tc in msg.tool_calls:
                    if tc["name"] == "save_note":
                        topic = tc["args"].get("topic", "(untitled)")
                        # Find the matching saved note to show content preview
                        preview = ""
                        if save_note_idx < len(new_notes):
                            content = new_notes[save_note_idx].get("content", "")
                            preview = content[:180] + ("..." if len(content) > 180 else "")
                            save_note_idx += 1
                        print(f"  📝 save_note [{topic}]")
                        if preview:
                            print(f"       └─ {preview}")
                    elif tc["name"] == "submit_answer":
                        print(f"  ✨ submit_answer()")
                    else:
                        args_str = json.dumps(tc["args"], ensure_ascii=False)
                        print(f"  🔧 {tc['name']}({args_str})")
                break
            if isinstance(msg, AIMessage):
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                print(f"  Decision (plain text): {content[:200]}")
                break

        if all_notes:
            delta = f" (+{notes_added} new)" if notes_added else ""
            print(f"  📔 Notebook: {len(all_notes)} total{delta}")

        if output.get("proposed_answer"):
            print(f"  Proposed answer: {output['proposed_answer'][:200]}")

    elif node_name == "navigator":
        url = output.get("current_url", "unknown")
        print(f"  Now at: {url}")
        if output.get("error_log"):
            print(f"  ⚠️  {output['error_log']}")

    elif node_name == "verifier":
        if output.get("final_answer"):
            print(f"  Verdict: PASS ✅")
            print(f"  Answer accepted.")
        else:
            history = output.get("history", [])
            for msg in reversed(history):
                if isinstance(msg, HumanMessage) and "[Verifier feedback]" in (msg.content or ""):
                    print(f"  Verdict: FAIL ❌")
                    print(f"  {msg.content[:300]}")
                    break


async def run(url: str, question: str) -> str:
    from agent.mcp_client import get_mcp_client
    from agent.graph import build_graph

    print(f"\n🔍 Research Navigator starting...")
    print(f"   URL      : {url}")
    print(f"   Question : {question}\n")

    client = get_mcp_client()

    # Use a persistent session so a single Node process (and browser) is shared
    # across all tool calls throughout the agent run.
    from langchain_mcp_adapters.tools import load_mcp_tools
    async with client.session("browser") as session:
        tools = await load_mcp_tools(session)
        tools_by_name = {t.name: t for t in tools}

        print(f"✅ MCP server connected. Tools available: {list(tools_by_name.keys())}\n")

        # Navigate to the initial URL before the graph starts
        goto_tool = tools_by_name.get("goto")
        if goto_tool:
            await goto_tool.ainvoke({"url": url})

        # Build and run the graph
        graph = build_graph(tools_by_name, tools)

        initial_state = {
            "question": question,
            "initial_url": url,
            "current_url": url,
            "visited_urls": [url],
            "history": [],
            "reasoning_steps": [],
            "page_content_markdown": "",
            "interactive_elements": {},
            "current_screenshot": None,
            "proposed_answer": None,
            "final_answer": None,
            "error_log": None,
            "loop_count": 0,
            "next_action": None,
            "notes": [],
            "last_turn_reasoning": None,
            "last_turn_notes_added": 0,
        }

        config = {"configurable": {"thread_id": "session-1"}}

        final_state = None
        async for step in graph.astream(initial_state, config=config):
            node_name = list(step.keys())[0]
            node_output = step[node_name]
            _print_step(node_name, node_output)
            final_state = node_output

        answer = (final_state or {}).get("final_answer") or (final_state or {}).get("proposed_answer") or "No answer found."

        print(f"\n{'='*60}")
        print("FINAL ANSWER")
        print('='*60)
        print(answer)
        print('='*60)

        return answer


def main():
    parser = argparse.ArgumentParser(description="Deep Research Navigator Agent")
    parser.add_argument("--url", required=True, help="Starting URL for research")
    parser.add_argument("--question", required=True, help="Research question to answer")
    args = parser.parse_args()

    asyncio.run(run(args.url, args.question))


if __name__ == "__main__":
    main()
