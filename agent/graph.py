"""Main LangGraph definition for world update system."""

from dotenv import load_dotenv
from langgraph.graph import StateGraph, START, END

from .state import OverallState
from .nodes.plan_reader import plan_reader
from .nodes.next_action import next_action
from .nodes.world_update import world_update


load_dotenv()


def should_continue(state: OverallState) -> str:
    """
    Determine if we should continue processing more actions.
    
    Returns:
        "continue" if there are remaining actions to process
        "end" if all actions are executed or execution failed
    """
    remaining_actions = state.get("remaining_actions", [])
    execution_status = state.get("execution_status")
    
    # Stop if execution failed
    if execution_status == "failed":
        return "end"
    
    # Continue if there are remaining actions
    if remaining_actions:
        return "continue"
    
    # Otherwise, end (all actions executed)
    return "end"


def build_workflow() -> StateGraph:
    """Build the workflow graph for world update system.
    
    Workflow:
    START → plan_reader → next_action → world_update → (continue/end)
    
    The workflow processes all actions in the plan:
    - Each action creates a new version of TTL files (dynamic_N.ttl, static_N.ttl)
    - Each action execution is logged to action/log/N.json
    - Continues until all actions are executed
    
    The plan_reader node:
    1. Reads solution.plan file from action/plan/ directory
    2. Parses PDDL actions from the plan
    3. Creates initial TTL files (dynamic_0.ttl, static_0.ttl) in action/world/
    4. Stores plan data in state for environment updates
    
    The next_action node:
    1. Extracts the next action from remaining_actions
    2. Stores as current_action
    3. Updates remaining_actions
    
    The world_update node:
    1. Parses current_action (e.g., move action)
    2. Updates TTL files (incremental versioning)
    3. Updates ontology via SPARQL UPDATE
    4. Saves execution log to action/log/N.json
    5. Updates executed_action_count
    """
    workflow = StateGraph(OverallState)

    # Add nodes
    workflow.add_node("plan_reader", plan_reader)
    workflow.add_node("next_action", next_action)
    workflow.add_node("world_update", world_update)

    # Workflow edges
    workflow.add_edge(START, "plan_reader")
    workflow.add_edge("plan_reader", "next_action")
    workflow.add_edge("next_action", "world_update")
    
    # Conditional edge: continue processing or end
    workflow.add_conditional_edges(
        "world_update",
        should_continue,
        {
            "continue": "next_action",  # Process next action
            "end": END  # Stop after 2 actions or no more actions
        }
    )

    return workflow


# Build and compile the graph
graph = build_workflow().compile()

print("LangGraph world update agent initialized successfully")