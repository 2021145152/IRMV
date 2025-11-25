from __future__ import annotations

from typing import List, Optional
from typing_extensions import TypedDict, Annotated

from langgraph.graph import add_messages


class OverallState(TypedDict, total=False):
    """State for world update system - reads plan and updates environment."""

    # Core LangGraph message management (required)
    messages: Annotated[List, add_messages]

    # Plan data (from solution.plan file)
    plan_actions: Optional[List[str]]  # List of PDDL action strings
    plan_cost: Optional[int]  # Plan cost if available
    plan_step_count: Optional[int]  # Number of actions in plan
    plan_raw_content: Optional[str]  # Raw plan file content
    
    # Action execution state
    current_action: Optional[str]  # Current action being executed
    remaining_actions: Optional[List[str]]  # Remaining actions to execute
    last_executed_action: Optional[str]  # Last successfully executed action
    execution_status: Optional[str]  # "success", "failed", etc.
    executed_action_count: Optional[int]  # Number of actions executed so far (default: 0)