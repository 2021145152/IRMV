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

    def generate_init_topology(self, topology: Dict[str, Any]) -> List[str]:
        """
        Generate topology section of init.

        Args:
            topology: Dict with 'connections' and 'distances'

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
            lines.append("    ; DISTANCES")
            lines.append("    ; ====================================================================")

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

        Returns:
            List of PDDL init statements
        """
        lines = []

        lines.append("    ; ====================================================================")
        lines.append("    ; ARTIFACT LOCATIONS")
        lines.append("    ; ====================================================================")

        for artifact_id in sorted(artifact_locs.keys()):
            loc_info = artifact_locs[artifact_id]

            # Record all location relationships
            for rel_type, target_id in sorted(loc_info.items()):
                lines.append(f"    ({rel_type} {artifact_id} {target_id})")

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

    def generate_init(
        self,
        topology: Dict[str, Any],
        robot_info: Dict[str, Any],
        artifact_locs: Dict[str, Dict[str, str]],
        affordances_map: Dict[str, List[str]]
    ) -> str:
        """
        Generate complete init section.

        Args:
            topology: Topology data
            robot_info: Robot data
            artifact_locs: Artifact location data
            affordances_map: Affordances data

        Returns:
            PDDL init section string
        """
        lines = ["  (:init"]
        lines.append("    (= (total-cost) 0)")
        lines.append("")

        # Add all subsections
        lines.extend(self.generate_init_topology(topology))
        lines.append("")

        lines.extend(self.generate_init_robot(robot_info))
        lines.append("")

        lines.extend(self.generate_init_artifact_locations(artifact_locs))
        lines.append("")

        lines.extend(self.generate_init_affordances(affordances_map))

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
        goal_formula: str
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

        # Init
        lines.append(self.generate_init(topology, robot_info, artifact_locs, affordances_map))
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
        "cup1": {"isInSpace": "room1"},
        "table1": {"isInSpace": "room1"}
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
