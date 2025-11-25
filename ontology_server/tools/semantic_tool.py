#!/usr/bin/env python3
"""
Semantic Search Tool using OpenAI embeddings and Neo4j vector index.
"""

from neo4j import GraphDatabase
from core.embedding import EmbeddingManager
from typing import List, Dict, Any, Optional, Union
import os
import numpy as np


class SemanticTool:
    """Semantic search tool using vector similarity with dual-model support."""

    def __init__(self, neo4j_uri: str, neo4j_user: str, neo4j_password: str,
                 openai_api_key: Optional[str] = None,
                 category_model: str = "text-embedding-3-small",
                 category_dimensions: Optional[int] = None,
                 description_model: str = "text-embedding-3-small",
                 description_dimensions: Optional[int] = None,
                 category_embeddings_path: Optional[str] = None):
        """
        Initialize semantic search tool with dual embedding models.

        Args:
            neo4j_uri: Neo4j connection URI
            neo4j_user: Neo4j username
            neo4j_password: Neo4j password
            openai_api_key: OpenAI API key (defaults to OPENAI_API_KEY env)
            category_model: Model for category embedding
            category_dimensions: Dimensions for category embedding (None = use recommended)
            description_model: Model for description embedding
            description_dimensions: Dimensions for description embedding (None = use recommended)
            category_embeddings_path: Path to category embeddings JSON file
        """
        self.driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))

        # Initialize embedding manager with dual models
        self.embedding_manager = EmbeddingManager(
            api_key=openai_api_key or os.getenv("OPENAI_API_KEY"),
            category_model=category_model,
            category_dimensions=category_dimensions,
            description_model=description_model,
            description_dimensions=description_dimensions
        )

        # Load category embeddings if path provided
        self.category_embeddings = None
        if category_embeddings_path:
            try:
                data = EmbeddingManager.load_category_embeddings(category_embeddings_path)
                self.category_embeddings = data["embeddings"]
                print(f"Loaded {len(self.category_embeddings)} category embeddings from cache")
            except FileNotFoundError:
                print(f"WARNING: Category embeddings file not found: {category_embeddings_path}")

    def close(self):
        """Close Neo4j connection."""
        if self.driver:
            self.driver.close()

    def search(self, query: str, top_k: int = 5, search_type: str = "description") -> Union[List[str], List[Dict[str, Any]]]:
        """
        Search for categories or objects using natural language query.

        Uses OpenAI embeddings to convert query to vector and finds similar
        categories or objects.

        Args:
            query: Natural language search query
                   e.g., "comfortable place to sit", "red mug", "chair"
            top_k: Maximum number of results to return (default: 5)
            search_type: Type of search to perform (default: "description")
                - "category": Search by object type/category (e.g., "chair", "table")
                             Returns list of category names (strings)
                             Best for: finding what types of objects exist
                - "description": Search by object features/description
                                Returns list of object details (dicts)
                                Best for: finding specific objects by their characteristics

        Returns:
            - If search_type="category": List of category names (strings)
              e.g., ["chair", "couch", "bench"]
            - If search_type="description": List of objects with all ontology properties and similarity scores (dicts)
              Each dict contains: id, category, description, isInSpace, isOpen, isON, etc. + similarity (excludes affordances)

        Examples:
            # Search by category (returns category names)
            categories = semantic_tool.search("chair", top_k=3, search_type="category")
            # Returns: ["chair", "stool", "bench"]

            # Search by description (returns objects with all properties)
            objects = semantic_tool.search("comfortable place to sit", top_k=3, search_type="description")
            # Returns: [{"id": "couch_32", "category": "couch", "description": "...", "isInSpace": "living_room_21", "isOpen": False, "similarity": 0.92}, ...]
        """
        # Validate search_type
        if search_type not in ["category", "description"]:
            raise ValueError(f"Invalid search_type: {search_type}. Must be 'category' or 'description'")

        if search_type == "category":
            # Category search: return category names using local similarity computation
            if not self.category_embeddings:
                raise ValueError("Category embeddings not loaded. Provide category_embeddings_path during initialization.")

            # Generate query embedding
            query_embedding = self.embedding_manager.generate_category_embedding(query)

            # Compute cosine similarity with all categories
            similarities = []
            for category, cat_embedding in self.category_embeddings.items():
                similarity = self._cosine_similarity(query_embedding, cat_embedding)
                similarities.append((category, similarity))

            # Sort by similarity and return top-k category names
            similarities.sort(key=lambda x: x[1], reverse=True)
            top_categories = [cat for cat, _ in similarities[:top_k]]

            return top_categories

        else:
            # Description search: return objects using Neo4j vector index
            query_embedding = self.embedding_manager.generate_description_embedding(query)
            index_name = "descriptionEmbeddingIndex"

            # Search using Neo4j vector index
            with self.driver.session() as session:
                result = session.run("""
                    CALL db.index.vector.queryNodes(
                        $index_name,
                        $top_k,
                        $query_embedding
                    )
                    YIELD node, score

                    OPTIONAL MATCH (node)-[r]->(target)
                    WHERE type(r) <> 'INSTANCE_OF'

                    WITH node, score, collect(DISTINCT {type: type(r), target: target.id}) AS relationships

                    RETURN
                        properties(node) AS properties,
                        relationships,
                        score AS similarity
                    ORDER BY score DESC
                """, index_name=index_name, query_embedding=query_embedding, top_k=top_k)

                results = []
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

                    # Add similarity score
                    obj["similarity"] = record["similarity"]

                    results.append(obj)

                return results

    @staticmethod
    def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        v1 = np.array(vec1)
        v2 = np.array(vec2)
        return float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2)))


