"""PDDL Planning Tool - Runs PDDL planner and returns solution."""

import sys
import subprocess
import shutil
import re
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
from langchain_core.tools import tool
from neo4j import GraphDatabase

# Add parent directory to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "ontology_server"))
sys.path.insert(0, str(project_root / "pddl"))

from scripts.pddl_parser import PDDLDomainParser
from scripts.pddl_generator import PDDLGenerator
from scripts.pddl_writer import PDDLWriter
from scripts.pddl_goal_utils import (
    extract_object_ids_from_goal, 
    classify_objects_by_domain_type,
    validate_goal_affordances
)
from core.config import get_config


def build_planner_command(solver: str = "lazy_wastar", heuristic: str = "ff", weight: int = 2) -> str:
    """Build Fast Downward search command."""
    if solver == 'lazy_wastar':
        return f"lazy_wastar([{heuristic}()], w={weight})"
    elif solver == 'astar':
        return f"astar({heuristic}())"
    elif solver == 'lama':
        return "lazy(alt([lama_synergy()], boost=1000), preferred=[lama_synergy()])"
    else:
        return f"lazy_wastar([{heuristic}()], w={weight})"


def normalize_goal_formula(goal_formula: str) -> str:
    """
    Normalize goal formula by converting unsupported predicates to supported ones
    and fixing syntax errors.
    
    Converts:
    - (isClosed ?a) -> (not (isOpen ?a))
    - (isInSpace ?a ?l) -> (artifactIsInSpace ?a ?l)  (domain uses artifactIsInSpace, not isInSpace)
    - Case-insensitive predicate matching for common typos
    - not (predicate) -> (not (predicate))  (fix missing parentheses)
    
    Args:
        goal_formula: Original PDDL goal formula
        
    Returns:
        Normalized goal formula with domain-compatible predicates
    """
    # Define predicate mappings (case-insensitive matching)
    # Format: (pattern, correct_predicate, num_args, special_handling)
    # special_handling: None or function to handle special cases
    predicate_mappings = [
        # isInSpace -> artifactIsInSpace (domain uses artifactIsInSpace, not isInSpace)
        (r'\(isInSpace\s+(\w+)\s+(\w+)\)', 'artifactIsInSpace', 2, None),
        
        # isOnTopOf -> isOntopOf (domain uses isOntopOf, not isOnTopOf)
        (r'\(isOnTopOf\s+(\w+)\s+(\w+)\)', 'isOntopOf', 2, None),
        (r'\(isOnTop\s+(\w+)\)', 'isON', 1, None),  # isOnTop -> isON (common typo)
        
        # Standard predicates with case-insensitive matching
        (r'\(isON\s+(\w+)\)', 'isON', 1, None),
        (r'\(isOpen\s+(\w+)\)', 'isOpen', 1, None),
        (r'\(isHeldBy\s+(\w+)\s+(\w+)\)', 'isHeldBy', 2, None),
        (r'\(isInsideOf\s+(\w+)\s+(\w+)\)', 'isInsideOf', 2, None),
        (r'\(isOntopOf\s+(\w+)\s+(\w+)\)', 'isOntopOf', 2, None),
        (r'\(robotIsInSpace\s+(\w+)\s+(\w+)\)', 'robotIsInSpace', 2, None),
        (r'\(artifactIsOnFloorOf\s+(\w+)\s+(\w+)\)', 'artifactIsOnFloorOf', 2, None),
        (r'\(artifactIsInSpace\s+(\w+)\s+(\w+)\)', 'artifactIsInSpace', 2, None),
        (r'\(isAdjacentTo\s+(\w+)\s+(\w+)\)', 'isAdjacentTo', 2, None),
        (r'\(isLocked\s+(\w+)\)', 'isLocked', 1, None),
        (r'\(isOpenDoor\s+(\w+)\)', 'isOpenDoor', 1, None),
    ]
    
    # Apply all predicate mappings with case-insensitive matching
    for pattern, correct_pred, num_args, special_handler in predicate_mappings:
        def make_replacer(pred_name, num_args, handler):
            if handler:
                return handler
            elif num_args == 1:
                def replacer(match):
                    arg1 = match.group(1)
                    return f"({pred_name} {arg1})"
                return replacer
            elif num_args == 2:
                def replacer(match):
                    arg1 = match.group(1)
                    arg2 = match.group(2)
                    return f"({pred_name} {arg1} {arg2})"
                return replacer
            else:
                return lambda m: m.group(0)  # No change
        
        replacer = make_replacer(correct_pred, num_args, special_handler)
        # Use case-insensitive matching to handle all case variations
        goal_formula = re.sub(pattern, replacer, goal_formula, flags=re.IGNORECASE)
    
    # Convert isClosed to (not (isOpen ...))
    # Pattern: (isClosed artifact_id) -> (not (isOpen artifact_id))
    def replace_isclosed(match):
        artifact_id = match.group(1)
        return f"(not (isOpen {artifact_id}))"
    
    # Match (isClosed artifact_id) - case-insensitive
    goal_formula = re.sub(r'\(isClosed\s+(\w+)\)', replace_isclosed, goal_formula, flags=re.IGNORECASE)
    
    # Fix: not (predicate) -> (not (predicate))
    # This handles cases like: (and ... not (predicate)) -> (and ... (not (predicate)))
    # Pattern: "not (" that is not already wrapped in parentheses
    # We need to match "not (" followed by a complete predicate and wrap it
    
    # Simple approach: find "not (" that's not already "(not ("
    # and wrap the entire predicate including parentheses
    def fix_not_syntax(text):
        # Find "not (" patterns and wrap them
        # Match: whitespace or opening paren, then "not ", then opening paren
        # But not if it's already "(not ("
        result = []
        i = 0
        while i < len(text):
            # Look for "not (" pattern
            if i + 4 < len(text) and text[i:i+5] == "not (":
                # Check if it's already wrapped (look back one char)
                if i == 0 or text[i-1] != '(':
                    # Find matching closing paren for the predicate
                    depth = 1
                    j = i + 5  # Start after "not ("
                    while j < len(text) and depth > 0:
                        if text[j] == '(':
                            depth += 1
                        elif text[j] == ')':
                            depth -= 1
                        j += 1
                    
                    if depth == 0:
                        # Found complete predicate, wrap "not (predicate)" with parentheses
                        result.append("(not ")
                        result.append(text[i+4:j])  # "(" + predicate content + ")"
                        result.append(")")
                        i = j
                        continue
            
            result.append(text[i])
            i += 1
        
        return ''.join(result)
    
    goal_formula = fix_not_syntax(goal_formula)
    
    return goal_formula


