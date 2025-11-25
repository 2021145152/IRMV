"""Next Action Node - Extracts the first action from the plan to execute."""

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from ..state import OverallState


def next_action(state: OverallState, config: RunnableConfig) -> dict:
    """
    Extract the first action from the plan to execute.
    
    Workflow:
    1. Get plan_actions from state
    2. Extract first action
    3. Store as current_action
    4. Store remaining actions (excluding first one)
    
    Returns:
        State updates with current_action and remaining_actions
    """
    try:
        plan_actions = state.get("plan_actions", [])
        remaining_actions = state.get("remaining_actions")
        
        # If no remaining_actions in state, use plan_actions (first call)
        if remaining_actions is None:
            remaining_actions = plan_actions
        
        if not plan_actions and not remaining_actions:
            error_msg = "ERROR: No actions found in plan. Please ensure plan_reader has loaded the plan."
            return {
                "messages": [AIMessage(content=error_msg)]
            }
        
        # Extract first action from remaining actions
        if not remaining_actions:
            error_msg = "ERROR: No actions remaining to execute."
            return {
                "messages": [AIMessage(content=error_msg)],
                "current_action": None,
                "remaining_actions": []
            }
        
        current_action = remaining_actions[0]
        new_remaining_actions = remaining_actions[1:]  # All actions except the first one
        
        # Create success message
        success_msg = f"Next action to execute:\n"
        success_msg += f"  {current_action}\n\n"
        success_msg += f"Remaining actions: {len(remaining_actions)}\n"
        if remaining_actions:
            success_msg += f"Next actions:\n"
            for i, action in enumerate(remaining_actions[:5], 1):  # Show first 5
                success_msg += f"  {i}. {action}\n"
            if len(remaining_actions) > 5:
                success_msg += f"  ... and {len(remaining_actions) - 5} more\n"
        
        return {
            "messages": [AIMessage(content=success_msg)],
            "current_action": current_action,
            "remaining_actions": new_remaining_actions
        }
        
    except Exception as e:
        error_msg = f"ERROR in next_action: {type(e).__name__}: {str(e)}"
        import traceback
        traceback.print_exc()
        return {
            "messages": [AIMessage(content=error_msg)]
        }

