"""Goal Validator Node - Validates goal formula for logical consistency and achievability."""

import re
import uuid
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
import sys
from pathlib import Path

# Add ontology_server to path for config access
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "ontology_server"))

from ..state import OverallState
from ..tools.ttl_reader import read_ttl_file, get_ttl_summary


def format_goal_formula(goal_formula: str) -> str:
    """
    Format goal formula for better readability.
    Each predicate is displayed on a separate line with proper indentation.
    
    Args:
        goal_formula: PDDL goal formula string
        
    Returns:
        Formatted goal formula string
    """
    # Remove extra whitespace
    goal_formula = goal_formula.strip()
    
    # If it starts with (and, format it nicely
    if goal_formula.startswith('(and'):
        # Extract the content inside (and ...)
        match = re.match(r'\(and\s+(.+)\)', goal_formula, re.DOTALL)
        if match:
            content = match.group(1).strip()
            # Split by parentheses to find individual predicates
            predicates = []
            depth = 0
            current = ""
            
            for char in content:
                current += char
                if char == '(':
                    depth += 1
                elif char == ')':
                    depth -= 1
                    if depth == 0:
                        predicates.append(current.strip())
                        current = ""
            
            # Format each predicate on a new line
            formatted = "(and\n"
            for pred in predicates:
                if pred:  # Skip empty strings
                    formatted += f"  {pred}\n"
            formatted = formatted.rstrip() + "\n)"
            return formatted
    
    # If not (and, return as is but with basic formatting
    return goal_formula


