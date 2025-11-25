"""Plan Reader Node - Reads PDDL plan from solution.plan file."""

import re
import sys
from pathlib import Path
from typing import List, Dict, Any
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

# Add ontology_server to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "ontology_server"))

from ..state import OverallState
from core.config import get_config


def parse_plan_file(plan_path: Path) -> Dict[str, Any]:
    """
    Parse PDDL plan file and extract actions.
    
    Args:
        plan_path: Path to solution.plan file
        
    Returns:
        Dictionary with:
            - actions: List of action strings
            - cost: Plan cost (if available)
            - step_count: Number of actions
    """
    if not plan_path.exists():
        raise FileNotFoundError(f"Plan file not found: {plan_path}")
    
    with open(plan_path, 'r') as f:
        content = f.read()
    
    # Extract actions (lines starting with '(' and not comments)
    actions = []
    cost = None
    step_count = 0
    
    for line in content.split('\n'):
        line = line.strip()
        
        # Skip empty lines and comments
        if not line or line.startswith(';'):
            # Try to extract cost from comment
            if 'cost' in line.lower():
                cost_match = re.search(r'cost\s*=\s*(\d+)', line, re.IGNORECASE)
                if cost_match:
                    cost = int(cost_match.group(1))
            continue
        
        # Extract action (PDDL action format: (action_name arg1 arg2 ...))
        if line.startswith('(') and line.endswith(')'):
            actions.append(line)
            step_count += 1
    
    return {
        "actions": actions,
        "cost": cost,
        "step_count": step_count,
        "raw_content": content
    }


def plan_reader(state: OverallState, config: RunnableConfig) -> dict:
    """
    Read PDDL plan from solution.plan file and create initial TTL files.
    
    Workflow:
    1. Read solution.plan file from action/plan/ directory
    2. Parse actions from the plan
    3. Create initial TTL files (dynamic_0.ttl, static_0.ttl) in action/world/
    4. Store plan data in state
    
    Returns:
        State updates with plan data
    """
    try:
        # Get project root
        project_root = Path(__file__).parent.parent.parent
        plan_path = project_root / "action" / "plan" / "solution.plan"
        world_dir = project_root / "action" / "world"
        
        # Parse plan file
        plan_data = parse_plan_file(plan_path)
        
        # Step 1: Create initial TTL files (dynamic_0.ttl, static_0.ttl)
        # Copy from ontology_server data directory
        from core.config import get_config
        config_obj = get_config()
        active_env = config_obj.get_active_env()
        
        ontology_server_dir = project_root / "ontology_server"
        env_dir = ontology_server_dir / "data" / "envs" / active_env
        
        # Create world directory if it doesn't exist
        world_dir.mkdir(parents=True, exist_ok=True)
        
        # Copy original TTL files to world directory as version 0
        import shutil
        original_dynamic = env_dir / "dynamic.ttl"
        original_static = env_dir / "static.ttl"
        
        initial_dynamic = world_dir / "dynamic_0.ttl"
        initial_static = world_dir / "static_0.ttl"
        
        if original_dynamic.exists():
            shutil.copy2(original_dynamic, initial_dynamic)
            print(f"Created initial TTL: {initial_dynamic}")
        else:
            print(f"WARNING: Original dynamic.ttl not found at {original_dynamic}")
        
        if original_static.exists():
            shutil.copy2(original_static, initial_static)
            print(f"Created initial TTL: {initial_static}")
        else:
            print(f"WARNING: Original static.ttl not found at {original_static}")
        
        # Create success message
        success_msg = f"Plan loaded successfully:\n"
        success_msg += f"- Total actions: {plan_data['step_count']}\n"
        if plan_data['cost']:
            success_msg += f"- Cost: {plan_data['cost']}\n"
        success_msg += f"\nInitial TTL files created:\n"
        success_msg += f"  - {initial_dynamic.name}\n"
        success_msg += f"  - {initial_static.name}\n"
        success_msg += f"\nActions:\n"
        for i, action in enumerate(plan_data['actions'], 1):
            success_msg += f"{i}. {action}\n"
        
        return {
            "messages": [AIMessage(content=success_msg)],
            "plan_actions": plan_data['actions'],
            "plan_cost": plan_data['cost'],
            "plan_step_count": plan_data['step_count'],
            "plan_raw_content": plan_data['raw_content']
        }
        
    except FileNotFoundError as e:
        error_msg = f"ERROR: Plan file not found: {e}"
        return {
            "messages": [AIMessage(content=error_msg)]
        }
    except Exception as e:
        error_msg = f"ERROR in plan_reader: {type(e).__name__}: {str(e)}"
        import traceback
        traceback.print_exc()
        return {
            "messages": [AIMessage(content=error_msg)]
        }

