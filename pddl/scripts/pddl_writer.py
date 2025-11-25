#!/usr/bin/env python3
"""PDDL Writer - Generate PDDL problem file from collected data."""

from pathlib import Path
from typing import Dict, List, Any


class PDDLWriter:
    """Generate PDDL problem file from data."""

    def __init__(self, problem_name: str, domain_name: str = "robot"):
        """
        Initialize PDDL writer.

        Args:
            problem_name: Name of the problem
            domain_name: Name of the domain
        """
        self.problem_name = problem_name
        self.domain_name = domain_name

    def generate_objects(self, types_map: Dict[str, str]) -> str:
        """
        Generate objects section.

        Args:
            types_map: Dict mapping object_id to type

        Returns:
            PDDL objects section string
        """
        # Group by type
        types_grouped = {}
        for obj_id, obj_type in types_map.items():
            if obj_type not in types_grouped:
                types_grouped[obj_type] = []
            types_grouped[obj_type].append(obj_id)

        # Generate PDDL
        lines = ["  (:objects"]

        # Add comment for each type group
        for obj_type in sorted(types_grouped.keys()):
            obj_ids = sorted(types_grouped[obj_type])
            lines.append(f"    ; {obj_type}")
            lines.append(f"    {' '.join(obj_ids)} - {obj_type}")
            lines.append("")

        # Remove last empty line and add closing
        lines = lines[:-1]
        lines.append("  )")

        return "\n".join(lines)

    def generate_init_topology(self, topology: Dict[str, Any], types_map: Dict[str, str] = None) -> List[str]:
        """
        Generate topology section of init.

        Args:
            topology: Dict with 'connections' and 'distances'
            types_map: Optional dict mapping object_id to type (not used for filtering anymore)

        Returns:
            List of PDDL init statements
        """
        lines = []

        lines.append("    ; ====================================================================")
        lines.append("    ; TOPOLOGY")
        lines.append("    ; ====================================================================")

        connections = topology['connections']
        distances = topology['distances']

        # Group connections by pairs
        for from_id, to_id in sorted(connections):
            lines.append(f"    (hasPathTo {from_id} {to_id})")
            lines.append(f"    (hasPathTo {to_id} {from_id})")

        if distances:
            lines.append("")
            lines.append("    ; ====================================================================")
            lines.append("    ; DISTANCES (Location->Location)")
            lines.append("    ; ====================================================================")
            lines.append("    ; Distance between locations via hasPathTo relationships")

            # Use all distances (Location->Location)
            for (from_id, to_id), dist in sorted(distances.items()):
                lines.append(f"    (= (distance {from_id} {to_id}) {dist})")

        return lines

    def generate_init_robot(self, robot_info: Dict[str, Any]) -> List[str]:
        """
        Generate robot structure section of init.

        Args:
            robot_info: Dict with robot_id, hands, location

        Returns:
            List of PDDL init statements
        """
        lines = []

        lines.append("    ; ====================================================================")
        lines.append("    ; ROBOT STRUCTURE")
        lines.append("    ; ====================================================================")

        robot_id = robot_info['robot_id']

        # hasHand relationships
        for hand_id in sorted(robot_info['hands']):
            lines.append(f"    (hasHand {robot_id} {hand_id})")

        # Initial location
        if robot_info['location']:
            lines.append(f"    (robotIsInSpace {robot_id} {robot_info['location']})")

        return lines

    def generate_init_artifact_locations(self, artifact_locs: Dict[str, Dict[str, str]]) -> List[str]:
        """
        Generate artifact location section of init.

        Args:
            artifact_locs: Dict mapping artifact_id to location info
                Relationship types from Neo4j:
                - isInSpace, objectIsInSpace -> artifactIsOnFloorOf (PDDL predicate)
                - isInsideOf, isOntopOf -> isInsideOf, isOntopOf (unchanged)

        Returns:
            List of PDDL init statements
        """
        lines = []

        lines.append("    ; ====================================================================")
        lines.append("    ; ARTIFACT LOCATIONS")
        lines.append("    ; ====================================================================")

        for artifact_id in sorted(artifact_locs.keys()):
            loc_info = artifact_locs[artifact_id]

            # Map Neo4j isInSpace to PDDL artifactIsOnFloorOf
            if "isInSpace" in loc_info:
                lines.append(f"    (artifactIsOnFloorOf {artifact_id} {loc_info['isInSpace']})")
            
            # Container relationships
            if "isInsideOf" in loc_info:
                lines.append(f"    (isInsideOf {artifact_id} {loc_info['isInsideOf']})")
            
            # Surface relationships
            if "isOntopOf" in loc_info:
                lines.append(f"    (isOntopOf {artifact_id} {loc_info['isOntopOf']})")

        return lines

    def generate_init_affordances(self, affordances_map: Dict[str, List[str]]) -> List[str]:
        """
        Generate affordances section of init.

        Args:
            affordances_map: Dict mapping artifact_id to affordance instance IDs

        Returns:
            List of PDDL init statements
        """
        lines = []

        lines.append("    ; ====================================================================")
        lines.append("    ; AFFORDANCES")
        lines.append("    ; ====================================================================")

        for artifact_id in sorted(affordances_map.keys()):
            affordances = sorted(affordances_map[artifact_id])
            for affordance_id in affordances:
                lines.append(f"    ({affordance_id} {artifact_id})")

        return lines

    def generate_init_door_states(self, door_states: Dict[str, bool]) -> List[str]:
        """
        Generate door states section of init.
        
        Args:
            door_states: Dict mapping door_id to isOpenDoor boolean value
            
        Returns:
            List of PDDL init statements
        """
        lines = []

        if not door_states:
            return lines

        lines.append("    ; ====================================================================")
        lines.append("    ; DOOR STATES")
        lines.append("    ; ====================================================================")

        for door_id in sorted(door_states.keys()):
            is_open = door_states[door_id]
            if is_open:
                lines.append(f"    (isOpenDoor {door_id})")

        return lines

    def generate_init_key_safe_relationships(self, key_safe_rels: Dict[str, Dict[str, List[str]]]) -> List[str]:
        """
        Generate key-safe relationships and locked states section of init.
        
        Args:
            key_safe_rels: Dict with 'unlocks' and 'requiresKey' mappings
                {
                    'unlocks': {key_id: [safe_id, ...], ...},
                    'requiresKey': {safe_id: [key_id, ...], ...}
                }
            
        Returns:
            List of PDDL init statements
        """
        lines = []

        unlocks_map = key_safe_rels.get('unlocks', {})
        requires_key_map = key_safe_rels.get('requiresKey', {})

        if not unlocks_map and not requires_key_map:
            return lines

        lines.append("    ; ====================================================================")
        lines.append("    ; KEY-SAFE RELATIONSHIPS")
        lines.append("    ; ====================================================================")

        # unlocks relationships (key unlocks safe) - bidirectional relationship
        for key_id in sorted(unlocks_map.keys()):
            for safe_id in sorted(unlocks_map[key_id]):
                lines.append(f"    (unlocks {key_id} {safe_id})")

        lines.append("")
        lines.append("    ; ====================================================================")
        lines.append("    ; SAFE KEY ATTRIBUTES (hasRequiredKey)")
        lines.append("    ; ====================================================================")
        lines.append("    ; Each safe has its required key as an attribute")
        
        # hasRequiredKey: each safe has its required key as an attribute
        for safe_id in sorted(requires_key_map.keys()):
            for key_id in sorted(requires_key_map[safe_id]):
                lines.append(f"    (hasRequiredKey {safe_id} {key_id})")

        lines.append("")
        lines.append("    ; ====================================================================")
        lines.append("    ; LOCKED STATES")
        lines.append("    ; ====================================================================")
        lines.append("    ; Safes with hasRequiredKey attribute are locked by default")
        
        # All safes that require a key are locked by default
        for safe_id in sorted(requires_key_map.keys()):
            lines.append(f"    (isLocked {safe_id})")

        return lines

    def generate_init(
        self,
        topology: Dict[str, Any],
        robot_info: Dict[str, Any],
        artifact_locs: Dict[str, Dict[str, str]],
        affordances_map: Dict[str, List[str]],
        door_states: Dict[str, bool] = None,
        key_safe_rels: Dict[str, Dict[str, List[str]]] = None,
        types_map: Dict[str, str] = None
    ) -> str:
        """
        Generate complete init section.

        Args:
            topology: Topology data
            robot_info: Robot data
            artifact_locs: Artifact location data
            affordances_map: Affordances data
            door_states: Door states data (optional)
            key_safe_rels: Key-safe relationships data (optional)
            types_map: Object types map (optional, for filtering Space->Space distances)

        Returns:
            PDDL init section string
        """
        lines = ["  (:init"]
        lines.append("    (= (total-cost) 0)")
        lines.append("")

        # Add all subsections
        lines.extend(self.generate_init_topology(topology, types_map))
        lines.append("")

        lines.extend(self.generate_init_robot(robot_info))
        lines.append("")

        lines.extend(self.generate_init_artifact_locations(artifact_locs))
        lines.append("")

        lines.extend(self.generate_init_affordances(affordances_map))
        
        if door_states:
            lines.append("")
            lines.extend(self.generate_init_door_states(door_states))

        if key_safe_rels:
            lines.append("")
            lines.extend(self.generate_init_key_safe_relationships(key_safe_rels))

        lines.append("  )")

        return "\n".join(lines)

    def generate_goal(self, goal_formula: str) -> str:
        """
        Generate goal section.

        Args:
            goal_formula: PDDL goal formula (user-provided)

        Returns:
            PDDL goal section string
        """
        # Indent goal formula properly
        goal_lines = goal_formula.strip().split('\n')
        indented = ["    " + line.strip() for line in goal_lines]

        return "  (:goal\n" + "\n".join(indented) + "\n  )"

    def write_problem(
        self,
        output_path: str,
        objects: Dict[str, str],
        topology: Dict[str, Any],
        robot_info: Dict[str, Any],
        artifact_locs: Dict[str, Dict[str, str]],
        affordances_map: Dict[str, List[str]],
        goal_formula: str,
        door_states: Dict[str, bool] = None,
        key_safe_rels: Dict[str, Dict[str, List[str]]] = None
    ):
        """
        Write complete PDDL problem file.

        Args:
            output_path: Path to output problem.pddl file
            objects: Object types map
            topology: Topology data
            robot_info: Robot data
            artifact_locs: Artifact location data
            affordances_map: Affordances data
            goal_formula: Goal formula string
            door_states: Door states data (optional)
            key_safe_rels: Key-safe relationships data (optional)
        """
        lines = []

        # Header
        lines.append(";; ====================================================================")
        lines.append(f";; PDDL Problem: {self.problem_name}")
        lines.append(";; Auto-generated from knowledge graph")
        lines.append(";; ====================================================================")
        lines.append("")

        # Problem definition
        lines.append(f"(define (problem {self.problem_name})")
        lines.append(f"  (:domain {self.domain_name})")
        lines.append("")

        # Objects
        lines.append(self.generate_objects(objects))
        lines.append("")

        # Init (pass objects as types_map for filtering Space->Space distances)
        lines.append(self.generate_init(topology, robot_info, artifact_locs, affordances_map, door_states, key_safe_rels, types_map=objects))
        lines.append("")

        # Goal
        lines.append(self.generate_goal(goal_formula))
        lines.append("")

        # Metric
        lines.append("  (:metric minimize (total-cost))")
        lines.append(")")

        # Write to file
        output_file = Path(output_path)
        output_file.write_text("\n".join(lines))

        print(f"Generated PDDL problem: {output_path}")


if __name__ == "__main__":
    # Test writer
    writer = PDDLWriter("test-problem", "robot")

    # Sample data
    objects = {
        "room1": "Space",
        "door1": "Door",
        "robot1": "Robot",
        "left_hand": "Hand",
        "right_hand": "Hand",
        "cup1": "Artifact",
        "table1": "Artifact"
    }

    topology = {
        "connections": [("room1", "door1")],
        "distances": {("room1", "door1"): 5, ("door1", "room1"): 5}
    }

    robot_info = {
        "robot_id": "robot1",
        "hands": ["left_hand", "right_hand"],
        "location": "room1"
    }

    artifact_locs = {
        "cup1": {"artifactIsOnFloorOf": "room1"},
        "table1": {"artifactIsOnFloorOf": "room1"}
    }

    affordances = {
        "cup1": ["Affordance_PickupOneHand"],
        "table1": ["Affordance_PlaceOn"]
    }

    goal = "(and\n  (isOntopOf cup1 table1)\n)"

    # Write test problem
    writer.write_problem(
        "test_problem.pddl",
        objects,
        topology,
        robot_info,
        artifact_locs,
        affordances,
        goal
    )

    print("\nGenerated test problem:")
    print(Path("test_problem.pddl").read_text())