def goal_validator(state: OverallState, config: RunnableConfig) -> dict:
    """
    Validate the generated goal formula for:
    1. Logical consistency (no mutually exclusive predicates)
    2. Object availability (objects have known initial locations)
    3. Affordance compatibility (containers have PlaceIn, surfaces have PlaceOn)
    4. Robot location consistency (robot not in multiple locations)
    
    If goal is provided in state.goal, uses it directly (skips validation, goes straight to planning).
    
    Returns:
        State updates with validated goal_formula and pddl_plan tool call, or error message
    """
    try:
        # Check if goal was provided directly (skip validation, go straight to planning)
        initial_goal = state.get("goal")
        if initial_goal and initial_goal.strip():
            goal_formula = initial_goal.strip()
            
            # Format goal formula for better readability
            formatted_goal = format_goal_formula(goal_formula)
            
            # Create pddl_plan tool call directly (skip validation)
            tool_call_args = {"goal_formula": goal_formula}
            success_msg = f"Using provided goal formula:\n{formatted_goal}"
            
            tool_call_message = AIMessage(
                content=success_msg,
                tool_calls=[{
                    "name": "pddl_plan",
                    "args": tool_call_args,
                    "id": str(uuid.uuid4())
                }]
            )
            
            return {
                "messages": [tool_call_message],
                "validation_errors": None,
                "validation_passed": True  # Mark as passed to route to pddl_plan
            }
        
        # Otherwise use goal from user_instruction (from generator) - perform validation
        goal_formula = state.get("user_instruction", "")
        messages = state.get("messages", [])
        
        # Extract goal formula from messages if not in user_instruction
        if not goal_formula and messages:
            for msg in messages:
                if isinstance(msg, AIMessage) and msg.content:
                    # Try to extract goal formula from message
                    content = msg.content
                    if "(and" in content or content.strip().startswith("("):
                        # Extract PDDL expression
                        match = re.search(r'\(and[^)]*(?:\([^)]+\)[^)]*)*\)|\([^)]+\)', content, re.DOTALL)
                        if match:
                            goal_formula = match.group(0).strip()
                            break
        
        if not goal_formula:
            return {
                "messages": [AIMessage(
                    content="ERROR: No goal formula found to validate."
                )]
            }
        
        # Parse goal formula to extract predicates
        validation_errors = []
        validation_warnings = []
        
        # 1. Check for robot location contradictions
        robot_locations = re.findall(r'\(robotIsInSpace\s+robot1\s+(\w+)\)', goal_formula)
        if len(robot_locations) > 1:
            validation_errors.append(
                f"Robot location contradiction: Robot cannot be in multiple locations simultaneously "
                f"({', '.join(set(robot_locations))})"
            )
        
        # 2. Check for mutually exclusive predicates on same object
        # Extract all predicates with their objects
        predicates = re.findall(r'\((isHeldBy|isInSpace|isInsideOf|isOntopOf)\s+(\w+)\s+(\w+)\)', goal_formula)
        artifact_states = {}  # object_id -> list of (pred_type, arg2) tuples
        
        for pred_type, obj_id, arg2 in predicates:
            if obj_id not in artifact_states:
                artifact_states[obj_id] = []
            artifact_states[obj_id].append((pred_type, arg2))
        
        # Check for objects with multiple mutually exclusive predicates
        for obj_id, states in artifact_states.items():
            if len(states) > 1:
                # Check if any combination is mutually exclusive
                pred_types = [pred for pred, _ in states]
                
                # CRITICAL: Each artifact can have ONLY ONE state predicate
                # The following predicates are MUTUALLY EXCLUSIVE for the same artifact:
                # - isHeldBy (robot is holding the artifact)
                # - isInSpace (artifact is in a location)
                # - isInsideOf (artifact is inside a container)
                # - isOntopOf (artifact is on top of a surface)
                
                # isHeldBy is exclusive with all spatial predicates
                if "isHeldBy" in pred_types:
                    spatial_preds = [f"{pred}({arg})" for pred, arg in states if pred != "isHeldBy"]
                    if spatial_preds:
                        validation_errors.append(
                            f"CRITICAL: {obj_id} has conflicting state predicates. "
                            f"An artifact CANNOT be held by robot AND be in a spatial location simultaneously. "
                            f"Found predicates: isHeldBy + {', '.join(spatial_preds)}. "
                            f"Each artifact must have EXACTLY ONE state predicate: either isHeldBy, isInSpace, isInsideOf, or isOntopOf (NOT multiple)."
                        )
                
                # Spatial predicates are mutually exclusive with each other
                spatial_pred_types = [pred for pred in pred_types if pred in ["isInSpace", "isInsideOf", "isOntopOf"]]
                if len(spatial_pred_types) > 1:
                    spatial_preds = [f"{pred}({arg})" for pred, arg in states if pred in spatial_pred_types]
                    validation_errors.append(
                        f"CRITICAL: {obj_id} has multiple conflicting spatial state predicates. "
                        f"An artifact CANNOT be in multiple spatial states simultaneously. "
                        f"Found: {', '.join(spatial_preds)}. "
                        f"Each artifact must have EXACTLY ONE spatial predicate: either isInSpace, isInsideOf, or isOntopOf (NOT multiple)."
                    )
        
        # 3. Check object availability and affordances
        # Get TTL data
        from core.config import get_config
        from core.env import EnvManager
        
        config_obj = get_config()
        env_manager = EnvManager()
        active_env = config_obj.get_active_env()
        
        if active_env:
            ontology_server_root = project_root / "ontology_server"
            env_dir = ontology_server_root / "data" / "envs" / active_env
            dynamic_path = env_dir / "dynamic.ttl" if env_dir.exists() else None
            
            if dynamic_path and dynamic_path.exists():
                dynamic_data = read_ttl_file(dynamic_path)
                artifacts_dict = {obj['id']: obj for obj in dynamic_data['objects'] if obj['type'] == 'Artifact'}
                
                # Extract all artifact IDs from goal (excluding locations)
                artifact_ids = set()
                artifact_ids.update(artifact_states.keys())
                # Extract from single-argument predicates (isON, isOpen, isLocked)
                for match in re.finditer(r'\((isON|isOpen|isLocked)\s+(\w+)\)', goal_formula):
                    artifact_ids.add(match.group(2))
                # Extract from two-argument spatial predicates (both args are artifacts)
                for match in re.finditer(r'\((isInsideOf|isOntopOf)\s+(\w+)\s+(\w+)\)', goal_formula):
                    artifact_ids.add(match.group(2))  # First artifact
                    artifact_ids.add(match.group(3))  # Second artifact (container/surface)
                # Extract from isInSpace (first arg is artifact, second is location - skip second)
                for match in re.finditer(r'\(isInSpace\s+(\w+)\s+(\w+)\)', goal_formula):
                    artifact_ids.add(match.group(1))  # Artifact only
                # Extract from isAdjacentTo
                for match in re.finditer(r'\(isAdjacentTo\s+robot1\s+(\w+)\)', goal_formula):
                    artifact_ids.add(match.group(1))
                # Extract from Key-Safe predicates (both args are artifacts)
                for match in re.finditer(r'\((hasRequiredKey|unlocks)\s+(\w+)\s+(\w+)\)', goal_formula):
                    artifact_ids.add(match.group(2))
                    artifact_ids.add(match.group(3))
                
                # Check object existence (only artifacts, not locations)
                for artifact_id in artifact_ids:
                    if artifact_id not in artifacts_dict:
                        validation_errors.append(
                            f"Object {artifact_id} does not exist in the environment"
                        )
                
                # Check each artifact
                for artifact_id in artifact_ids:
                    if artifact_id not in artifacts_dict:
                        continue
                    
                    artifact = artifacts_dict[artifact_id]
                    
                    # Check if artifact has location (for isHeldBy, isInSpace, isInsideOf, isOntopOf)
                    if artifact_id in artifact_states:
                        if not artifact.get('location'):
                            validation_errors.append(
                                f"Object {artifact_id} has no known initial location, cannot be used in "
                                f"(isHeldBy ...) or (isInSpace ...)"
                            )
                    
                    # Check affordances for isInsideOf
                    is_inside_of = re.search(rf'\(isInsideOf\s+{artifact_id}\s+(\w+)\)', goal_formula)
                    if is_inside_of:
                        container_id = is_inside_of.group(1)
                        if container_id in artifacts_dict:
                            container = artifacts_dict[container_id]
                            if 'Affordance_PlaceIn' not in container.get('affordances', []):
                                validation_errors.append(
                                    f"Container {container_id} does not have Affordance_PlaceIn, "
                                    f"cannot place {artifact_id} inside it"
                                )
                    
                    # Check affordances for isOntopOf
                    is_ontop_of = re.search(rf'\(isOntopOf\s+{artifact_id}\s+(\w+)\)', goal_formula)
                    if is_ontop_of:
                        surface_id = is_ontop_of.group(1)
                        if surface_id in artifacts_dict:
                            surface = artifacts_dict[surface_id]
                            if 'Affordance_PlaceOn' not in surface.get('affordances', []):
                                validation_errors.append(
                                    f"Surface {surface_id} does not have Affordance_PlaceOn, "
                                    f"cannot place {artifact_id} on top of it"
                                )
                
                # Check isOpen and isInsideOf logical relationship
                # If container is closed (not isOpen), cannot place object inside
                for match in re.finditer(r'\(isInsideOf\s+(\w+)\s+(\w+)\)', goal_formula):
                    artifact_id = match.group(1)
                    container_id = match.group(2)
                    if container_id in artifacts_dict:
                        # Check if container is explicitly closed (not isOpen)
                        # Note: We check for explicit "not (isOpen ...)" pattern
                        container_closed = re.search(rf'\(not\s+\(isOpen\s+{re.escape(container_id)}\)\)', goal_formula)
                        if container_closed:
                            validation_errors.append(
                                f"Logical contradiction: Cannot place {artifact_id} inside closed container {container_id}. "
                                f"Container must be open (isOpen {container_id}) to place objects inside."
                            )
                        # Also check if isOpen is not present but container has Affordance_Open
                        # This is a warning case - container might need to be opened first
                        container = artifacts_dict[container_id]
                        if 'Affordance_Open' in container.get('affordances', []):
                            is_open = re.search(rf'\(isOpen\s+{re.escape(container_id)}\)', goal_formula)
                            if not is_open:
                                # This is a warning, not an error - container might be open initially
                                validation_warnings.append(
                                    f"Note: Container {container_id} has Affordance_Open. "
                                    f"Ensure it is open before placing {artifact_id} inside."
                                )
        
        # If validation errors, return error and store in state for feedback loop
        if validation_errors:
            generation_attempts = state.get("generation_attempts", 0)
            error_msg = f"Goal validation FAILED (attempt {generation_attempts}):\n\n" + "\n".join(f"  ❌ {err}" for err in validation_errors)
            if validation_warnings:
                error_msg += "\n\nWarnings:\n" + "\n".join(f"  ⚠️  {warn}" for warn in validation_warnings)
            error_msg += "\n\n🔄 Retrying goal generation with feedback..."
            return {
                "messages": [AIMessage(content=error_msg)],
                "validation_errors": validation_errors,
                "validation_passed": False
            }
        
        # Validation passed - create pddl_plan tool call
        tool_call_args = {"goal_formula": goal_formula}
        
        # Format goal formula for better readability
        formatted_goal = format_goal_formula(goal_formula)
        
        success_msg = "Goal validation PASSED ✓\n\n"
        if validation_warnings:
            success_msg += "Warnings:\n" + "\n".join(f"  ⚠️  {warn}" for warn in validation_warnings) + "\n\n"
        success_msg += f"Validated goal formula:\n{formatted_goal}"
        
        tool_call_message = AIMessage(
            content=success_msg,
            tool_calls=[{
                "name": "pddl_plan",
                "args": tool_call_args,
                "id": str(uuid.uuid4())
            }]
        )
        
        return {
            "messages": [tool_call_message],
            "validation_errors": None,
            "validation_passed": True
        }
        
    except Exception as e:
        error_msg = f"ERROR in goal_validator: {type(e).__name__}: {str(e)}"
        import traceback
        traceback.print_exc()
        return {
            "messages": [AIMessage(content=error_msg)]
        }

