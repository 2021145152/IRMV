#!/usr/bin/env python3
"""PDDL Task Runner - Generate problem and execute planner."""

import sys
import yaml
import shutil
import subprocess
from pathlib import Path
from neo4j import GraphDatabase

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "ontology_server"))
sys.path.insert(0, str(project_root / "pddl"))

from scripts.pddl_parser import PDDLDomainParser
from scripts.pddl_generator import PDDLGenerator
from scripts.pddl_writer import PDDLWriter
from scripts.pddl_goal_utils import extract_object_ids_from_goal, classify_objects_by_domain_type
from core.config import get_config


def load_config(config_path: Path) -> dict:
    """Load task configuration from YAML file."""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def build_planner_command(planner_config: dict) -> str:
    """Build Fast Downward search command from planner config."""
    solver = planner_config.get('solver', 'lazy_wastar')
    heuristic = planner_config.get('heuristic', 'ff')
    weight = planner_config.get('weight', 2)

    if solver == 'lazy_wastar':
        return f"lazy_wastar([{heuristic}()], w={weight})"
    elif solver == 'astar':
        return f"astar({heuristic}())"
    elif solver == 'lama':
        return "lazy(alt([lama_synergy()], boost=1000), preferred=[lama_synergy()])"
    else:
        return f"lazy_wastar([{heuristic}()], w={weight})"


