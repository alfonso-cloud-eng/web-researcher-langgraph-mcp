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


async def run(url: str, question: str) -> str:
    from agent.mcp_client import get_mcp_client
    from agent.graph import build_graph

    print(f"\n🔍 Research Navigator starting...")
    print(f"   URL      : {url}")
    print(f"   Question : {question}\n")

    client = get_mcp_client()

    async with client:
        # Retrieve tools from MCP server
        tools = await client.get_tools()
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
        }

        config = {"configurable": {"thread_id": "session-1"}}

        final_state = None
        async for step in graph.astream(initial_state, config=config):
            node_name = list(step.keys())[0]
            node_output = step[node_name]
            loop = node_output.get("loop_count", "?")
            print(f"  [{node_name}] step={loop}", end="")
            if node_output.get("error_log"):
                print(f" ⚠️  {node_output['error_log']}", end="")
            if node_output.get("current_url"):
                print(f" → {node_output['current_url']}", end="")
            print()
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
