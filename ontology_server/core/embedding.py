"""
Embedding Manager for generating and managing vector embeddings using OpenAI API.
"""
import os
from typing import List, Optional
from openai import OpenAI


class EmbeddingManager:
    """Manages embedding generation using OpenAI's text-embedding models with dual-model support."""

    # Recommended dimensions per model (balanced performance/storage)
    RECOMMENDED_DIMENSIONS = {
        "text-embedding-3-small": 512,
        "text-embedding-3-large": 1024,
        "text-embedding-ada-002": 1536,  # Fixed for ada-002
    }

    def __init__(self, api_key: Optional[str] = None,
                 category_model: str = "text-embedding-3-small",
                 category_dimensions: Optional[int] = None,
                 description_model: str = "text-embedding-3-small",
                 description_dimensions: Optional[int] = None):
        """
        Initialize EmbeddingManager with OpenAI API and dual model support.

        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env variable)
            category_model: Model for category embeddings (object type names)
            category_dimensions: Dimensions for category embeddings (None = use recommended)
            description_model: Model for description embeddings (detailed features)
            description_dimensions: Dimensions for description embeddings (None = use recommended)
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key not provided. Set OPENAI_API_KEY environment variable.")

        # Category embedding config
        self.category_model = category_model
        if category_dimensions is None:
            self.category_dimensions = self.RECOMMENDED_DIMENSIONS.get(category_model, 512)
        else:
            self.category_dimensions = category_dimensions

        # Description embedding config
        self.description_model = description_model
        if description_dimensions is None:
            self.description_dimensions = self.RECOMMENDED_DIMENSIONS.get(description_model, 512)
        else:
            self.description_dimensions = description_dimensions

        self.client = OpenAI(api_key=self.api_key)

        print(f"EmbeddingManager initialized: "
              f"category={self.category_model}({self.category_dimensions}D), "
              f"description={self.description_model}({self.description_dimensions}D)")

    def generate_category_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for category text (object type names).

        Args:
            text: Category text to embed (e.g., "chair", "kitchen")

        Returns:
            List of floats representing the embedding vector
        """
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")

        response = self.client.embeddings.create(
            input=text,
            model=self.category_model,
            dimensions=self.category_dimensions
        )

        return response.data[0].embedding

    def generate_description_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for description text (detailed features).

        Args:
            text: Description text to embed

        Returns:
            List of floats representing the embedding vector
        """
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")

        response = self.client.embeddings.create(
            input=text,
            model=self.description_model,
            dimensions=self.description_dimensions
        )

        return response.data[0].embedding


    def embed_individual(self, individual, neo4j_session) -> bool:
        """
        Generate description embedding and store in Neo4j.

        Only generates description embedding for Space and Artifact classes.
        Category embeddings are now stored separately in category_embeddings.json.

        Args:
            individual: Owlready2 Individual object
            neo4j_session: Neo4j session for database operations

        Returns:
            True if embedding was created
        """
        # Check individual's classes
        class_names = set()
        for cls in individual.INDIRECT_is_a:
            if hasattr(cls, 'name') and cls.name:
                class_names.add(cls.name)

        # Only generate description embedding for Space and Artifact
        should_generate_description = bool({'Space', 'Artifact'} & class_names)

        if not should_generate_description:
            return False

        # Get category from TTL data property
        category = None
        if hasattr(individual, 'category') and individual.category:
            category = individual.category[0] if isinstance(individual.category, list) else individual.category

        # Get description from TTL data property
        description = None
        if hasattr(individual, 'description') and individual.description:
            description = individual.description[0] if isinstance(individual.description, list) else individual.description

        # Skip if no description or category (fallback)
        if not description and not category:
            return False

        # Generate description embedding
        # If no description, use category as fallback
        description_text = description if description else category
        description_embedding = self.generate_description_embedding(description_text)

        # Store embedding in Neo4j
        query = """
            MATCH (n:Individual {id: $id})
            SET n.description_embedding = $description_embedding
            RETURN n.id AS id
        """

        result = neo4j_session.run(query, id=individual.name, description_embedding=description_embedding)

        # Consume result to ensure query is executed
        result.consume()

        return True

    def get_embedding_dimensions(self) -> dict:
        """Get the dimensions for category and description embeddings."""
        return {
            'category': self.category_dimensions,
            'description': self.description_dimensions
        }

    def get_embedding_config(self) -> dict:
        """Get the complete embedding configuration including models and dimensions."""
        return {
            'category': {
                'model': self.category_model,
                'dimensions': self.category_dimensions
            },
            'description': {
                'model': self.description_model,
                'dimensions': self.description_dimensions
            }
        }

    def save_embeddings_to_file(self, neo4j_session, output_path: str):
        """
        Save description embeddings from Neo4j to a JSON file for caching.

        Args:
            neo4j_session: Neo4j session to query embeddings
            output_path: Path to save the embeddings JSON file
        """
        import json
        from pathlib import Path

        # Query description embeddings from Neo4j
        result = neo4j_session.run("""
            MATCH (n:Individual)
            WHERE n.description_embedding IS NOT NULL
            RETURN n.id AS id,
                   n.description_embedding AS description_embedding
        """)

        embeddings_list = []
        for record in result:
            embeddings_list.append({
                "id": record["id"],
                "description_embedding": record["description_embedding"]
            })

        # Create JSON with metadata and embeddings
        output_data = {
            "metadata": {
                "description_model": self.description_model,
                "description_dimensions": self.description_dimensions
            },
            "embeddings": embeddings_list
        }

        # Save to file
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(output_data, f, indent=2)

        print(f"Saved {len(embeddings_list)} description embeddings to {output_path}")
        print(f"  Model: {self.description_model} ({self.description_dimensions}D)")

    def load_embeddings_from_file(self, neo4j_session, input_path: str) -> int:
        """
        Load description embeddings from a JSON file and store them in Neo4j.

        Args:
            neo4j_session: Neo4j session to store embeddings
            input_path: Path to the embeddings JSON file

        Returns:
            Number of embeddings loaded

        Raises:
            FileNotFoundError: If the embeddings file doesn't exist
        """
        import json
        from pathlib import Path

        if not Path(input_path).exists():
            raise FileNotFoundError(f"Embeddings cache file not found: {input_path}")

        # Load from file
        with open(input_path, 'r') as f:
            data = json.load(f)

        # Check if new format (with metadata) or legacy format (array only)
        if isinstance(data, dict) and "metadata" in data and "embeddings" in data:
            # New format with metadata
            metadata = data["metadata"]
            embeddings_list = data["embeddings"]

            # Log metadata info
            print(f"  Loaded metadata from cache:")
            print(f"    Description: {metadata['description_model']} ({metadata['description_dimensions']}D)")
        elif isinstance(data, list):
            # Legacy format (array of embeddings)
            embeddings_list = data
            print(f"  WARNING: Loading from legacy format (no metadata)")
        else:
            raise ValueError(f"Invalid embedding cache format in {input_path}")

        # Store in Neo4j
        count = 0
        for item in embeddings_list:
            if item.get("description_embedding") is None:
                continue

            query = """
                MATCH (n:Individual {id: $id})
                SET n.description_embedding = $description_embedding
                RETURN n.id AS id
            """

            result = neo4j_session.run(
                query,
                id=item["id"],
                description_embedding=item["description_embedding"]
            )
            if result.single():
                count += 1

        print(f"Loaded {count} description embeddings from {input_path}")
        return count

    def extract_unique_categories(self, neo4j_session) -> list:
        """
        Extract unique categories from Neo4j.

        Args:
            neo4j_session: Neo4j session

        Returns:
            List of unique category strings
        """
        query = """
            MATCH (n:Individual)
            WHERE n.category IS NOT NULL
            RETURN DISTINCT n.category AS category
            ORDER BY category
        """

        result = neo4j_session.run(query)
        categories = [record["category"] for record in result]

        return categories

    def generate_and_save_category_embeddings(self, neo4j_session, output_path: str):
        """
        Generate embeddings for unique categories and save to JSON file.

        Args:
            neo4j_session: Neo4j session to extract categories
            output_path: Path to save category embeddings JSON file
        """
        import json
        from pathlib import Path

        # Extract unique categories
        categories = self.extract_unique_categories(neo4j_session)

        print(f"Generating embeddings for {len(categories)} unique categories...")

        # Generate embeddings for each category
        category_embeddings = {}
        for i, category in enumerate(categories, 1):
            embedding = self.generate_category_embedding(category)
            category_embeddings[category] = embedding

            if i % 10 == 0 or i == len(categories):
                print(f"  Progress: {i}/{len(categories)}")

        # Create JSON with metadata
        output_data = {
            "metadata": {
                "category_model": self.category_model,
                "category_dimensions": self.category_dimensions
            },
            "embeddings": category_embeddings
        }

        # Save to file
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(output_data, f, indent=2)

        print(f"Saved {len(category_embeddings)} category embeddings to {output_path}")
        print(f"  Model: {self.category_model} ({self.category_dimensions}D)")

    @staticmethod
    def load_category_embeddings(input_path: str) -> dict:
        """
        Load category embeddings from JSON file.

        Args:
            input_path: Path to category embeddings JSON file

        Returns:
            Dictionary with metadata and embeddings
            {
                "metadata": {...},
                "embeddings": {category: embedding_vector, ...}
            }

        Raises:
            FileNotFoundError: If the file doesn't exist
        """
        import json
        from pathlib import Path

        if not Path(input_path).exists():
            raise FileNotFoundError(f"Category embeddings file not found: {input_path}")

        with open(input_path, 'r') as f:
            data = json.load(f)

        return data

    @staticmethod
    def load_metadata_from_file(input_path: str) -> dict:
        """
        Load only metadata from embedding cache file.

        Args:
            input_path: Path to the embeddings JSON file

        Returns:
            Metadata dict with category and description model config

        Raises:
            FileNotFoundError: If the embeddings file doesn't exist
            ValueError: If metadata not found in cache file
        """
        import json
        from pathlib import Path

        if not Path(input_path).exists():
            raise FileNotFoundError(f"Embeddings cache file not found: {input_path}")

        with open(input_path, 'r') as f:
            data = json.load(f)

        if isinstance(data, dict) and "metadata" in data:
            return data["metadata"]
        else:
            raise ValueError(
                f"No metadata found in {input_path}. "
                "This might be a legacy format cache file. "
                "Please regenerate embeddings with generate: true in config.yaml"
            )
