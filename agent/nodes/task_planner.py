"""Task Planner Node - Generates PDDL goals and validates plans."""

import uuid
from typing import Literal
from pydantic import BaseModel, Field
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI

from ..state import OverallState, SystemStatus
from ..config import Configuration
from ..prompts import task_planner_prompt


class PlanningDecision(BaseModel):
    """Structured decision from task planner."""

    action: Literal["call_pddl_plan", "finish"] = Field(
        description="Next action to take"
    )
    reasoning: str = Field(
        description="Explanation of this decision"
    )
    pddl_goal: str = Field(
        default="",
        description="If calling pddl_plan, the PDDL goal formula"
    )
    task_description: str = Field(
        default="",
        description="Brief task description for filename (e.g., 'turnOnTV', 'moveCupToKitchen')"
    )


def task_planner(state: OverallState, config: RunnableConfig) -> dict:
    """Generate PDDL goal and manage planning process.

    Decides whether to:
    1. Call pddl_plan tool with a PDDL goal formula
    2. Finish after reviewing planning results

    Returns:
        State updates with routing decision
    """
    cfg = Configuration.from_runnable_config(config)

    # Initialize LLM with structured output
    llm = ChatOpenAI(
        model=cfg.task_planner_model,
        temperature=cfg.temperature
    )
    llm_with_structure = llm.with_structured_output(PlanningDecision)

    # Get user instruction and messages
    user_instruction = state.get("user_instruction", "")
    messages = state.get("messages", [])
    planning_context = state.get("next_agent_context", "")

    # Build context from user instruction or planning context
    if not planning_context:
        if user_instruction:
            planning_context = f"User instruction: {user_instruction}"
        elif messages:
            # Get last user message if available
            user_messages = [msg for msg in messages if hasattr(msg, 'content') and msg.content]
            if user_messages:
                planning_context = user_messages[-1].content
            else:
                planning_context = "Please provide a task instruction."
        else:
            planning_context = "Please provide a task instruction."

    # Prepare messages for LLM
    planning_messages = [
        SystemMessage(content=task_planner_prompt),
        HumanMessage(content=planning_context)
    ]

    # Add conversation history (including tool results)
    planning_messages.extend(messages)

    try:
        decision = llm_with_structure.invoke(planning_messages)
    except Exception as e:
        return {
            "messages": [AIMessage(content=f"Error in planning: {e}")],
            "system_status": SystemStatus.FAILED,
            "current_agent": "task_planner"
        }

    # Create response message
    response_message = AIMessage(
        content=f"Planning decision: {decision.reasoning}\nAction: {decision.action}"
    )

    # Route based on decision
    if decision.action == "call_pddl_plan":
        # Create AIMessage with tool_calls to invoke pddl_plan tool
        tool_call_args = {"goal_formula": decision.pddl_goal}
        if decision.task_description:
            tool_call_args["task_description"] = decision.task_description

        tool_call_message = AIMessage(
            content=f"Calling PDDL planner with goal: {decision.pddl_goal}",
            tool_calls=[{
                "name": "pddl_plan",
                "args": tool_call_args,
                "id": str(uuid.uuid4())
            }]
        )
        return {
            "messages": [tool_call_message],
            "current_agent": "task_planner",
            "system_status": SystemStatus.PLANNING
        }

    else:  # finish
        return {
            "messages": [response_message],
            "system_status": SystemStatus.COMPLETED,
            "current_agent": "task_planner"
        }
