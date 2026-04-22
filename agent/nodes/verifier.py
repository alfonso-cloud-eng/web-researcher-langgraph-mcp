"""
Verifier node: independent LLM judge that evaluates the proposed answer.
Returns PASS (sets final_answer) or FAIL (sends feedback back to Analyst).
"""
import json
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_anthropic import ChatAnthropic
from agent.state import AgentState
from agent.prompts import VERIFIER_SYSTEM


async def verifier_node(state: AgentState) -> dict:
    system_prompt = VERIFIER_SYSTEM.format(
        question=state["question"],
        proposed_answer=state.get("proposed_answer", ""),
        reasoning_steps="\n".join(state.get("reasoning_steps", [])),
    )

    llm = ChatAnthropic(model="claude-haiku-4-5-20251001", temperature=0)
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

    if verdict == "PASS":
        return {
            "final_answer": state.get("proposed_answer", ""),
            "_next": "pass",
        }
    else:
        # Inject feedback into history so Analyst sees it
        from langchain_core.messages import HumanMessage
        feedback_msg = HumanMessage(
            content=f"[Verifier feedback] Your answer was rejected.\nReason: {reason}\nGuidance: {feedback}\nPlease continue researching."
        )
        new_history = list(state.get("history", [])) + [feedback_msg]
        return {
            "history": new_history,
            "proposed_answer": None,
            "_next": "fail",
        }
