#!/usr/bin/env python3
"""PDDL Goal Utilities - Extract and classify objects from goal formula."""

import re
from typing import List, Set, Tuple, Dict


def extract_identifiers_from_goal(goal_formula: str) -> Set[str]:
    """Extract all potential identifiers from PDDL goal formula."""
    keywords = {
        'and', 'or', 'not', 'forall', 'exists', 'when', 'imply',
        'either', 'increase', 'decrease', 'assign'
    }

    pattern = r'\b([a-zA-Z][a-zA-Z0-9_-]*)\b'
    identifiers = re.findall(pattern, goal_formula)
    return {id for id in identifiers if id.lower() not in keywords}


def filter_valid_object_ids(identifiers: Set[str], driver) -> List[str]:
    """Filter identifiers to only include valid object IDs that exist in Neo4j."""
    if not identifiers:
        return []

    with driver.session() as session:
        result = session.run("""
            UNWIND $ids AS id
            MATCH (n:Individual {id: id})
            RETURN DISTINCT id
        """, ids=list(identifiers))

        return [record["id"] for record in result]


def extract_object_ids_from_goal(goal_formula: str, driver) -> List[str]:
    """Extract valid object IDs from PDDL goal formula."""
    identifiers = extract_identifiers_from_goal(goal_formula)
    return filter_valid_object_ids(identifiers, driver)


def classify_objects_by_domain_type(
    object_ids: List[str],
    types_map: Dict[str, str],
    domain_parser
) -> Tuple[List[str], List[str]]:
    """Classify object IDs into artifacts and locations based on domain type hierarchy."""
    artifact_ids = []
    location_ids = []

    for obj_id in object_ids:
        obj_type = types_map.get(obj_id)

        if not obj_type:
            continue

        if domain_parser.is_subtype_of(obj_type, "Location") or obj_type == "Location":
            location_ids.append(obj_id)
        elif obj_type == "Artifact":
            artifact_ids.append(obj_id)

    return artifact_ids, location_ids


def validate_goal_affordances(
    goal_formula: str,
    artifact_ids: List[str],
    affordances_map: Dict[str, List[str]]
) -> Tuple[List[str], Dict[str, any]]:
    """
    Validate that artifacts in goal have required affordances for goal predicates.
    
    Args:
        goal_formula: PDDL goal formula string
        artifact_ids: List of artifact IDs in the goal
        affordances_map: Dictionary mapping artifact IDs to their affordances
        
    Returns:
        Tuple of (warnings list, validation dict)
    """
    warnings = []
    artifacts_with_issues = []
    
    # Map predicates to required affordances
    predicate_to_affordance = {
        'isON': 'Affordance_Power',
        'isOpen': 'Affordance_Open',
        # Add more mappings as needed
    }
    
    # Extract predicates from goal formula
    predicate_pattern = r'\((\w+)\s+([^)]+)\)'
    matches = re.findall(predicate_pattern, goal_formula)
    
    for predicate, args in matches:
        required_affordance = predicate_to_affordance.get(predicate)
        if not required_affordance:
            continue
            
        # Extract artifact IDs from arguments
        arg_ids = args.split()
        for arg_id in arg_ids:
            arg_id = arg_id.strip()
            if arg_id in artifact_ids:
                artifact_affordances = affordances_map.get(arg_id, [])
                if required_affordance not in artifact_affordances:
                    warning = f"Artifact '{arg_id}' needs '{required_affordance}' for predicate '{predicate}' but only has: {artifact_affordances}"
                    warnings.append(warning)
                    if arg_id not in artifacts_with_issues:
                        artifacts_with_issues.append(arg_id)
    
    validation = {
        "has_issues": len(warnings) > 0,
        "artifacts_with_issues": artifacts_with_issues
    }
    
    return warnings, validation


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    from neo4j import GraphDatabase
    from core.config import get_config
    from pddl.scripts.pddl_parser import PDDLDomainParser
    from pddl.scripts.pddl_generator import PDDLGenerator

    test_goal = """
    (and
        (isON tv_52)
        (isOpen oven_53)
        (robotIsInSpace robot1 living_room_23)
    )
    """

    print("Testing PDDL Goal Utilities")
    print("=" * 60)

    identifiers = extract_identifiers_from_goal(test_goal)
    print(f"\nExtracted identifiers: {sorted(identifiers)}")

    config = get_config()
    neo4j_config = config.get_neo4j_config()
    driver = GraphDatabase.driver(neo4j_config['uri'], auth=(neo4j_config['user'], neo4j_config['password']))

    object_ids = extract_object_ids_from_goal(test_goal, driver)
    print(f"\nValid object IDs: {sorted(object_ids)}")

    domain_path = Path(__file__).parent.parent / "domain.pddl"
    parser = PDDLDomainParser(domain_path)
    generator = PDDLGenerator(driver, parser)

    types_map = generator.get_types(object_ids)
    artifact_ids, location_ids = classify_objects_by_domain_type(
        object_ids, types_map, parser
    )

    print(f"\nArtifact IDs: {artifact_ids}")
    print(f"Location IDs: {location_ids}")

    driver.close()
