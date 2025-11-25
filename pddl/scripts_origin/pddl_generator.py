#!/usr/bin/env python3
"""PDDL Generator - Extract PDDL problem data from Neo4j knowledge graph."""

from pathlib import Path
from typing import Dict, List, Any
from neo4j import GraphDatabase


class PDDLGenerator:
    """Generate PDDL problem data from Neo4j knowledge graph."""

    def __init__(self, driver, domain_parser):
        """
        Initialize PDDL generator.

        Args:
            driver: Neo4j driver instance
            domain_parser: PDDLDomainParser instance
        """
        self.driver = driver
        self.parser = domain_parser

    def get_types(self, ids: List[str]) -> Dict[str, str]:
        """Get domain types for given IDs - uses classes that match PDDL types."""
        types_map = {}
        pddl_types = set(self.parser.all_types)

        with self.driver.session() as session:
            result = session.run("""
                UNWIND $ids AS obj_id
                MATCH (n:Individual {id: obj_id})-[:INSTANCE_OF]->(c:Class)
                RETURN obj_id, collect(c.name) as class_names
            """, ids=ids)

            for record in result:
                obj_id = record["obj_id"]
                class_names = record["class_names"]

                # Find most specific class that matches a PDDL type
                # class_names are ordered from specific to general
                domain_type = None
                for class_name in class_names:
                    if class_name in pddl_types:
                        domain_type = class_name
                        break

                if domain_type:
                    types_map[obj_id] = domain_type
                else:
                    print(f"WARNING: Could not map {obj_id} with classes {class_names} to PDDL type")

        return types_map

    def get_robot_info(self) -> Dict[str, Any]:
        """Get robot and hand information."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (r:Robot)
                OPTIONAL MATCH (r)-[:hasHand]->(h:Hand)
                OPTIONAL MATCH (r)-[:robotIsInSpace]->(loc:Space)
                RETURN r.id as robot_id,
                       collect(DISTINCT h.id) as hands,
                       loc.id as location
                LIMIT 1
            """)

            record = result.single()
            if not record:
                return None

            return {
                "robot_id": record["robot_id"],
                "hands": record["hands"],
                "location": record["location"]
            }

    def get_topology_with_paths(self, location_ids: List[str]) -> Dict[str, Any]:
        """
        Get topology including all intermediate locations on shortest paths.

        Optimized: Single query to find connected subgraph and extract all hasPathTo relationships.

        Args:
            location_ids: Initial location IDs (from goal + robot location)

        Returns:
            Dict with 'locations' (expanded set), 'connections', and 'distances'
        """
        all_locations = set()
        connections = []
        distances = {}

        with self.driver.session() as session:
            if len(location_ids) == 1:
                # Single location: just get its immediate connections
                result = session.run("""
                    MATCH (n {id: $loc})-[:hasPathTo]-(m)
                    WHERE n:Space OR n:Door OR n:Stairs OR n:Opening
                    RETURN DISTINCT n.id as from_id, m.id as to_id
                """, loc=location_ids[0])
            else:
                # Multiple locations: find shortest paths and extract subgraph
                result = session.run("""
                    // Find all shortest paths between goal locations
                    WITH $locations as locs
                    UNWIND locs as loc1
                    UNWIND locs as loc2
                    WITH loc1, loc2 WHERE loc1 < loc2  // Avoid duplicates

                    MATCH (a {id: loc1}), (b {id: loc2})
                    WHERE (a:Space OR a:Door OR a:Stairs OR a:Opening)
                      AND (b:Space OR b:Door OR b:Stairs OR b:Opening)
                    MATCH p=shortestPath((a)-[:hasPathTo*]-(b))

                    WITH collect(nodes(p)) as all_paths

                    // Flatten to get all unique nodes
                    UNWIND all_paths as path_nodes
                    UNWIND path_nodes as node
                    WITH collect(DISTINCT node.id) as all_node_ids

                    // Get all hasPathTo relationships within this subgraph
                    UNWIND all_node_ids as nid
                    MATCH (n {id: nid})-[:hasPathTo]->(m)
                    WHERE m.id IN all_node_ids

                    RETURN DISTINCT n.id as from_id, m.id as to_id
                """, locations=location_ids)

            # Process results
            for record in result:
                from_id = record["from_id"]
                to_id = record["to_id"]

                all_locations.add(from_id)
                all_locations.add(to_id)

                # Add connection (avoid duplicates)
                if (from_id, to_id) not in connections and (to_id, from_id) not in connections:
                    connections.append((from_id, to_id))

                # Uniform edge cost
                distances[(from_id, to_id)] = 1
                distances[(to_id, from_id)] = 1

        return {
            "locations": all_locations,
            "connections": connections,
            "distances": distances
        }

    def get_artifact_locations(self, artifact_ids: List[str]) -> Dict[str, Dict[str, str]]:
        """
        Get location information for artifacts and all related containers/surfaces.

        Strategy:
        1. From goal artifacts, find root artifacts connected to Space via artifactIsOnFloorOf
        2. From each root, extract all isInsideOf/isOntopOf relationships downward
        3. Returns all artifacts and their location relationships

        Args:
            artifact_ids: Initial artifact IDs from goal

        Returns:
            Dict mapping artifact_id to location relationships
        """
        locations_map = {}

        with self.driver.session() as session:
            # One query to get everything:
            # 1. Find roots (artifacts on floor of Space)
            # 2. Get all artifacts under those roots
            # 3. Get their location relationships
            result = session.run("""
                UNWIND $goal_ids AS goal_id
                // Find root: go up from goal to artifact on floor
                MATCH (goal:Artifact {id: goal_id})-[:isInsideOf|isOntopOf*0..]->(root:Artifact)
                      -[:artifactIsOnFloorOf]->(space:Space)

                WITH collect(DISTINCT root) as roots

                // From each root, go down to get all artifacts
                UNWIND roots as root
                MATCH (root)<-[:isInsideOf|isOntopOf*0..]-(artifact:Artifact)

                // Get location relationships for each artifact
                OPTIONAL MATCH (artifact)-[r]->(target)
                WHERE type(r) IN ['isInsideOf', 'isOntopOf', 'artifactIsOnFloorOf']
                  AND (target:Artifact OR target:Space)

                RETURN DISTINCT artifact.id as artifact_id,
                                type(r) as rel_type,
                                target.id as target_id
            """, goal_ids=artifact_ids)

            # Organize by artifact
            for record in result:
                artifact_id = record["artifact_id"]
                rel_type = record["rel_type"]
                target_id = record["target_id"]

                if artifact_id not in locations_map:
                    locations_map[artifact_id] = {}

                # Store only if relationship exists
                if rel_type and target_id:
                    locations_map[artifact_id][rel_type] = target_id

        return locations_map

    def get_affordances(self, artifact_ids: List[str]) -> Dict[str, List[str]]:
        """Get affordances for artifacts."""
        affordances_map = {}

        with self.driver.session() as session:
            result = session.run("""
                UNWIND $ids AS artifact_id
                MATCH (a:Artifact {id: artifact_id})-[:affords]->(aff:Individual)
                RETURN artifact_id, collect(aff.id) as affordance_ids
            """, ids=artifact_ids)

            for record in result:
                artifact_id = record["artifact_id"]
                affordances = record["affordance_ids"]
                if affordances:
                    affordances_map[artifact_id] = affordances

        return affordances_map

    def get_all_required_objects(
        self,
        artifact_locs: Dict[str, Dict[str, str]],
        topology_result: Dict[str, Any]
    ) -> List[str]:
        """
        Collect all object IDs needed (artifacts, locations, robot, hands).

        Args:
            artifact_locs: Artifact location map (already includes all artifacts in chain)
            topology_result: Topology with expanded locations

        Returns:
            Sorted list of all object IDs
        """
        all_ids = set()

        # Add all artifacts from location chain
        all_ids.update(artifact_locs.keys())

        # Add all targets from artifact locations (containers, surfaces, spaces)
        for loc_info in artifact_locs.values():
            all_ids.update(loc_info.values())

        # Add all locations from topology
        all_ids.update(topology_result["locations"])

        # Add robot and hands
        robot_info = self.get_robot_info()
        if robot_info:
            all_ids.add(robot_info["robot_id"])
            all_ids.update(robot_info["hands"])

        return sorted(all_ids)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    from pddl.scripts.pddl_parser import PDDLDomainParser
    from ontology_server.core.config import get_config

    domain_path = Path(__file__).parent.parent / "domain.pddl"
    parser = PDDLDomainParser(domain_path)

    config = get_config()
    neo4j_config = config.get_neo4j_config()
    driver = GraphDatabase.driver(
        neo4j_config['uri'],
        auth=(neo4j_config['user'], neo4j_config['password'])
    )

    generator = PDDLGenerator(driver, parser)

    print("\n" + "=" * 60)
    print("PDDL Generator Test - Optimized Version")
    print("=" * 60)

    # Test get_types
    test_ids = ["robot1", "left_hand"]
    types = generator.get_types(test_ids)
    print(f"\nTypes:")
    for id, type in types.items():
        print(f"  {id}: {type}")

    # Test robot info
    robot_info = generator.get_robot_info()
    print(f"\nRobot info: {robot_info}")

    # Test artifact locations (with automatic chain expansion)
    # Find some real artifacts first
    with driver.session() as session:
        result = session.run("""
            MATCH (a:Artifact)-[:isInsideOf|isOntopOf]->(container:Artifact)
            RETURN a.id as artifact_id
            LIMIT 2
        """)
        test_artifacts = [r["artifact_id"] for r in result]

    if test_artifacts:
        print(f"\nTesting artifact location chain for: {test_artifacts}")
        artifact_locs = generator.get_artifact_locations(test_artifacts)
        print(f"Found {len(artifact_locs)} artifacts in chain:")
        for id, loc in artifact_locs.items():
            print(f"  {id}: {loc}")

        # Test affordances
        affordances = generator.get_affordances(list(artifact_locs.keys()))
        print(f"\nAffordances for artifacts in chain:")
        for id, affs in affordances.items():
            print(f"  {id}: {affs}")

    # Test topology with paths (optimized single query)
    if robot_info and robot_info['location']:
        test_locations = [robot_info['location']]
        print(f"\nTesting topology expansion from: {test_locations}")
        topology = generator.get_topology_with_paths(test_locations)
        print(f"Expanded to {len(topology['locations'])} locations")
        print(f"Connections: {len(topology['connections'])} pairs")
        print(f"Sample distances: {list(topology['distances'].items())[:5]}")

    driver.close()