def main():
    """Main function to run PDDL task."""
    print("=" * 70)
    print("PDDL Task Runner")
    print("=" * 70)
    print()

    base_dir = Path(__file__).parent
    config_path = base_dir / "config.yaml"
    domain_path = base_dir / "domain.pddl"
    problem_dir = base_dir / "problem"
    solution_dir = base_dir / "solution"
    if not config_path.exists():
        print(f"ERROR: Config file not found: {config_path}")
        return 1

    if not domain_path.exists():
        print(f"ERROR: Domain file not found: {domain_path}")
        return 1
    print(f"Loading Loading configuration: {config_path.name}")
    config = load_config(config_path)

    task_name = config.get('task', 'unnamed-task')
    domain_name = config.get('domain', 'robot')
    goal_formula = config.get('goal', '(and)')
    additional_artifacts = config.get('additional_artifacts', [])
    additional_locations = config.get('additional_locations', [])
    planner_config = config.get('planner', {})

    print(f"  Task: {task_name}")
    print(f"  Domain: {domain_name}")
    print()

    print(f"Parsing Parsing domain: {domain_path.name}")
    parser = PDDLDomainParser(domain_path)
    print()

    print("Connecting Connecting to Neo4j...")
    sys_config = get_config()
    neo4j_config = sys_config.get_neo4j_config()
    driver = GraphDatabase.driver(
        neo4j_config['uri'],
        auth=(neo4j_config['user'], neo4j_config['password'])
    )
    print(" Connected to Neo4j")
    print()

    print("Initializing  Initializing PDDL generator...")
    generator = PDDLGenerator(driver, parser)
    print()

    print("Step Step 1: Extracting objects from goal...")
    goal_object_ids = extract_object_ids_from_goal(goal_formula, driver)
    print(f"  Objects in goal: {len(goal_object_ids)}")
    print(f"  IDs: {sorted(goal_object_ids)}")
    print()

    print("🏷️  Step 2: Mapping object types...")
    goal_types_map = generator.get_types(goal_object_ids)
    print(f"  Mapped types: {len(goal_types_map)}")
    print()

    print("📋 Step 3: Classifying objects by domain type...")
    artifact_ids, location_ids = classify_objects_by_domain_type(
        goal_object_ids, goal_types_map, parser
    )
    artifact_ids.extend(additional_artifacts)
    location_ids.extend(additional_locations)

    print(f"  Artifacts: {len(artifact_ids)}")
    print(f"  Locations (from goal): {len(location_ids)}")
    print()

    print("🤖 Step 4: Extracting robot structure...")
    robot_info = generator.get_robot_info()
    if robot_info:
        print(f"  Robot: {robot_info['robot_id']}")
        print(f"  Hands: {robot_info['hands']}")
        print(f"  Location: {robot_info['location']}")
        # Add robot location to location_ids
        if robot_info['location']:
            location_ids.append(robot_info['location'])
    else:
        print("  WARNING: No robot found in knowledge graph")
    print()

    print("Step Step 5: Finding artifact locations...")
    artifact_locs = generator.get_artifact_locations(artifact_ids)
    referenced_ids = [id for loc_info in artifact_locs.values() for id in loc_info.values()]
    if referenced_ids:
        referenced_types = generator.get_types(referenced_ids)
        location_ids.extend([
            obj_id for obj_id, obj_type in referenced_types.items()
            if obj_type == "Location" or parser.is_subtype_of(obj_type, "Location")
        ])
    location_ids = list(set(location_ids))
    print(f"  Locations: {len(location_ids)} (goal + artifact references + robot location)")
    print()

    print("Step Step 6: Expanding locations with shortest paths...")
    all_locations = generator.get_locations_with_paths(location_ids)
    print(f"  Initial locations: {len(location_ids)}")
    print(f"  Expanded locations: {len(all_locations)}")
    print()

    print("📦 Step 7: Collecting all required objects...")
    all_object_ids = generator.get_all_required_objects(artifact_ids, all_locations, artifact_locs)
    print(f"  Total objects: {len(all_object_ids)}")
    print()

    print("🔖 Step 8: Mapping all object types...")
    types_map = generator.get_types(all_object_ids)
    print(f"  Mapped types: {len(types_map)}")
    print()

    print("🗺️  Step 9: Building topology...")
    topology = generator.get_topology(all_locations)
    print(f"  Connections: {len(topology['connections'])}")
    print(f"  Distances: {len(topology['distances']) // 2} pairs")
    print()

    print("🔧 Step 10: Extracting affordances...")
    affordances_map = generator.get_affordances(artifact_ids)
    total_affordances = sum(len(affs) for affs in affordances_map.values())
    print(f"  Artifacts with affordances: {len(affordances_map)}")
    print(f"  Total affordances: {total_affordances}")
    print()

    print("🔐 Step 11: Extracting key-safe relationships...")
    key_safe_rels = generator.get_key_safe_relationships(artifact_ids)
    unlocks_count = sum(len(safes) for safes in key_safe_rels.get('unlocks', {}).values())
    requires_key_count = sum(len(keys) for keys in key_safe_rels.get('requiresKey', {}).values())
    print(f"  Unlocks relationships: {unlocks_count}")
    print(f"  RequiresKey relationships: {requires_key_count}")
    print()

    print("✍️  Generating PDDL problem file...")
    problem_path = problem_dir / f"{task_name}.pddl"
    writer = PDDLWriter(task_name, domain_name)
    writer.write_problem(
        problem_path,
        types_map,
        topology,
        robot_info,
        artifact_locs,
        affordances_map,
        goal_formula,
        door_states=None,  # Door states can be added if needed
        key_safe_rels=key_safe_rels
    )
    print()

    driver.close()
    print("Running Running Fast Downward planner...")
    search_cmd = build_planner_command(planner_config)
    print(f"  Solver: {planner_config.get('solver', 'lazy_wastar')}")
    print(f"  Search command: {search_cmd}")
    print()

    fd_path = base_dir / "fast-downward" / "fast-downward.py"
    if not fd_path.exists():
        print(f"ERROR: Fast Downward not found: {fd_path}")
        return 1

    solution_path = solution_dir / f"{task_name}.plan"
    sas_plan_path = base_dir / "sas_plan"

    try:
        result = subprocess.run(
            [
                "python", str(fd_path),
                str(domain_path),
                str(problem_path),
                "--search", search_cmd
            ],
            capture_output=True,
            text=True,
            cwd=base_dir
        )

        if result.returncode == 0:
            print("SUCCESS: Planning successful!")
            print()

            if sas_plan_path.exists():
                shutil.copy(sas_plan_path, solution_path)
                sas_plan_path.unlink()

            for line in result.stdout.split('\n'):
                if 'Plan length' in line or 'Plan cost' in line or 'Solution found' in line:
                    print(f"  {line.strip()}")

            print()
            print(f"📄 Problem file: {problem_path}")
            print(f"📄 Solution file: {solution_path}")

        else:
            print("ERROR: Planning failed!")
            print()
            print("Planner output:")
            print(result.stdout)
            if result.stderr:
                print("\nErrors:")
                print(result.stderr)
            return 1

    except Exception as e:
        print(f"ERROR: Error running planner: {e}")
        return 1

    print()
    print("=" * 70)
    print("SUCCESS: PDDL Task Complete")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
