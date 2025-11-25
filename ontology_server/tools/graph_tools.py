#!/usr/bin/env python3
"""
Graph Query Tools for Neo4j
Provides tools for object info, filtering, and pathfinding.
"""

from neo4j import GraphDatabase
from pathlib import Path
from typing import Dict, List, Optional, Any, Union


class GraphTools:
    """Graph query tools using Neo4j Cypher."""

    def __init__(self, neo4j_uri: str, neo4j_user: str, neo4j_password: str):
        """Initialize graph tools with Neo4j connection."""
        self.driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
        self.queries_dir = Path(__file__).parent / "queries"

    def close(self):
        """Close Neo4j connection."""
        if self.driver:
            self.driver.close()

    def _load_query(self, query_file: str) -> str:
        """Load Cypher query from file."""
        query_path = self.queries_dir / query_file
        with open(query_path, 'r') as f:
            return f.read()

    def get_object_info(self, object_ids: Union[str, List[str]]) -> Union[Dict[str, Any], List[Dict[str, Any]], None]:
        """
        Get complete information about object(s) or space(s).

        Args:
            object_ids: Single ID or list of IDs (e.g., "mug_5" or ["mug_5", "kitchen_20"])

        Returns:
            - If single ID: Dictionary with object info, or None if not found
            - If list of IDs: List of dictionaries (empty list if none found)

            Each object info includes:
            - All data properties (category, description, isOpen, etc.)
            - All object relationships (isInSpace, isInStorey, isInsideOf, etc.)

        Examples:
            info = tools.get_object_info("mug_5")
            infos = tools.get_object_info(["mug_5", "kitchen_20", "robot1"])
        """
        # Normalize input
        is_single = isinstance(object_ids, str)
        ids_list = [object_ids] if is_single else object_ids

        query = self._load_query("get_object_info.cypher")

        with self.driver.session() as session:
            result = session.run(query, object_ids=ids_list)

            objects = []
            for record in result:
                # Start with all properties (excluding internal fields)
                properties = record["properties"]
                obj_info = {
                    k: v for k, v in properties.items()
                    if k not in ["uri", "name", "category_embedding", "description_embedding"]
                }

                # Add relationships (exclude affordances)
                for rel in record["relationships"]:
                    if rel["type"] and rel["target"]:
                        rel_type = rel["type"]

                        # Skip affordances
                        if rel_type == "affords":
                            continue

                        # Convert relationship names to match ontology
                        if rel_type == "objectIsInSpace":
                            rel_type = "isInSpace"
                        elif rel_type == "robotIsInSpace":
                            rel_type = "isInSpace"
                        elif rel_type == "roomIsInStorey" or rel_type == "corridorIsInStorey":
                            rel_type = "isInStorey"

                        # Store as single value or list
                        if rel_type in obj_info:
                            # Convert to list if not already
                            if not isinstance(obj_info[rel_type], list):
                                obj_info[rel_type] = [obj_info[rel_type]]
                            obj_info[rel_type].append(rel["target"])
                        else:
                            obj_info[rel_type] = rel["target"]

                objects.append(obj_info)

            # Return format based on input
            if is_single:
                return objects[0] if objects else None
            return objects

    def filter_objects(self,
                      class_name: Optional[str] = None,
                      category: Optional[str] = None,
                      relationships: Optional[Dict[str, str]] = None,
                      data_properties: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Filter objects by various criteria (all optional, can be combined).

        Args:
            class_name: Filter by class label (e.g., "Artifact", "Space", "Portal")
            category: Filter by category property (e.g., "chair", "table", "cup")
            relationships: Filter by object properties (relationships to other individuals)
                          (e.g., {"isInSpace": "kitchen_20"})
            data_properties: Filter by data properties (attributes with literal values)
                            (e.g., {"isOpen": True, "isPowered": False})

        Returns:
            List of objects with all ontology properties and relationships

        Examples:
            # Find all chair-type objects
            chairs = tools.filter_objects(category="chair")

            # Find all chairs in living room
            chairs = tools.filter_objects(category="chair", relationships={"isInSpace": "living_room_23"})

            # Find all open doors on floor A
            doors = tools.filter_objects(
                class_name="Portal",
                relationships={"isInStorey": "Floor_A"},
                data_properties={"isOpen": True}
            )


            # Find powered devices in kitchen
            devices = tools.filter_objects(
                relationships={"isInSpace": "kitchen_20"},
                data_properties={"isPowered": True}
            )
        """
        query_parts = ["MATCH (obj:Individual)"]
        where_clauses = []
        params = {}

        if class_name:
            where_clauses.append(f"'{class_name}' IN labels(obj)")

        if category:
            where_clauses.append("obj.category = $category")
            params["category"] = category

        if data_properties:
            for prop_name, prop_value in data_properties.items():
                param_name = f"prop_{prop_name}"
                where_clauses.append(f"obj.{prop_name} = ${param_name}")
                params[param_name] = prop_value

        if where_clauses:
            query_parts.append("WHERE " + " AND ".join(where_clauses))

        if relationships:
            for rel_type, target_id in relationships.items():
                param_name = f"rel_{rel_type}"
                query_parts.append(f"MATCH (obj)-[:{rel_type}]->(n:Individual {{id: ${param_name}}})")
                params[param_name] = target_id

        query_parts.extend([
            "OPTIONAL MATCH (obj)-[r]->(target)",
            "WHERE type(r) <> 'INSTANCE_OF'",
            "WITH obj, collect(DISTINCT {type: type(r), target: target.id}) AS relationships",
            "RETURN properties(obj) AS properties, relationships",
            "ORDER BY obj.id"
        ])

        query = "\n".join(query_parts)

        with self.driver.session() as session:
            result = session.run(query, **params)

            objects = []
            for record in result:
                # Start with all properties (excluding internal fields)
                properties = record["properties"]
                obj = {
                    k: v for k, v in properties.items()
                    if k not in ["uri", "name", "category_embedding", "description_embedding"]
                }

                # Add relationships (exclude affordances)
                for rel in record["relationships"]:
                    if rel["type"] and rel["target"]:
                        rel_type = rel["type"]

                        # Skip affordances
                        if rel_type == "affords":
                            continue

                        # Convert relationship names to match ontology
                        if rel_type == "objectIsInSpace":
                            rel_type = "isInSpace"
                        elif rel_type == "robotIsInSpace":
                            rel_type = "isInSpace"
                        elif rel_type == "roomIsInStorey" or rel_type == "corridorIsInStorey":
                            rel_type = "isInStorey"

                        # Store as single value or list
                        if rel_type in obj:
                            if not isinstance(obj[rel_type], list):
                                obj[rel_type] = [obj[rel_type]]
                            obj[rel_type].append(rel["target"])
                        else:
                            obj[rel_type] = rel["target"]

                objects.append(obj)

            return objects

    def find_path(self, from_id: str, to_id: str) -> Optional[Dict[str, Any]]:
        """
        Find shortest path between two locations using GDS Dijkstra.
        Automatically resolves objects to their containing spaces.

        Args:
            from_id: Source object or space ID (e.g., "robot1", "kitchen_20")
            to_id: Target object or space ID (e.g., "mug_5", "bedroom_11")

        Returns:
            Dictionary with path information:
            - path: List of nodes with index and id
            - cost: Total path cost (number of edges)
            - num_nodes: Number of nodes in path

        Example:
            path = tools.find_path("robot1", "kitchen_20")
            # Returns: {path: [{index: 0, id: "living_room_23"}, ...], cost: 4, num_nodes: 5}
        """
        # First, ensure spatialGraph projection exists
        self._ensure_spatial_graph()

        query = self._load_query("find_path.cypher")

        try:
            with self.driver.session() as session:
                result = session.run(query, from_id=from_id, to_id=to_id)
                record = result.single()

                if not record:
                    return None

                return {
                    "path": record["path"],
                    "cost": record["cost"],
                    "num_nodes": record["num_nodes"]
                }

        except Exception as e:
            print(f"Error finding path: {e}")
            return None

    def _ensure_spatial_graph(self):
        """Ensure GDS spatialGraph projection exists."""
        # Check if projection exists
        with self.driver.session() as session:
            result = session.run("CALL gds.graph.exists('spatialGraph') YIELD exists")
            exists = result.single()["exists"]

        if not exists:
            print("Creating spatialGraph projection...")
            # Create projection including both Space and Portal (they are siblings under Environment)
            # Use edge count (uniform weight = 1.0) instead of Euclidean distance
            with self.driver.session() as session:
                session.run("""
                    CALL gds.graph.project.cypher(
                      'spatialGraph',
                      'MATCH (n) WHERE n:Space OR n:Portal RETURN id(n) AS id',
                      'MATCH (s)-[r:hasPathTo]-(t)
                       WHERE (s:Space OR s:Portal) AND (t:Space OR t:Portal)
                       RETURN id(s) AS source, id(t) AS target, 1.0 AS weight'
                    )
                """)
            print("spatialGraph projection created")


if __name__ == "__main__":
    # Test
    from core.config import get_config

    config = get_config()
    neo4j_config = config.get_neo4j_config()

    tools = GraphTools(
        neo4j_uri=neo4j_config['uri'],
        neo4j_user=neo4j_config['user'],
        neo4j_password=neo4j_config['password']
    )

    # Test get_object_info
    print("Testing get_object_info...")
    info = tools.get_object_info("robot1")
    print(f"Robot info: {info}")

    tools.close()
