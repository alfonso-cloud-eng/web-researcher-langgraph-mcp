"""
Verifier node: independent LLM judge that evaluates the proposed answer.
Returns PASS (sets final_answer) or FAIL (sends feedback back to Analyst).
"""
import os
import json
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from agent.state import AgentState
from agent.prompts import VERIFIER_SYSTEM
from agent.nodes.analyst import format_notes


MAX_VERIFIER_FAILS = 2


async def verifier_node(state: AgentState) -> dict:
    # Count prior rejections to break potential PASS/FAIL oscillations
    history = state.get("history", [])
    prior_fails = sum(
        1 for m in history
        if hasattr(m, "content") and isinstance(m.content, str) and m.content.startswith("[Verifier feedback]")
    )

    notes_section = format_notes(state.get("notes", []))

    system_prompt = VERIFIER_SYSTEM.format(
        question=state["question"],
        proposed_answer=state.get("proposed_answer", ""),
        notes_section=notes_section,
    )

    llm = ChatOpenAI(
        model=os.getenv("LLM_MODEL_ID", "google/gemma-4-31b-it:free"),
        openai_api_key=os.getenv("LLM_API_KEY"),
        openai_api_base=os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1"),
        temperature=0,
    )
    response = await llm.ainvoke([SystemMessage(content=system_prompt)])

    content = response.content if isinstance(response.content, str) else str(response.content)

    # Parse JSON verdict
    try:
        # Strip markdown code fences if present
        clean = content.strip().removeprefix("```json").removesuffix("```").strip()
        verdict_data = json.loads(clean)
    except json.JSONDecodeError:
        # If parsing fails, be conservative and pass
        verdict_data = {"verdict": "PASS", "reason": "Could not parse verifier response", "feedback": ""}

    verdict = verdict_data.get("verdict", "PASS")
    feedback = verdict_data.get("feedback", "")
    reason = verdict_data.get("reason", "")

    # Safety valve: if the verifier has already rejected MAX_VERIFIER_FAILS times,
    # accept the current proposal to avoid infinite rejection loops.
    if verdict != "PASS" and prior_fails >= MAX_VERIFIER_FAILS:
        return {
            "final_answer": state.get("proposed_answer", ""),
            "next_action": "pass",
        }

    if verdict == "PASS":
        return {
            "final_answer": state.get("proposed_answer", ""),
            "next_action": "pass",
        }
    else:
        # Inject feedback into history so Analyst sees it
        feedback_msg = HumanMessage(
            content=f"[Verifier feedback] Your answer was rejected.\nReason: {reason}\nGuidance: {feedback}\nPlease continue researching."
        )
        new_history = list(state.get("history", [])) + [feedback_msg]
        return {
            "history": new_history,
            "proposed_answer": None,
            "next_action": "fail",
        }
