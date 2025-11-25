#!/usr/bin/env python3
"""PDDL Generator - Extract PDDL problem data from Neo4j knowledge graph."""

import math
from pathlib import Path
from typing import Dict, List, Set, Any
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
        self._types_cache = {}  # Cache for type lookups to avoid redundant queries

    def get_types(self, ids: List[str]) -> Dict[str, str]:
        """Get domain types for given IDs.
        
        Checks both:
        1. Node labels (e.g., :Door, :Opening, :Stairs, :Space)
        2. INSTANCE_OF relationships to Class nodes
        
        Uses caching to avoid redundant queries for the same IDs.
        """
        types_map = {}
        
        # Check cache first
        uncached_ids = [obj_id for obj_id in ids if obj_id not in self._types_cache]
        
        if not uncached_ids:
            # All IDs are in cache
            return {obj_id: self._types_cache[obj_id] for obj_id in ids if obj_id in self._types_cache}
        
        # Query only uncached IDs
        with self.driver.session() as session:
            result = session.run("""
                UNWIND $ids AS obj_id
                MATCH (n {id: obj_id})
                OPTIONAL MATCH (n)-[:INSTANCE_OF]->(c:Class)
                RETURN obj_id, 
                       labels(n) as node_labels,
                       collect(DISTINCT c.name) as class_names
            """, ids=uncached_ids)

            for record in result:
                obj_id = record["obj_id"]
                node_labels = record["node_labels"] or []
                class_names = record["class_names"] or []
                
                # Combine node labels and class names
                # Node labels are more direct (e.g., :Door, :Opening, :Stairs, :Space)
                all_type_candidates = list(set(node_labels + class_names))
                
                # Remove non-domain labels (Individual, Environment, etc.)
                # But keep Space, Door, Stairs, Opening even if not in parser.get_all_types()
                # because these are the actual domain types we need
                domain_types_in_parser = self.parser.get_all_types()
                domain_labels = [label for label in all_type_candidates 
                               if label in domain_types_in_parser]
                
                # Also check for direct Space, Door, Stairs, Opening labels (case-insensitive)
                direct_type_labels = ["Space", "Door", "Stairs", "Opening"]
                for direct_type in direct_type_labels:
                    if direct_type in node_labels:
                        types_map[obj_id] = direct_type
                        break
                else:
                    # If no direct type label found, check domain_labels
                    if domain_labels:
                        # Prioritize most specific types: Door, Stairs, Opening, Space (leaf nodes in hierarchy)
                        # These are more specific than Portal or Environment
                        priority_types = ["Door", "Stairs", "Opening", "Space"]
                        for priority_type in priority_types:
                            if priority_type in domain_labels:
                                types_map[obj_id] = priority_type
                                break
                        else:
                            # If no leaf type found, use map_class_to_domain_type to find most specific
                            domain_type = self.parser.map_class_to_domain_type(domain_labels)
                            if domain_type:
                                types_map[obj_id] = domain_type
                            else:
                                # Last resort: use first domain label
                                types_map[obj_id] = domain_labels[0]
                    else:
                        # Fallback: try to infer from labels even if not in domain types
                        # Check for common patterns (case-insensitive)
                        all_labels_lower = [label.lower() for label in node_labels]
                        if any("door" in label for label in all_labels_lower):
                            types_map[obj_id] = "Door"
                        elif any("stair" in label for label in all_labels_lower):
                            types_map[obj_id] = "Stairs"
                        elif any("opening" in label for label in all_labels_lower):
                            types_map[obj_id] = "Opening"
                        elif any("space" in label for label in all_labels_lower):
                            types_map[obj_id] = "Space"
                        elif class_names:
                            # Last resort: try class names
                            domain_type = self.parser.map_class_to_domain_type(class_names)
                            if domain_type:
                                types_map[obj_id] = domain_type
        
        # Update cache with newly queried types
        self._types_cache.update(types_map)
        
        # Return all requested IDs (from cache + newly queried)
        result_map = {}
        for obj_id in ids:
            if obj_id in self._types_cache:
                result_map[obj_id] = self._types_cache[obj_id]
        
        return result_map

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

    def get_locations_with_paths(self, location_ids: List[str], robot_location: str = None, artifact_pairs: set = None):
        """
        Expand location set to include all intermediate locations on shortest paths.
        Also returns distances found during path exploration to avoid redundant queries.
        
        Strategy: Find shortest paths between ALL pairs of necessary locations
        - This ensures we don't miss any important paths
        - Example: If goal has (robotIsInSpace robot space1), (isHeldBy artifact1 hand), (artifactIsOnFloorOf artifact2 space3)
          We need paths between: robot <-> space1, robot <-> artifact1_loc, robot <-> space3, space1 <-> artifact1_loc, etc.
        
        Args:
            location_ids: List of location IDs (should include robot location and all target locations)
            robot_location: Optional robot location ID (for logging/debugging)
            artifact_pairs: Set of tuples (loc1, loc2) representing additional artifact location pairs that need paths
                           (e.g., from goal relationships like isOntopOf, isInsideOf)
        
        Returns:
            Tuple of (all_location_ids, distances_dict) where:
            - all_location_ids: Set of all location IDs including intermediate locations on paths
            - distances_dict: Dict mapping (loc1, loc2) -> distance (path length)
        """
        all_locations = set(location_ids)
        distances = {}  # Store distances found during path exploration

        if len(location_ids) < 2:
            return all_locations, distances

        # Strategy: Find shortest paths between ALL pairs of necessary locations
        # This ensures completeness - we find all paths between:
        # - Robot location <-> Goal locations
        # - Robot location <-> Artifact locations
        # - Goal locations <-> Artifact locations
        # - Artifact locations <-> Artifact locations (if needed)
        print(f"  Finding shortest paths between all {len(location_ids)} necessary locations...")
        print(f"  Locations: {sorted(location_ids)}")
        
        # Add artifact pairs to location_ids if not already present
        if artifact_pairs:
            for loc1, loc2 in artifact_pairs:
                if loc1 not in all_locations:
                    all_locations.add(loc1)
                if loc2 not in all_locations:
                    all_locations.add(loc2)
        
        location_list = sorted(all_locations)
        total_pairs = len(location_list) * (len(location_list) - 1) // 2
        print(f"  Total pairs to check: {total_pairs} (nC2 where n={len(location_list)})")
        
        # Generate all pairs for batch processing
        pairs = []
        for i, loc1 in enumerate(location_list):
            for loc2 in location_list[i+1:]:
                pairs.append({"loc1": loc1, "loc2": loc2})
        
        with self.driver.session() as session:
            # Batch process: Find all shortest paths in one query using UNWIND
            # When we find a path, we extract distances for ALL pairs in that path
            result = session.run("""
                UNWIND $pairs AS pair
                MATCH (a {id: pair.loc1}), (b {id: pair.loc2})
                WHERE (a:Space OR a:Door OR a:Stairs OR a:Opening)
                  AND (b:Space OR b:Door OR b:Stairs OR b:Opening)
                OPTIONAL MATCH p = shortestPath((a)-[:hasPathTo*1..50]-(b))
                OPTIONAL MATCH direct = (a)-[:hasPathTo]-(b)
                RETURN pair.loc1 AS loc1,
                       pair.loc2 AS loc2,
                       CASE WHEN p IS NOT NULL THEN [n in nodes(p) | n.id] ELSE null END AS path_nodes,
                       CASE WHEN p IS NOT NULL THEN length(p) ELSE null END AS path_length,
                       CASE WHEN direct IS NOT NULL THEN true ELSE false END AS has_direct_connection
            """, pairs=pairs)
            
            paths_found = 0
            direct_connections = 0
            no_paths = 0
            
            for record in result:
                loc1 = record["loc1"]
                loc2 = record["loc2"]
                path_nodes = record["path_nodes"]
                path_length = record["path_length"]
                has_direct = record["has_direct_connection"]
                
                if path_nodes and path_length is not None:
                    # Found path: extract distances for ALL pairs in this path
                    # Example: path [a, x, y, b] gives us:
                    # - a-x: 1, x-y: 1, y-b: 1 (direct edges)
                    # - a-y: 2, a-b: 3, x-b: 2 (subpaths)
                    all_locations.update(path_nodes)
                    
                    # Store distance for the full path
                    distances[(loc1, loc2)] = int(path_length)
                    distances[(loc2, loc1)] = int(path_length)
                    
                    # Extract distances for all pairs in the path
                    # For path [a, x, y, b] with indices [0, 1, 2, 3]:
                    # - distance between indices i and j = |j - i|
                    for i, node1 in enumerate(path_nodes):
                        for j, node2 in enumerate(path_nodes[i+1:], start=i+1):
                            subpath_distance = j - i
                            if (node1, node2) not in distances:
                                distances[(node1, node2)] = subpath_distance
                            if (node2, node1) not in distances:
                                distances[(node2, node1)] = subpath_distance
                    
                    paths_found += 1
                    if paths_found <= 5:
                        print(f"  ✓ Path {paths_found}: {loc1} <-> {loc2} (length {path_length}): {' -> '.join(path_nodes)}")
                elif has_direct:
                    # Direct connection (distance = 1)
                    distances[(loc1, loc2)] = 1
                    distances[(loc2, loc1)] = 1
                    direct_connections += 1
                    if direct_connections <= 3:
                        print(f"  ✓ Direct connection: {loc1} <-> {loc2}")
                else:
                    no_paths += 1
                    if no_paths <= 3:
                        print(f"  ✗ No path: {loc1} <-> {loc2}")
            
            if paths_found > 5:
                print(f"  ... and {paths_found - 5} more paths")
            if direct_connections > 3:
                print(f"  ... and {direct_connections - 3} more direct connections")
            if no_paths > 3:
                print(f"  ... and {no_paths - 3} more pairs with no path")
            
            print(f"  Summary: {paths_found} paths found, {direct_connections} direct connections, {no_paths} no paths")
            print(f"  Extracted {len(distances)} total distances (including subpath distances)")

        print(f"  Final location set ({len(all_locations)} locations): {sorted(all_locations)[:10]}..." if len(all_locations) > 10 else f"  Final location set ({len(all_locations)} locations): {sorted(all_locations)}")
        print(f"  Found {len(distances)} distances during path exploration (can be reused)")
        return all_locations, distances

    def get_topology(self, location_ids: Set[str], types_map: Dict[str, str] = None, precomputed_distances: Dict[tuple[str, str], int] = None) -> Dict[str, Any]:
        """
        Extract topology with hasPathTo relationships.
        
        Args:
            location_ids: Set of location IDs
            types_map: Optional dict mapping location_id to type (for filtering Space->Space distances)
            precomputed_distances: Optional dict of precomputed distances from get_locations_with_paths
                                  Format: {(loc1, loc2): distance, ...}
        
        Returns:
            Dict with 'connections' (all hasPathTo) and 'distances' (all Location->Location)
        """
        connections = []
        distances = {}
        
        if not location_ids:
            print("  ⚠️  WARNING: No locations provided for topology extraction")
            return {
                "connections": connections,
                "distances": distances
            }

        print(f"  Extracting topology for {len(location_ids)} locations...")

        with self.driver.session() as session:
            # Get all hasPathTo relationships between locations in the set
            # This includes Space->Portal, Portal->Space, and any other connections
            result = session.run("""
                MATCH (a)-[:hasPathTo]->(b)
                WHERE a.id IN $all_locs
                  AND b.id IN $all_locs
                  AND a.id <> b.id
                RETURN DISTINCT a.id as from_id, b.id as to_id
                ORDER BY a.id, b.id
            """, all_locs=list(location_ids))

            connection_count = 0
            for record in result:
                from_id = record["from_id"]
                to_id = record["to_id"]

                # Avoid duplicates (both directions)
                if (from_id, to_id) not in connections and (to_id, from_id) not in connections:
                    connections.append((from_id, to_id))
                    connection_count += 1

                # Store edge distances for graph building (used for Space->Space calculation)
                # Use uniform edge cost (edge count = 1 per edge)
                distances[(from_id, to_id)] = 1
                distances[(to_id, from_id)] = 1

            print(f"  ✓ Found {connection_count} unique connections (total {len(distances)} directed edges)")

        if not connections:
            print("  ⚠️  WARNING: No hasPathTo relationships found! This will cause planning to fail.")
            print(f"     Locations searched: {sorted(location_ids)}")
            # Try to find any hasPathTo relationships involving these locations
            with self.driver.session() as session:
                debug_result = session.run("""
                    MATCH (a)-[:hasPathTo]->(b)
                    WHERE a.id IN $all_locs OR b.id IN $all_locs
                    RETURN a.id as from_id, b.id as to_id
                    LIMIT 10
                """, all_locs=list(location_ids))
                debug_connections = list(debug_result)
                if debug_connections:
                    print(f"     Found {len(debug_connections)} hasPathTo relationships involving these locations (but not between them):")
                    for conn in debug_connections[:5]:
                        print(f"       {conn['from_id']} -> {conn['to_id']}")

        # Calculate distances only for directly connected pairs (hasPathTo)
        # Since move action only moves between directly connected locations,
        # we only need distances for hasPathTo pairs, not all pairs
        location_to_location_distances = {}
        
        # Use precomputed distances from path exploration (these are shortest path distances)
        if precomputed_distances:
            print(f"  Using {len(precomputed_distances)} precomputed distances from path exploration")
            location_to_location_distances.update(precomputed_distances)
        
        # Add distances for direct hasPathTo connections (edge distance = 1)
        # These are already in connections, so we can add them directly
        for from_id, to_id in connections:
            # Only add if not already in precomputed_distances
            if (from_id, to_id) not in location_to_location_distances:
                location_to_location_distances[(from_id, to_id)] = 1
            if (to_id, from_id) not in location_to_location_distances:
                location_to_location_distances[(to_id, from_id)] = 1
        
        print(f"  ✓ Total {len(location_to_location_distances)} Location->Location distances")
        print(f"     - {len(precomputed_distances) if precomputed_distances else 0} from path exploration (shortest paths)")
        print(f"     - {len(connections) * 2} from direct hasPathTo connections (distance = 1)")
        
        distances = location_to_location_distances

        return {
            "connections": connections,
            "distances": distances
        }

    def get_artifact_locations(self, artifact_ids: List[str]) -> Dict[str, Dict[str, str]]:
        """
        Get location information for artifacts using Neo4j relationships.
        Since input is artifacts, we only check artifact -> space relationships:
        - isInSpace: Artifact -> Space
        - objectIsInSpace: Artifact -> Space
        - isInsideOf: Artifact -> Artifact
        - isOntopOf: Artifact -> Artifact

        Args:
            artifact_ids: Initial artifact IDs from goal

        Returns:
            Dict mapping artifact_id to location relationships
        """
        locations_map = {}

        with self.driver.session() as session:
            # Query: Check artifact -> space relationships only
            result = session.run("""
                UNWIND $goal_ids AS goal_id
                MATCH (artifact {id: goal_id})
                
                // 1. Direct artifact -> space relationships
                OPTIONAL MATCH (artifact)-[:isInSpace|objectIsInSpace]->(space:Space)
                
                // 2. Artifact -> artifact relationships (containers/surfaces)
                OPTIONAL MATCH (artifact)-[:isInsideOf]->(container)
                OPTIONAL MATCH (artifact)-[:isOntopOf]->(surface)
                
                // 3. Check if artifact is inside/on top of another artifact that has location
                OPTIONAL MATCH (artifact)-[:isInsideOf|isOntopOf*1..]->(parent)-[:isInSpace|objectIsInSpace]->(parent_location:Space)
                
                RETURN DISTINCT goal_id as artifact_id,
                                space.id as isInSpace,
                                container.id as isInsideOf,
                                surface.id as isOntopOf,
                                parent_location.id as parent_location
            """, goal_ids=artifact_ids)

            # Organize by artifact
            for record in result:
                artifact_id = record["artifact_id"]
                
                if artifact_id not in locations_map:
                    locations_map[artifact_id] = {}
                
                # Store all found relationships
                if record["isInSpace"]:
                    locations_map[artifact_id]["isInSpace"] = record["isInSpace"]
                if record["isInsideOf"]:
                    locations_map[artifact_id]["isInsideOf"] = record["isInsideOf"]
                if record["isOntopOf"]:
                    locations_map[artifact_id]["isOntopOf"] = record["isOntopOf"]
                if record["parent_location"]:
                    # If artifact is inside/on top of another artifact, use parent's location
                    if "isInSpace" not in locations_map[artifact_id]:
                        locations_map[artifact_id]["isInSpace"] = record["parent_location"]
            
            # Fallback: If any goal artifact is missing location, try without label constraints
            missing_artifacts = set(artifact_ids) - set(locations_map.keys())
            if missing_artifacts:
                print(f"  ⚠️  WARNING: {len(missing_artifacts)} artifacts missing from initial query: {list(missing_artifacts)[:5]}")
                
                # Try more flexible query without label constraints
                fallback_result = session.run("""
                    UNWIND $artifact_ids AS artifact_id
                    MATCH (artifact {id: artifact_id})
                    
                    // Check artifact -> space relationships only
                    OPTIONAL MATCH (artifact)-[r]->(target)
                    WHERE type(r) IN ['isInSpace', 'objectIsInSpace', 'isInsideOf', 'isOntopOf']
                    
                    RETURN artifact_id,
                           type(r) as rel_type,
                           target.id as target_id
                """, artifact_ids=list(missing_artifacts))
                
                for record in fallback_result:
                    artifact_id = record["artifact_id"]
                    
                    if artifact_id not in locations_map:
                        locations_map[artifact_id] = {}
                    
                    # Store relationships
                    if record["rel_type"] and record["target_id"]:
                        rel_type = record["rel_type"]
                        target_id = record["target_id"]
                        locations_map[artifact_id][rel_type] = target_id
                
                # Final check: If still missing, report error
                still_missing = set(artifact_ids) - set(locations_map.keys())
                if still_missing:
                    print(f"  ❌ ERROR: {len(still_missing)} artifacts still have no location in Neo4j: {list(still_missing)[:5]}")
                    # Check if artifacts exist in Neo4j
                    existence_check = session.run("""
                        UNWIND $artifact_ids AS artifact_id
                        OPTIONAL MATCH (n {id: artifact_id})
                        RETURN artifact_id, n IS NOT NULL as exists, labels(n) as node_labels
                    """, artifact_ids=list(still_missing))
                    
                    for record in existence_check:
                        artifact_id = record["artifact_id"]
                        exists = record["exists"]
                        labels = record["node_labels"]
                        if exists:
                            print(f"     - {artifact_id} exists with labels: {labels}, but has no location relationships")
                        else:
                            print(f"     - {artifact_id} does NOT exist in Neo4j!")

        return locations_map

    def get_affordances(self, artifact_ids: List[str]) -> Dict[str, List[str]]:
        """Get affordances for artifacts."""
        affordances_map = {}

        with self.driver.session() as session:
            result = session.run("""
                UNWIND $ids AS artifact_id
                MATCH (a:Individual {id: artifact_id})-[:INSTANCE_OF]->(:Class {name: "Artifact"})
                MATCH (a)-[:affords]->(aff:Individual)
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
        artifact_ids: List[str],
        location_ids: Set[str],
        artifact_locs: Dict[str, Dict[str, str]] = None
    ) -> List[str]:
        """Collect all object IDs needed (artifacts, locations, robot, hands)."""
        all_ids = set(artifact_ids)
        all_ids.update(location_ids)

        robot_info = self.get_robot_info()
        if robot_info:
            all_ids.add(robot_info["robot_id"])
            all_ids.update(robot_info["hands"])

        if artifact_locs is None:
            artifact_locs = self.get_artifact_locations(artifact_ids)

        for loc_info in artifact_locs.values():
            all_ids.update(loc_info.values())

        return sorted(all_ids)

    def get_door_states(self, door_ids: List[str]) -> Dict[str, bool]:
        """
        Get door states (isOpenDoor) from Neo4j.
        
        Args:
            door_ids: List of door IDs
            
        Returns:
            Dictionary mapping door_id to isOpenDoor boolean value
        """
        door_states = {}
        
        if not door_ids:
            return door_states
        
        with self.driver.session() as session:
            # Find Door nodes - check both Door label and INSTANCE_OF relationship
            result = session.run("""
                UNWIND $ids AS door_id
                MATCH (d {id: door_id})
                WHERE d:Door OR (d:Individual AND (d)-[:INSTANCE_OF]->(:Class {name: "Door"}))
                RETURN door_id, 
                       d.isOpenDoor as is_open,
                       labels(d) as labels,
                       keys(d) as properties
            """, ids=door_ids)
            
            found_doors = []
            for record in result:
                door_id = record["door_id"]
                is_open = record["is_open"]
                labels = record["labels"]
                properties = record["properties"]
                found_doors.append(door_id)
                
                # Handle boolean or string values
                if is_open is None:
                    is_open = False
                elif isinstance(is_open, str):
                    is_open = is_open.lower() in ("true", "1", "yes")
                door_states[door_id] = bool(is_open)
            
            missing_doors = set(door_ids) - set(found_doors)
            if missing_doors:
                print(f"  ⚠️  WARNING: {len(missing_doors)} doors not found in Neo4j: {list(missing_doors)[:5]}")
            if found_doors:
                print(f"  ✓ Found {len(found_doors)} doors with states: {dict(list(door_states.items())[:3])}")
            else:
                print(f"  ⚠️  WARNING: No doors found in Neo4j for IDs: {door_ids[:5]}")
        
        return door_states

    def get_key_safe_relationships(self, artifact_ids: List[str]) -> Dict[str, Dict[str, List[str]]]:
        """
        Get key-safe relationships (unlocks, requiresKey) from Neo4j.
        
        Args:
            artifact_ids: List of artifact IDs (keys and safes)
            
        Returns:
            Dictionary with 'unlocks' and 'requiresKey' mappings
            {
                'unlocks': {key_id: [safe_id, ...], ...},
                'requiresKey': {safe_id: [key_id, ...], ...}
            }
        """
        unlocks_map = {}
        requires_key_map = {}
        
        if not artifact_ids:
            return {'unlocks': unlocks_map, 'requiresKey': requires_key_map}
        
        with self.driver.session() as session:
            # Get requiresKey relationships (safe -> key) FIRST
            # This is important: we need to find safes that require keys, even if keys aren't in artifact_ids yet
            # Note: Nodes are stored as :Individual, Artifact class is via INSTANCE_OF
            # Query for ANY safe in artifact_ids that has a requiresKey relationship
            # Use direct MATCH instead of OPTIONAL MATCH to ensure we only get relationships that exist
            result = session.run("""
                UNWIND $ids AS artifact_id
                MATCH (s:Individual {id: artifact_id})-[:INSTANCE_OF]->(:Class {name: "Artifact"})
                MATCH (s)-[:requiresKey]->(k:Individual)-[:INSTANCE_OF]->(:Class {name: "Artifact"})
                RETURN artifact_id as safe_id, k.id as key_id
            """, ids=artifact_ids)
            
            requires_key_count = 0
            for record in result:
                safe_id = record["safe_id"]
                key_id = record["key_id"]
                if safe_id and key_id:
                    if safe_id not in requires_key_map:
                        requires_key_map[safe_id] = []
                    requires_key_map[safe_id].append(key_id)
                    requires_key_count += 1
            
            if requires_key_count > 0:
                print(f"  Found {requires_key_count} requiresKey relationships")
            
            # Get unlocks relationships (key -> safe) - forward direction
            # Note: Nodes are stored as :Individual, Artifact class is via INSTANCE_OF
            # Query for ANY key in artifact_ids that has an unlocks relationship
            # Use direct MATCH instead of OPTIONAL MATCH to ensure we only get relationships that exist
            result = session.run("""
                UNWIND $ids AS artifact_id
                MATCH (k:Individual {id: artifact_id})-[:INSTANCE_OF]->(:Class {name: "Artifact"})
                MATCH (k)-[:unlocks]->(s:Individual)-[:INSTANCE_OF]->(:Class {name: "Artifact"})
                RETURN artifact_id as key_id, s.id as safe_id
            """, ids=artifact_ids)
            
            unlocks_count = 0
            for record in result:
                key_id = record["key_id"]
                safe_id = record["safe_id"]
                if key_id and safe_id:
                    if key_id not in unlocks_map:
                        unlocks_map[key_id] = []
                    unlocks_map[key_id].append(safe_id)
                    unlocks_count += 1
            
            # Get unlocks relationships (key -> safe) - REVERSE direction
            # If a safe is in artifact_ids, find keys that unlock it (even if key is not in artifact_ids yet)
            # This is important: if safe_214 is in artifact_ids but key_215 is not, we need to find key_215
            result = session.run("""
                UNWIND $ids AS artifact_id
                MATCH (s:Individual {id: artifact_id})-[:INSTANCE_OF]->(:Class {name: "Artifact"})
                MATCH (k:Individual)-[:INSTANCE_OF]->(:Class {name: "Artifact"})
                MATCH (k)-[:unlocks]->(s)
                RETURN artifact_id as safe_id, k.id as key_id
            """, ids=artifact_ids)
            
            reverse_unlocks_count = 0
            for record in result:
                safe_id = record["safe_id"]
                key_id = record["key_id"]
                if safe_id and key_id:
                    # Add to unlocks_map (key unlocks safe)
                    if key_id not in unlocks_map:
                        unlocks_map[key_id] = []
                    if safe_id not in unlocks_map[key_id]:
                        unlocks_map[key_id].append(safe_id)
                        reverse_unlocks_count += 1
                    
                    # Also add to requiresKey_map (safe requires key) - inferred from unlocks relationship
                    if safe_id not in requires_key_map:
                        requires_key_map[safe_id] = []
                    if key_id not in requires_key_map[safe_id]:
                        requires_key_map[safe_id].append(key_id)
            
            if reverse_unlocks_count > 0:
                print(f"  Found {reverse_unlocks_count} unlocks relationships (reverse direction)")
            
            if unlocks_count > 0 or reverse_unlocks_count > 0:
                print(f"  Total unlocks relationships: {unlocks_count + reverse_unlocks_count}")
        
        # Debug output
        if artifact_ids and (not unlocks_map and not requires_key_map):
            print(f"⚠️  WARNING: No key-safe relationships found for {len(artifact_ids)} artifacts")
            print(f"   Searched artifact_ids: {artifact_ids[:5]}{'...' if len(artifact_ids) > 5 else ''}")
        
        return {
            'unlocks': unlocks_map,
            'requiresKey': requires_key_map
        }
    
    def get_artifact_states(self, artifact_ids: List[str]) -> Dict[str, Dict[str, bool]]:
        """
        Get artifact states (isOpen, isLocked) from Neo4j.
        
        Args:
            artifact_ids: List of artifact IDs
            
        Returns:
            Dictionary mapping artifact_id to state dict
            {
                'artifact_id': {
                    'isOpen': bool,
                    'isLocked': bool
                }
            }
        """
        states_map = {}
        
        if not artifact_ids:
            return states_map
        
        with self.driver.session() as session:
            # Get isOpen and isLocked states
            result = session.run("""
                UNWIND $ids AS artifact_id
                MATCH (a:Individual {id: artifact_id})-[:INSTANCE_OF]->(:Class {name: "Artifact"})
                OPTIONAL MATCH (a)-[:hasPropertyValue]->(pv:PropertyValue)
                WHERE pv.propertyName IN ['isOpen', 'isLocked']
                RETURN artifact_id, 
                       collect({name: pv.propertyName, value: pv.value}) as properties
            """, ids=artifact_ids)
            
            for record in result:
                artifact_id = record["artifact_id"]
                properties = record["properties"] or []
                
                states = {}
                for prop in properties:
                    if prop and prop.get("name") and prop.get("value"):
                        prop_name = prop["name"]
                        prop_value = prop["value"]
                        # Convert string to boolean
                        if isinstance(prop_value, str):
                            states[prop_name] = prop_value.lower() in ("true", "1", "yes")
                        else:
                            states[prop_name] = bool(prop_value)
                
                if states:
                    states_map[artifact_id] = states
        
        # Fallback: Try direct property access (if stored as node properties)
        with self.driver.session() as session:
            result = session.run("""
                UNWIND $ids AS artifact_id
                MATCH (a:Individual {id: artifact_id})-[:INSTANCE_OF]->(:Class {name: "Artifact"})
                RETURN artifact_id, 
                       a.isOpen as isOpen,
                       a.isLocked as isLocked
            """, ids=artifact_ids)
            
            for record in result:
                artifact_id = record["artifact_id"]
                if artifact_id not in states_map:
                    states_map[artifact_id] = {}
                
                if record["isOpen"] is not None:
                    is_open = record["isOpen"]
                    if isinstance(is_open, str):
                        states_map[artifact_id]["isOpen"] = is_open.lower() in ("true", "1", "yes")
                    else:
                        states_map[artifact_id]["isOpen"] = bool(is_open)
                
                if record["isLocked"] is not None:
                    is_locked = record["isLocked"]
                    if isinstance(is_locked, str):
                        states_map[artifact_id]["isLocked"] = is_locked.lower() in ("true", "1", "yes")
                    else:
                        states_map[artifact_id]["isLocked"] = bool(is_locked)
        
        return states_map


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
    print("PDDL Generator Test")
    print("=" * 60)

    test_ids = ["cup_6", "living_room_22", "robot1", "left_hand"]
    types = generator.get_types(test_ids)
    print(f"\nTypes:")
    for id, type in types.items():
        print(f"  {id}: {type}")

    robot_info = generator.get_robot_info()
    print(f"\nRobot info: {robot_info}")

    locations = generator.get_locations_with_paths(["living_room_22", "bedroom_9"])
    print(f"\nLocations (with paths): {sorted(locations)}")

    topology = generator.get_topology(locations)
    print(f"\nConnections: {len(topology['connections'])} pairs")
    print(f"Sample distances: {list(topology['distances'].items())[:5]}")

    artifact_locs = generator.get_artifact_locations(["cup_6", "book_59"])
    print(f"\nArtifact locations:")
    for id, loc in artifact_locs.items():
        print(f"  {id}: {loc}")

    affordances = generator.get_affordances(["cup_6", "dining_table_48"])
    print(f"\nAffordances:")
    for id, affs in affordances.items():
        print(f"  {id}: {affs}")

    driver.close()