def extract_task_description(task_description: str = None, goal_formula: str = None) -> str:
    """Extract task description for naming.

    Args:
        task_description: Optional task description from LLM
        goal_formula: PDDL goal formula to extract description from

    Returns:
        Description string like "isON_tv_44" or "turnOnTV"
    """
    # Extract task description
    if task_description:
        # Use provided description
        desc = task_description
    elif goal_formula:
        # Extract from goal formula - take first predicate
        # e.g., "(isON tv_52)" -> "isON_tv_52"
        match = re.search(r'\((\w+)\s+([^)]+)\)', goal_formula)
        if match:
            predicate = match.group(1)
            obj = match.group(2).split()[0] if ' ' in match.group(2) else match.group(2)
            desc = f"{predicate}_{obj}"
        else:
            desc = "task"
    else:
        desc = "task"

    # Sanitize description for filename (remove special chars, limit length)
    desc = re.sub(r'[^a-zA-Z0-9_]', '', desc)
    desc = desc[:50]  # Limit length

    return desc


@tool
def pddl_plan(goal_formula: str, task_description: str = None) -> str:
    """Execute PDDL planner with the given goal formula.

    This tool:
    1. Extracts objects from the goal
    2. Generates a PDDL problem file with meaningful filename
    3. Runs Fast Downward planner
    4. Returns the solution or error logs

    Args:
        goal_formula: PDDL goal formula (e.g., "(and (isInSpace cup_12 kitchen_5))")
        task_description: Optional task description for filename (e.g., "turnOnTV")

    Returns:
        Success: The generated plan as a string
        Failure: Error logs explaining what went wrong
    """
    try:
        # Normalize goal formula (convert unsupported predicates like isClosed to supported ones)
        goal_formula = normalize_goal_formula(goal_formula)
        
        # Setup paths
        base_dir = Path(__file__).parent.parent.parent / "pddl"
        domain_path = base_dir / "domain.pddl"
        domain_name = "robot"
        
        # Generate timestamp for folder
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Extract task description for PDDL problem naming
        task_desc = extract_task_description(task_description, goal_formula)
        
        # Create timestamp-based log directory (logs/{timestamp}/)
        # mkdir(parents=True, exist_ok=True) ensures logs/ and subdirectory are created
        log_base_dir = base_dir / "logs"
        log_dir = log_base_dir / timestamp
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize debug log
        debug_log: Dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "timestamp_folder": timestamp,
            "task_description": task_desc,
            "goal_formula": goal_formula,
            "task_description_input": task_description,
            "status": "started",
            "files": {
                "problem": None,
                "solution": None,
                "log": None
            }
        }

        # Verify domain exists
        if not domain_path.exists():
            return f"ERROR: Domain file not found at {domain_path}"

        # Parse domain
        parser = PDDLDomainParser(domain_path)

        # Connect to Neo4j
        sys_config = get_config()
        neo4j_config = sys_config.get_neo4j_config()
        driver = GraphDatabase.driver(
            neo4j_config['uri'],
            auth=(neo4j_config['user'], neo4j_config['password'])
        )

        # Initialize generator
        generator = PDDLGenerator(driver, parser)

        # Extract objects from goal
        goal_object_ids = extract_object_ids_from_goal(goal_formula, driver)
        debug_log["extracted_objects"] = {
            "goal_object_ids": goal_object_ids,
            "count": len(goal_object_ids)
        }

        # Get object types
        goal_types_map = generator.get_types(goal_object_ids)
        debug_log["extracted_objects"]["goal_types_map"] = goal_types_map

        # Classify by domain type
        artifact_ids, location_ids = classify_objects_by_domain_type(
            goal_object_ids, goal_types_map, parser
        )
        
        # CRITICAL: Ensure all goal locations are explicitly included
        # This is important for robotIsInSpace goals where the target location must be in location_ids
        for obj_id in goal_object_ids:
            obj_type = goal_types_map.get(obj_id)
            if obj_type and (obj_type == "Location" or obj_type == "Space" or 
                           obj_type == "Door" or obj_type == "Stairs" or obj_type == "Opening" or
                           parser.is_subtype_of(obj_type, "Location")):
                if obj_id not in location_ids:
                    location_ids.append(obj_id)
                    print(f"  ✓ Added goal location to location_ids: {obj_id} ({obj_type})")
        
        # If goal_types_map is empty or objects weren't classified, 
        # ensure goal objects are at least added to artifact_ids as fallback
        # But exclude Hand objects from isHeldBy predicate
        import re
        isHeldBy_matches = re.findall(r'\(isHeldBy\s+(\w+)\s+(\w+)\)', goal_formula)
        hand_ids_in_goal = set()
        for artifact_id, hand_id in isHeldBy_matches:
            hand_ids_in_goal.add(hand_id)
        
        for obj_id in goal_object_ids:
            if obj_id not in artifact_ids and obj_id not in location_ids:
                # Skip if it's a Hand in isHeldBy predicate
                if obj_id in hand_ids_in_goal:
                    continue
                # Try to infer: if it's used in artifact predicates, it's likely an artifact
                artifact_predicates = ['isOpen', 'isON', 'isLocked', 'isInsideOf', 'isOntopOf', 'isHeldBy', 'Affordance']
                if any(pred in goal_formula for pred in artifact_predicates):
                    artifact_ids.append(obj_id)
                    print(f"⚠️  WARNING: Added {obj_id} to artifact_ids as fallback (type not found in Neo4j)")

        # STEP 1: Collect all necessary locations from goal
        # - Goal에 명시된 location들
        # - Artifact의 위치 (isInSpace로 연결된 Space)
        print(f"\n📍 STEP 1: Collecting necessary locations from goal...")
        print(f"   Goal locations: {location_ids}")
        
        # Get artifact locations (this finds where artifacts are located)
        artifact_locs = generator.get_artifact_locations(artifact_ids)
        
        # Extract artifact locations (isInSpace relationships)
        artifact_location_spaces = set()
        for artifact_id, loc_info in artifact_locs.items():
            # isInSpace로 연결된 Space를 찾음
            if "isInSpace" in loc_info:
                space_id = loc_info["isInSpace"]
                artifact_location_spaces.add(space_id)
                if space_id not in location_ids:
                    location_ids.append(space_id)
                    print(f"   ✓ Added artifact location: {space_id} (from {artifact_id})")
        
        # Also include containers/surfaces that artifacts are in/on (for access)
        for artifact_id, loc_info in artifact_locs.items():
            # isInsideOf, isOntopOf 관계로 연결된 artifact의 위치도 필요
            for rel_type in ["isInsideOf", "isOntopOf"]:
                if rel_type in loc_info:
                    container_id = loc_info[rel_type]
                    # Container의 위치도 찾아야 함 (재귀적으로)
                    if container_id in artifact_locs:
                        container_loc_info = artifact_locs[container_id]
                        if "isInSpace" in container_loc_info:
                            container_space = container_loc_info["isInSpace"]
                            if container_space not in location_ids:
                                location_ids.append(container_space)
                                print(f"   ✓ Added container location: {container_space} (from {container_id} containing {artifact_id})")
        
        location_ids = list(set(location_ids))
        print(f"   Total locations from goal: {len(location_ids)}")
        
        # Validate that all goal artifacts have location information
        missing_location_artifacts = []
        for artifact_id in artifact_ids:
            if artifact_id not in artifact_locs:
                missing_location_artifacts.append(artifact_id)
            else:
                # Check if artifact has location information (needed for access action)
                # Accept: isInSpace, isInsideOf, isOntopOf
                loc_info = artifact_locs[artifact_id]
                has_location = (
                    "isInSpace" in loc_info or
                    "isInsideOf" in loc_info or
                    "isOntopOf" in loc_info
                )
                if not has_location:
                    missing_location_artifacts.append(artifact_id)
        
        if missing_location_artifacts:
            warning_msg = f"⚠️  WARNING: Artifacts in goal lack location information: {missing_location_artifacts}\n"
            warning_msg += "  These artifacts cannot be accessed by the robot without location information.\n"
            warning_msg += "  This will likely cause planning to fail.\n"
            print(warning_msg)
            debug_log["location_warnings"] = {
                "missing_location_artifacts": missing_location_artifacts,
                "message": "Artifacts in goal lack location information (isInSpace, isInsideOf, or isOntopOf)"
            }

        # STEP 2: Get robot's current location
        print(f"\n🤖 STEP 2: Getting robot's current location...")
        robot_info = generator.get_robot_info()
        if not robot_info:
            driver.close()
            return "ERROR: No robot found in knowledge graph"

        robot_location = robot_info.get('location')
        if robot_location:
            if robot_location not in location_ids:
                location_ids.append(robot_location)
                print(f"   ✓ Added robot location: {robot_location}")
            else:
                print(f"   Robot location already in list: {robot_location}")
        else:
            print(f"   ⚠️  WARNING: Robot has no location!")
        
        location_ids = list(set(location_ids))
        print(f"   Total necessary locations: {len(location_ids)}")
        print(f"   Locations: {sorted(location_ids)}")

        # STEP 3: Collect all necessary locations
        # Now we have:
        # - Goal locations (from goal_formula)
        # - Artifact locations (isInSpace)
        # - Robot location
        # These are ALL the locations we need for planning
        print(f"\n📍 STEP 3: Summary of necessary locations...")
        print(f"   Total necessary locations: {len(location_ids)}")
        print(f"   Locations: {sorted(location_ids)}")
        
        # STEP 4: Find paths between ALL pairs of necessary locations
        # Strategy: Find shortest paths between ALL pairs (nC2 combinations)
        # This ensures we don't miss any important paths
        # Example: If we have 5 locations, we find paths for all 5C2=10 pairs
        print(f"\n🗺️  STEP 4: Finding paths between all necessary locations...")
        print(f"   Strategy: Find shortest paths for all {len(location_ids)}C2 = {len(location_ids) * (len(location_ids) - 1) // 2} pairs")
        print(f"   This ensures completeness - we include all paths between:")
        print(f"     - Robot location <-> Goal locations")
        print(f"     - Robot location <-> Artifact locations")
        print(f"     - Goal locations <-> Artifact locations")
        print(f"     - Artifact locations <-> Artifact locations")
        
        all_locations, precomputed_distances = generator.get_locations_with_paths(
            location_ids, 
            robot_location=robot_location
        )
        print(f"   ✓ Expanded to {len(all_locations)} locations (including intermediate locations on paths)")
        print(f"   Locations: {sorted(all_locations)[:20]}..." if len(all_locations) > 20 else f"   Locations: {sorted(all_locations)}")
        print(f"   ✓ Precomputed {len(precomputed_distances)} distances during path exploration (will be reused)")

        # Collect all required objects (artifacts, robot, hands)
        all_object_ids = generator.get_all_required_objects(artifact_ids, all_locations, artifact_locs)
        all_object_ids_list = list(all_object_ids)

        # Add all goal objects
        for obj_id in goal_object_ids:
            if obj_id not in all_object_ids_list:
                all_object_ids_list.append(obj_id)

        # Add robot and hands
        if robot_info['robot_id'] not in all_object_ids_list:
            all_object_ids_list.append(robot_info['robot_id'])
        for hand in robot_info.get('hands', []):
            if hand not in all_object_ids_list:
                all_object_ids_list.append(hand)
        
        # CRITICAL: Add all locations from paths (including Portals: Door, Stairs, Opening)
        # These are the locations on paths between goal locations
        for loc_id in all_locations:
            if loc_id not in all_object_ids_list:
                all_object_ids_list.append(loc_id)
                print(f"  Added location from path: {loc_id}")

        # Get types for all objects (get_types now checks both node labels and INSTANCE_OF relationships)
        print(f"\n🏷️  Getting types for all objects (checking node labels and INSTANCE_OF relationships)...")
        types_map = generator.get_types(all_object_ids_list)
        
        # Log classified location types
        location_types_found = {loc_id: types_map.get(loc_id) for loc_id in all_locations if loc_id in types_map}
        if location_types_found:
            print(f"  ✓ Classified {len(location_types_found)} locations from paths:")
            for loc_id, loc_type in sorted(location_types_found.items()):
                print(f"    {loc_id} -> {loc_type}")
        
        # For locations still missing types, try ID-based inference
        missing_location_types = [loc_id for loc_id in all_locations if loc_id not in types_map]
        if missing_location_types:
            print(f"  ⚠️  {len(missing_location_types)} locations missing types, using ID-based inference...")
            for loc_id in missing_location_types:
                loc_id_lower = loc_id.lower()
                if "opening" in loc_id_lower:
                    types_map[loc_id] = "Opening"
                    print(f"    {loc_id} -> Opening (inferred from ID)")
                elif "stair" in loc_id_lower:
                    types_map[loc_id] = "Stairs"
                    print(f"    {loc_id} -> Stairs (inferred from ID)")
                elif "door" in loc_id_lower:
                    types_map[loc_id] = "Door"
                    print(f"    {loc_id} -> Door (inferred from ID)")
                else:
                    types_map[loc_id] = "Space"  # Default to Space
                    print(f"    {loc_id} -> Space (default)")
        
        # Ensure robot and hands are in types_map
        if robot_info['robot_id'] not in types_map:
            types_map[robot_info['robot_id']] = "Robot"
        for hand in robot_info.get('hands', []):
            if hand not in types_map:
                types_map[hand] = "Hand"
        
        # Ensure all goal objects are in types_map (they may not be found in Neo4j)
        # Try to infer type from goal formula if not found
        isHeldBy_matches = re.findall(r'\(isHeldBy\s+(\w+)\s+(\w+)\)', goal_formula)
        hand_ids_in_goal = set()
        artifact_ids_in_isHeldBy = set()
        for artifact_id, hand_id in isHeldBy_matches:
            hand_ids_in_goal.add(hand_id)
            artifact_ids_in_isHeldBy.add(artifact_id)
        
        for obj_id in goal_object_ids:
            if obj_id not in types_map:
                obj_types = generator.get_types([obj_id])
                if obj_id in obj_types:
                    types_map[obj_id] = obj_types[obj_id]
                else:
                    # Infer from goal formula context
                    if obj_id in hand_ids_in_goal:
                        types_map[obj_id] = "Hand"
                    elif any(pred in goal_formula for pred in ['isOpen', 'isON', 'isLocked', 'isInsideOf', 'isOntopOf']):
                        types_map[obj_id] = "Artifact"
                    elif obj_id in artifact_ids_in_isHeldBy:
                        types_map[obj_id] = "Artifact"
                    elif 'robotIsInSpace' in goal_formula and obj_id == robot_info['robot_id']:
                        types_map[obj_id] = "Robot"
                    else:
                        print(f"⚠️  WARNING: Could not determine type for {obj_id}, defaulting to Artifact")
                        types_map[obj_id] = "Artifact"
        
        # Ensure all locations from all_locations are in types_map
        # This is critical for get_topology to work correctly
        missing_location_types = [loc_id for loc_id in all_locations if loc_id not in types_map]
        if missing_location_types:
            print(f"  ⚠️  WARNING: {len(missing_location_types)} locations missing from types_map, adding them...")
            # Get types for missing locations
            missing_types = generator.get_types(missing_location_types)
            for loc_id, loc_type in missing_types.items():
                types_map[loc_id] = loc_type
            # For still missing ones, use ID-based inference
            still_missing = [loc_id for loc_id in missing_location_types if loc_id not in types_map]
            for loc_id in still_missing:
                loc_id_lower = loc_id.lower()
                if "opening" in loc_id_lower:
                    types_map[loc_id] = "Opening"
                elif "stair" in loc_id_lower:
                    types_map[loc_id] = "Stairs"
                elif "door" in loc_id_lower:
                    types_map[loc_id] = "Door"
                else:
                    types_map[loc_id] = "Space"
        
        # Get door states for Door locations (from classified types)
        door_ids = [loc_id for loc_id in all_locations if types_map.get(loc_id) == "Door"]
        door_states = generator.get_door_states(door_ids) if door_ids else {}
        
        # NOTE: We only include locations on paths between necessary locations
        # No need to find ALL connected Spaces - that would include everything!
        # all_locations already contains:
        # - Goal locations
        # - Robot location
        # - Artifact locations
        # - Locations on shortest paths between them (from get_locations_with_paths)
        print(f"\n📍 Using {len(all_locations)} locations (only necessary ones on paths)")
        
        # Build topology (with types_map for Space->Space distance calculation)
        # All locations should now be in types_map
        # Use precomputed distances from get_locations_with_paths to avoid redundant queries
        print(f"\n🗺️  Building topology from {len(all_locations)} locations...")
        print(f"   Locations in types_map: {sum(1 for loc_id in all_locations if loc_id in types_map)}/{len(all_locations)}")
        topology = generator.get_topology(all_locations, types_map, precomputed_distances=precomputed_distances)
        print(f"   Topology connections: {len(topology['connections'])}")
        if topology['connections']:
            print(f"   Sample connections: {topology['connections'][:5]}")
        else:
            print(f"   ⚠️  WARNING: No topology connections found!")
        print(f"   Topology distances (Space->Space only): {len(topology.get('distances', {}))}")

        # Get affordances
        affordances_map = generator.get_affordances(artifact_ids)
        
        # Add door debugging info to debug_log
        all_ids_to_check = set(all_object_ids_list) | all_locations
        debug_log["door_debug"] = {
            "all_object_ids_list_length": len(all_object_ids_list),
            "all_locations_length": len(all_locations),
            "all_ids_to_check_length": len(all_ids_to_check),
            "door_ids_found": door_ids,
            "door_ids_count": len(door_ids),
            "door_states_found": door_states,
            "door_states_count": len(door_states),
            "door_like_in_types_map": [obj_id for obj_id, obj_type in types_map.items() 
                                      if obj_type == "Door"],
            "door_like_in_all_locations": [loc_id for loc_id in all_locations 
                                          if types_map.get(loc_id) == "Door"],
        }
        
        if door_states:
            print(f"   Door states: {door_states}")
        else:
            print(f"   ⚠️  WARNING: No door states found! Doors may not be openable.")
            print(f"   This means doors cannot be opened/closed, which may prevent movement.")
            if door_ids:
                print(f"   ⚠️  Door IDs were found but get_door_states returned empty!")
                print(f"   This may indicate that doors are not in Neo4j or query failed.")
        
        # NOTE: Space->Space distances are now calculated in get_topology() when types_map is provided
        # The topology['distances'] already contains Space->Space distances only
        # Verify that distances are Space->Space only
        # Get Space IDs from all_locations (not just all_object_ids_list)
        # This ensures we include all locations from paths, even if they weren't in all_object_ids_list initially
        space_ids = [loc_id for loc_id in all_locations 
                    if types_map.get(loc_id) == "Space"]
        
        # Count Space->Space distances
        space_to_space_count = 0
        for (from_id, to_id) in topology.get('distances', {}).keys():
            if types_map.get(from_id) == "Space" and types_map.get(to_id) == "Space":
                space_to_space_count += 1
        
        # Store final distances count for later use
        final_distances_count = len(topology.get('distances', {}))
        
        print(f"\n✓ Space->Space distances: {space_to_space_count} (calculated in get_topology)")
        
        # Add distance calculation info to debug log
        debug_log["distance_calculation"] = {
            "all_object_ids_list_length": len(all_object_ids_list),
            "types_map_length": len(types_map),
            "space_ids_count": len(space_ids),
            "space_ids_sample": space_ids[:10] if space_ids else [],
            "space_to_space_distances_count": space_to_space_count,
            "final_topology_distances_count": final_distances_count,
            "note": "Space->Space distances calculated in get_topology() with types_map",
            "warnings": []
        }
        if not space_ids:
            debug_log["distance_calculation"]["warnings"].append("No Space objects found in all_object_ids_list")
        if space_to_space_count == 0:
            debug_log["distance_calculation"]["warnings"].append("No Space->Space distances found in topology")
        if not topology.get('distances'):
            debug_log["distance_calculation"]["warnings"].append("No distances in topology")
        
        # Get key-safe relationships (unlocks, requiresKey) - first pass to find related keys
        key_safe_rels = generator.get_key_safe_relationships(artifact_ids)
        
        # Debug: Check if relationships were found
        unlocks_map = key_safe_rels.get('unlocks', {})
        requires_key_map = key_safe_rels.get('requiresKey', {})
        if not unlocks_map and not requires_key_map and any('safe' in aid.lower() for aid in artifact_ids):
            print(f"⚠️  WARNING: No key-safe relationships found for artifacts: {artifact_ids}")
            print(f"   This may indicate that relationships are not in Neo4j or query failed")
        
        # Extract keys from relationships and add them to artifact_ids if not already included
        related_key_ids = set()
        
        # Collect all keys mentioned in unlocks relationships
        for key_id in unlocks_map.keys():
            related_key_ids.add(key_id)
        
        # Collect all keys mentioned in requiresKey relationships
        for safe_id, key_ids in requires_key_map.items():
            for key_id in key_ids:
                related_key_ids.add(key_id)
        
        # Add related keys to artifact_ids if not already present
        keys_added = []
        for key_id in related_key_ids:
            if key_id not in artifact_ids:
                artifact_ids.append(key_id)
                keys_added.append(key_id)
        
        # If keys were added, update types_map, artifact_locs, and all_object_ids_list
        if keys_added:
            print(f"🔑 Added related keys to problem: {keys_added}")
            
            # Get types for new keys
            key_types_map = generator.get_types(keys_added)
            for key_id in keys_added:
                if key_id in key_types_map:
                    types_map[key_id] = key_types_map[key_id]
                else:
                    # Fallback: keys are artifacts
                    types_map[key_id] = "Artifact"
                    print(f"⚠️  WARNING: Could not determine type for key {key_id}, defaulting to Artifact")
                if key_id not in all_object_ids_list:
                    all_object_ids_list.append(key_id)
            
            # Get locations for new keys
            key_artifact_locs = generator.get_artifact_locations(keys_added)
            for key_id, loc_info in key_artifact_locs.items():
                artifact_locs[key_id] = loc_info
                # Add location IDs from key locations to location_ids
                for loc_id in loc_info.values():
                    if loc_id not in location_ids:
                        location_ids.append(loc_id)
            
            # Expand locations with paths for newly added locations
            if location_ids:
                additional_locations, additional_distances = generator.get_locations_with_paths(location_ids)
                all_locations.update(additional_locations)
                # Update precomputed_distances with new distances
                precomputed_distances.update(additional_distances)
                # Update topology with new locations
                # CRITICAL: Preserve existing distances (including Space->Space distances)
                existing_distances = topology.get('distances', {}).copy()
                topology = generator.get_topology(all_locations, types_map, precomputed_distances=precomputed_distances)
                # Restore existing distances
                topology['distances'].update(existing_distances)
                
                # Add location objects to all_object_ids_list and types_map
                for loc_id in additional_locations:
                    if loc_id not in all_object_ids_list:
                        all_object_ids_list.append(loc_id)
                        loc_type_result = generator.get_types([loc_id])
                        if loc_id in loc_type_result:
                            types_map[loc_id] = loc_type_result[loc_id]
            
            # Re-fetch key-safe relationships with updated artifact_ids to ensure completeness
            key_safe_rels = generator.get_key_safe_relationships(artifact_ids)
            
            # Get affordances for new keys
            key_affordances = generator.get_affordances(keys_added)
            for key_id, affs in key_affordances.items():
                affordances_map[key_id] = affs
        
        # Validate that artifacts in goal have required affordances
        affordance_warnings, affordance_validation = validate_goal_affordances(
            goal_formula, artifact_ids, affordances_map
        )
        if affordance_warnings:
            print("\n⚠️  Goal Affordance Warnings:")
            for warning in affordance_warnings:
                print(f"  {warning}")
            print("  This may cause planning to fail if required affordances are missing.\n")
        
        # Always add affordance validation info to debug log (even if no issues)
        debug_log["affordance_validation"] = {
            "warnings": affordance_warnings,
            "has_issues": affordance_validation["has_issues"],
            "artifacts_with_issues": affordance_validation["artifacts_with_issues"],
            "all_artifact_affordances": {
                artifact_id: sorted(affordances_map.get(artifact_id, []))
                for artifact_id in artifact_ids
            }
        }

        # Write problem file in log directory
        problem_path = log_dir / "problem.pddl"
        debug_log["files"]["problem"] = str(problem_path)
        
        # Verify topology distances before writing
        # Recalculate final_distances_count in case topology was updated (e.g., when keys were added)
        final_distances_count = len(topology.get('distances', {}))
        topology_distances_before_write = len(topology.get('distances', {}))
        debug_log["distance_calculation"]["topology_distances_before_write"] = topology_distances_before_write
        if topology_distances_before_write != final_distances_count:
            debug_log["distance_calculation"]["warnings"].append(
                f"Topology distances count changed: {final_distances_count} -> {topology_distances_before_write}"
            )
        
        # Add door_states info to debug_log before writing
        debug_log["door_debug"]["door_states_passed_to_write_problem"] = door_states
        debug_log["door_debug"]["door_states_count_passed"] = len(door_states) if door_states else 0
        
        # Use timestamp + description as problem name for PDDL file content
        problem_name = f"{timestamp}_{task_desc}"
        writer = PDDLWriter(problem_name, domain_name)
        writer.write_problem(
            problem_path,
            types_map,
            topology,
            robot_info,
            artifact_locs,
            affordances_map,
            goal_formula,
            door_states,
            key_safe_rels
        )
        
        # Verify what was actually written to file
        if problem_path.exists():
            with open(problem_path, 'r') as f:
                problem_content = f.read()
                isOpenDoor_lines = [line for line in problem_content.split('\n') if 'isOpenDoor' in line]
                debug_log["door_debug"]["isOpenDoor_lines_in_file"] = isOpenDoor_lines
                debug_log["door_debug"]["isOpenDoor_count_in_file"] = len(isOpenDoor_lines)
        
        # Verify what was actually written
        if problem_path.exists():
            with open(problem_path, 'r') as f:
                problem_content = f.read()
                distance_lines = [line for line in problem_content.split('\n') if 'distance' in line and '=' in line]
                debug_log["distance_calculation"]["distances_written_to_file"] = len(distance_lines)
                debug_log["distance_calculation"]["space_to_space_in_file"] = len([
                    line for line in distance_lines 
                    if any(space in line for space in space_ids) and 
                       any(space in line for space in space_ids if space != line.split()[2])
                ])
        
        # Update debug log with problem generation info
        artifact_count = len([v for v in types_map.values() if v == 'Artifact'])
        location_count = len([v for v in types_map.values() if v == 'Location'])
        debug_log["problem_generation"] = {
            "total_objects": len(types_map),
            "artifacts": artifact_count,
            "locations": location_count,
            "robot_id": robot_info['robot_id'],
            "robot_location": robot_info.get('location'),
            "artifact_ids": artifact_ids,
            "location_ids": list(location_ids)
        }
        
        print(f"✓ Generated PDDL problem: {problem_path}")
        print(f"  Goal: {goal_formula}")
        print(f"  Objects: {len(types_map)} ({artifact_count} artifacts, {location_count} locations)")

        driver.close()

        # Run Fast Downward
        fd_path = base_dir / "fast-downward" / "fast-downward.py"
        if not fd_path.exists():
            return f"ERROR: Fast Downward not found at {fd_path}"

        search_cmd = build_planner_command()
        solution_path = log_dir / "solution.plan"
        debug_log["files"]["solution"] = str(solution_path)
        debug_log["planner"] = {
            "command": search_cmd,
            "domain": str(domain_path),
            "problem": str(problem_path)
        }
        sas_plan_path = base_dir / "sas_plan"

        result = subprocess.run(
            [
                "python", str(fd_path),
                str(domain_path),
                str(problem_path),
                "--search", search_cmd
            ],
            capture_output=True,
            text=True,
            cwd=base_dir,
            timeout=60
        )
        
        debug_log["planner"]["returncode"] = result.returncode
        debug_log["planner"]["stdout"] = result.stdout
        debug_log["planner"]["stderr"] = result.stderr

        # Check result
        if result.returncode == 0:
            # Success - read solution
            if sas_plan_path.exists():
                shutil.copy(sas_plan_path, solution_path)
                sas_plan_path.unlink()

            if solution_path.exists():
                with open(solution_path, 'r') as f:
                    solution_content = f.read()

                # Extract plan metrics
                metrics = []
                plan_length = None
                plan_cost = None
                for line in result.stdout.split('\n'):
                    if 'Plan length' in line:
                        metrics.append(line.strip())
                        # Extract number
                        match = re.search(r'(\d+)', line)
                        if match:
                            plan_length = int(match.group(1))
                    elif 'Plan cost' in line:
                        metrics.append(line.strip())
                        # Extract number
                        match = re.search(r'(\d+)', line)
                        if match:
                            plan_cost = int(match.group(1))

                # Parse solution content and format nicely
                plan_lines = solution_content.strip().split('\n')
                action_lines = []
                cost_line = None
                
                for line in plan_lines:
                    line = line.strip()
                    if not line or line.startswith(';'):
                        if 'cost' in line.lower():
                            cost_line = line
                        continue
                    # Only include action lines (lines starting with '(')
                    if line.startswith('('):
                        action_lines.append(line)

                # Format plan with numbered steps
                formatted_plan = []
                for i, action in enumerate(action_lines, 1):
                    formatted_plan.append(f"{i:2d}. {action}")
                
                if cost_line:
                    formatted_plan.append("")
                    formatted_plan.append(f"    {cost_line}")

                # Update debug log
                debug_log["status"] = "success"
                debug_log["solution"] = {
                    "plan_length": plan_length,
                    "plan_cost": plan_cost,
                    "actions": action_lines
                }
                debug_log["files"]["solution"] = str(solution_path)

                # Format response with file paths for debugging
                response = "SUCCESS:\n\n"
                response += "Plan:\n"
                response += "\n".join(formatted_plan) + "\n\n"
                response += "Metrics:\n" + "\n".join(metrics) + "\n\n"
                response += f"Files saved in: {log_dir}\n"
                response += f"  - problem.pddl\n"
                response += f"  - solution.plan\n"
                response += f"  - debug.json\n"
                
                # Save debug log in log directory
                log_path = log_dir / "debug.json"
                debug_log["files"]["log"] = str(log_path)
                with open(log_path, 'w') as f:
                    json.dump(debug_log, f, indent=2)
                print(f"✓ Debug log saved: {log_path}")
                
                return response
            else:
                return f"SUCCESS: Planning completed but solution file not found.\n\nFiles saved in: {log_dir}\nProblem file: {problem_path}\nPlanner output:\n{result.stdout}"

        else:
            # Failure - update debug log and return error logs
            debug_log["status"] = "failed"
            debug_log["error"] = {
                "type": "planner_error",
                "returncode": result.returncode
            }
            
            # Save debug log even on failure
            log_path = log_dir / "debug.json"
            debug_log["files"]["log"] = str(log_path)
            with open(log_path, 'w') as f:
                json.dump(debug_log, f, indent=2)
            print(f"✓ Debug log saved: {log_path}")
            
            error_msg = "PLANNING FAILED:\n\n"
            error_msg += f"Files saved in: {log_dir}\n"
            error_msg += f"  - problem.pddl\n"
            error_msg += f"  - debug.json\n\n"
            error_msg += "STDOUT:\n" + result.stdout + "\n\n"
            if result.stderr:
                error_msg += "STDERR:\n" + result.stderr
            error_msg += f"\n\nTo debug:\n"
            error_msg += f"  1. Check problem file: {problem_path}\n"
            error_msg += f"  2. Check domain file: {domain_path}\n"
            error_msg += f"  3. Check debug log: {log_path}\n"
            error_msg += f"  4. Verify goal formula and object IDs in Neo4j\n"
            return error_msg

    except subprocess.TimeoutExpired:
        debug_log["status"] = "timeout"
        debug_log["error"] = {"type": "timeout", "timeout_seconds": 60}
        log_path = log_dir / "debug.json"
        debug_log["files"]["log"] = str(log_path)
        try:
            with open(log_path, 'w') as f:
                json.dump(debug_log, f, indent=2)
            return f"ERROR: Planner timed out after 60 seconds\nDebug log: {log_path}"
        except:
            return f"ERROR: Planner timed out after 60 seconds"
    except Exception as e:
        debug_log["status"] = "error"
        debug_log["error"] = {
            "type": type(e).__name__,
            "message": str(e)
        }
        log_path = log_dir / "debug.json"
        debug_log["files"]["log"] = str(log_path)
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            with open(log_path, 'w') as f:
                json.dump(debug_log, f, indent=2)
            return f"ERROR: {type(e).__name__}: {str(e)}\nDebug log: {log_path}"
        except:
            return f"ERROR: {type(e).__name__}: {str(e)}"