if __name__ == "__main__":
    # Test
    from core.config import get_config

    config = get_config()
    neo4j_config = config.get_neo4j_config()
    embedding_config = config.get_embedding_config()

    # Check if using cached embeddings
    generate_embeddings = embedding_config.get('generate', True)

    if not generate_embeddings:
        # Load model info from cache metadata
        print("Loading embedding model info from cache metadata...")
        env_id = os.getenv('ONTOLOGY_ENV_ID') or config.get_active_env()
        cache_path = f"data/envs/{env_id}/dynamic_embeddings.json"

        try:
            metadata = EmbeddingManager.load_metadata_from_file(cache_path)
            print(f"  Loaded: category={metadata['category_model']}({metadata['category_dimensions']}D), "
                  f"description={metadata['description_model']}({metadata['description_dimensions']}D)")

            category_config = {
                'model': metadata['category_model'],
                'dimensions': metadata['category_dimensions']
            }
            description_config = {
                'model': metadata['description_model'],
                'dimensions': metadata['description_dimensions']
            }
        except (FileNotFoundError, ValueError) as e:
            print(f"  WARNING: Could not load metadata from cache: {e}")
            print(f"  Using config.yaml settings instead")
            category_config = embedding_config.get('category', {})
            description_config = embedding_config.get('description', {})
    else:
        # Use config.yaml settings
        category_config = embedding_config.get('category', {})
        description_config = embedding_config.get('description', {})

    tool = SemanticTool(
        neo4j_uri=neo4j_config['uri'],
        neo4j_user=neo4j_config['user'],
        neo4j_password=neo4j_config['password'],
        category_model=category_config.get('model', 'text-embedding-3-small'),
        category_dimensions=category_config.get('dimensions'),
        description_model=description_config.get('model', 'text-embedding-3-small'),
        description_dimensions=description_config.get('dimensions')
    )

    # Test category search
    print("\n=== Testing category search ===")
    results = tool.search("chair", top_k=3, search_type="category")
    for result in results:
        print(f"  {result['id']} (category: {result['category']}) - score: {result['similarity']:.3f}")

    # Test description search
    print("\n=== Testing description search ===")
    results = tool.search("comfortable place to sit", top_k=3, search_type="description")
    for result in results:
        comment = result['comment'][:50] if result['comment'] else "No description"
        print(f"  {result['id']}: {comment}... - score: {result['similarity']:.3f}")

    tool.close()
