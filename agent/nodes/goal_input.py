"""Goal Input Node - Extracts goal_formula from input and calls pddl_plan."""

import uuid
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from ..state import OverallState


def goal_input(state: OverallState, config: RunnableConfig) -> dict:
    """Extract goal_formula from user input and prepare pddl_plan tool call.
    
    Expects goal_formula in:
    1. user_instruction field (direct goal formula)
    2. First human message content
    
    Returns:
        State updates with tool_call to pddl_plan
    """
    # Get goal_formula from various sources
    goal_formula = state.get("user_instruction", "")
    messages = state.get("messages", [])
    
    # If no goal_formula in user_instruction, check messages
    if not goal_formula and messages:
        for msg in messages:
            if isinstance(msg, HumanMessage) and msg.content:
                goal_formula = msg.content.strip()
                break
    
    if not goal_formula:
        return {
            "messages": [AIMessage(content="ERROR: No goal_formula provided. Please provide a PDDL goal formula (e.g., '(isON tv_52)')")]
        }
    
    # Create tool call to pddl_plan (task_description is auto-generated from goal_formula)
    tool_call_args = {"goal_formula": goal_formula}
    
    tool_call_message = AIMessage(
        content=f"Calling PDDL planner with goal: {goal_formula}",
        tool_calls=[{
            "name": "pddl_plan",
            "args": tool_call_args,
            "id": str(uuid.uuid4())
        }]
    )
    
    return {
        "messages": [tool_call_message]
    }
