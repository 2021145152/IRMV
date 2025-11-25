#!/usr/bin/env python3
"""
OntologyManager: Core ontology management with owlready2 + reasoner + Neo4j
"""

import owlready2 as owl
from neo4j import GraphDatabase
from pathlib import Path
from typing import Dict, Any, List, Optional
import traceback
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class OntologyManager:
    """Manage OWL ontology with real-time Neo4j synchronization."""

    def __init__(self, owl_path: str = "data/robot.owx",
                 env_id: Optional[str] = None,
                 neo4j_uri: Optional[str] = None,
                 neo4j_user: Optional[str] = None,
                 neo4j_password: Optional[str] = None):
        """Initialize ontology manager.

        Args:
            owl_path: Path to shared ontology schema file
            env_id: ID of the space to load (optional, for context)
            neo4j_uri: Neo4j connection URI (required if not in config)
            neo4j_user: Neo4j username (required if not in config)
            neo4j_password: Neo4j password (required if not in config)
        """
        self.owl_path = owl_path
        self.env_id = env_id
        self.neo4j_uri = neo4j_uri
        self.neo4j_user = neo4j_user
        self.neo4j_password = neo4j_password

        self.world = None
        self.ontology = None
        self.driver = None
        self.current_data_type = None  # "static" or "dynamic" - tracks current loading context

        # Load OWL schema
        self._load_ontology()

        # Connect to Neo4j
        self._connect_neo4j()

        # Initialize Neo4j with schema
        self._initialize_neo4j_schema()

        space_info = f" (space: {env_id})" if env_id else ""
        print(f"OntologyManager initialized successfully{space_info}")

    def _load_ontology(self):
        """Load OWL ontology schema."""
        try:
            self.world = owl.World()
            self.world.get_ontology(f"file://{Path(self.owl_path).absolute()}").load()

            # Get ontology by IRI
            ontology_iri = "http://www.semanticweb.org/namh_woo/ontologies/2025/10/untitled-ontology-10"
            self.ontology = self.world.get_ontology(ontology_iri)

            if not self.ontology:
                self.ontology = list(self.world.ontologies())[0]

            classes = list(self.ontology.classes())
            obj_props = list(self.ontology.object_properties())
            data_props = list(self.ontology.data_properties())

            print(f"Loaded OWL ontology: {len(classes)} classes, "
                  f"{len(obj_props)} object properties, {len(data_props)} data properties")

        except Exception as e:
            print(f"ERROR: Failed to load ontology: {e}")
            raise

    def _connect_neo4j(self):
        """Connect to Neo4j database."""
        if not self.neo4j_uri or not self.neo4j_user or not self.neo4j_password:
            raise ValueError(
                "Neo4j credentials not provided. Please provide neo4j_uri, "
                "neo4j_user, and neo4j_password parameters, or set them in config.yaml"
            )

        try:
            self.driver = GraphDatabase.driver(
                self.neo4j_uri,
                auth=(self.neo4j_user, self.neo4j_password)
            )
            with self.driver.session() as session:
                session.run("RETURN 1")
            print("Connected to Neo4j")
        except Exception as e:
            print(f"ERROR: Neo4j connection failed: {e}")
            raise

    def _initialize_neo4j_schema(self):
        """Initialize Neo4j with OWL schema (classes, properties, hierarchy)."""
        try:
            with self.driver.session() as session:
                # Clear all data
                session.run("MATCH (n) DETACH DELETE n")

                # Sync classes
                for cls in self.ontology.classes():
                    session.run("""
                        MERGE (c:Class {id: $class_id})
                        SET c.name = $class_name,
                            c.uri = $class_uri
                    """, class_id=cls.name, class_name=cls.name, class_uri=str(cls.iri))

                # Sync class hierarchy
                for cls in self.ontology.classes():
                    for parent in cls.is_a:
                        if hasattr(parent, 'name') and parent != owl.Thing:
                            session.run("""
                                MATCH (child:Class {id: $child_id})
                                MATCH (parent:Class {id: $parent_id})
                                MERGE (child)-[:SUBCLASS_OF]->(parent)
                            """, child_id=cls.name, parent_id=parent.name)

                # Sync properties
                for prop in self.ontology.object_properties():
                    session.run("""
                        MERGE (p:Property {id: $prop_id})
                        SET p.name = $prop_name,
                            p.uri = $prop_uri,
                            p.type = 'ObjectProperty'
                    """, prop_id=prop.name, prop_name=prop.name, prop_uri=str(prop.iri))

                for prop in self.ontology.data_properties():
                    session.run("""
                        MERGE (p:Property {id: $prop_id})
                        SET p.name = $prop_name,
                            p.uri = $prop_uri,
                            p.type = 'DataProperty'
                    """, prop_id=prop.name, prop_name=prop.name, prop_uri=str(prop.iri))

                # Sync property domains and ranges
                for prop in self.ontology.object_properties():
                    for domain in prop.domain:
                        if hasattr(domain, 'name'):
                            session.run("""
                                MATCH (p:Property {id: $prop_id})
                                MATCH (c:Class {id: $class_id})
                                MERGE (p)-[:HAS_DOMAIN]->(c)
                            """, prop_id=prop.name, class_id=domain.name)

                    for range_cls in prop.range:
                        if hasattr(range_cls, 'name'):
                            session.run("""
                                MATCH (p:Property {id: $prop_id})
                                MATCH (c:Class {id: $class_id})
                                MERGE (p)-[:HAS_RANGE]->(c)
                            """, prop_id=prop.name, class_id=range_cls.name)

                # Sync property hierarchy
                for prop in self.ontology.object_properties():
                    for parent in prop.is_a:
                        if hasattr(parent, 'name') and parent != owl.ObjectProperty:
                            if parent.name not in ['SymmetricProperty', 'TransitiveProperty', 'topObjectProperty']:
                                session.run("""
                                    MATCH (child:Property {id: $child_id})
                                    MATCH (parent:Property {id: $parent_id})
                                    MERGE (child)-[:SUBPROPERTY_OF]->(parent)
                                """, child_id=prop.name, parent_id=parent.name)

                # Setup vector index for semantic search
                self._setup_vector_index(session)

            print("Initialized Neo4j with OWL schema")

        except Exception as e:
            print(f"ERROR: Failed to initialize Neo4j schema: {e}")
            raise

    def _setup_vector_index(self, session):
        """Setup dual vector indices for category and description embeddings with different dimensions."""
        try:
            from .config import get_config

            # Load embedding configuration
            config = get_config()
            embedding_config = config.get_embedding_config()

            # Extract dimensions for category and description
            category_config = embedding_config.get('category', {})
            description_config = embedding_config.get('description', {})

            # Use recommended defaults if not specified
            from .embedding import EmbeddingManager
            category_dims = category_config.get('dimensions') or \
                          EmbeddingManager.RECOMMENDED_DIMENSIONS.get(
                              category_config.get('model', 'text-embedding-3-small'), 512)
            description_dims = description_config.get('dimensions') or \
                             EmbeddingManager.RECOMMENDED_DIMENSIONS.get(
                                 description_config.get('model', 'text-embedding-3-small'), 512)

            # Always recreate indices to ensure correct dimensions
            # Drop old single embedding index if exists (for backward compatibility)
            session.run("DROP INDEX individualEmbeddingIndex IF EXISTS")

            # Drop existing dual embedding indices if they exist
            session.run("DROP INDEX categoryEmbeddingIndex IF EXISTS")
            session.run("DROP INDEX descriptionEmbeddingIndex IF EXISTS")
            print(f"Dropped old vector indices")

            # Create category embedding index
            session.run(f"""
                CREATE VECTOR INDEX categoryEmbeddingIndex
                FOR (n:Individual)
                ON n.category_embedding
                OPTIONS {{
                    indexConfig: {{
                        `vector.dimensions`: {category_dims},
                        `vector.similarity_function`: 'cosine'
                    }}
                }}
            """)
            print(f"Created category embedding index ({category_dims}D)")

            # Create description embedding index
            session.run(f"""
                CREATE VECTOR INDEX descriptionEmbeddingIndex
                FOR (n:Individual)
                ON n.description_embedding
                OPTIONS {{
                    indexConfig: {{
                        `vector.dimensions`: {description_dims},
                        `vector.similarity_function`: 'cosine'
                    }}
                }}
            """)
            print(f"Created description embedding index ({description_dims}D)")

        except Exception as e:
            print(f"WARNING: Vector index setup failed: {e}")
            print("  (This is optional - semantic search will not work without it)")

    def _set_data_properties(self, individual, data: Dict[str, Any]):
        """Helper method to set data properties on an individual."""
        if "data_properties" in data:
            for prop_name, value in data["data_properties"].items():
                setattr(individual, prop_name, value)

    def _set_object_properties(self, individual, data: Dict[str, Any]):
        """Helper method to set object properties on an individual."""
        if "object_properties" in data:
            for prop_name, target_ids in data["object_properties"].items():
                if not isinstance(target_ids, list):
                    target_ids = [target_ids]

                targets = []
                for target_id in target_ids:
                    target = self.ontology.search_one(iri=f"*{target_id}")
                    if target:
                        targets.append(target)

                if targets:
                    setattr(individual, prop_name, targets)

    def add_individual(self, data: Dict[str, Any], auto_sync: bool = True) -> Dict[str, Any]:
        """
        Add a new individual to the ontology.

        Args:
            data: {
                "id": "room_101",
                "class": "Room",
                "data_properties": {"roomNumber": "101"},
                "object_properties": {"isSpaceOf": "floor_1"}
            }
            auto_sync: Whether to automatically sync to Neo4j (default: True)

        Returns:
            Status dictionary
        """
        try:
            individual_id = data["id"]
            class_name = data["class"]

            # Get class from ontology
            cls = getattr(self.ontology, class_name, None)
            if not cls:
                return {"status": "error", "message": f"Class {class_name} not found"}

            # Check if individual already exists
            existing = self.ontology.search_one(iri=f"*{individual_id}")
            if existing:
                return {"status": "error", "message": f"Individual {individual_id} already exists"}

            # Create individual
            individual = cls(individual_id)

            # Set properties using helper methods
            self._set_data_properties(individual, data)
            self._set_object_properties(individual, data)

            print(f"Added individual: {individual_id}")

            # Auto sync (optional)
            if auto_sync:
                self.sync_to_neo4j()

            return {"status": "success", "id": individual_id}

        except Exception as e:
            print(f"ERROR: Failed to add individual: {e}")
            traceback.print_exc()
            return {"status": "error", "message": str(e)}

    def load_instances_from_ttl(self, ttl_path: str) -> Dict[str, Any]:
        """
        Load individuals from TTL file by parsing and using owlready2's add_individual API.

        Args:
            ttl_path: Path to TTL file containing individual instances

        Returns:
            Status dictionary with count of loaded individuals
        """
        try:
            import rdflib
            from rdflib.namespace import RDF

            ttl_file = Path(ttl_path).absolute()
            if not ttl_file.exists():
                return {"status": "error", "message": f"TTL file not found: {ttl_path}"}

            # Determine if this is static or dynamic data based on file path
            if "static.ttl" in str(ttl_path):
                self.current_data_type = "static"
            elif "dynamic.ttl" in str(ttl_path):
                self.current_data_type = "dynamic"
            else:
                self.current_data_type = None

            print(f"Loading individuals from TTL: {ttl_path}")

            # Parse TTL using rdflib
            g = rdflib.Graph()
            g.parse(str(ttl_file), format="turtle")
            print(f"  Parsed {len(g)} triples from TTL")

            # Extract individuals from TTL
            individuals_data = []
            subjects = set(g.subjects(RDF.type, None))

            for subject in subjects:
                subject_id = str(subject).split('#')[-1]

                # Skip ontology declaration
                if 'Ontology' in str(subject) or subject_id == '':
                    continue

                # Get rdf:type (class)
                types = [obj for obj in g.objects(subject, RDF.type)
                        if 'Ontology' not in str(obj)]
                if not types:
                    continue

                class_name = str(types[0]).split('#')[-1]

                # Get data and object properties
                data_properties = {}
                object_properties = {}

                for pred, obj in g.predicate_objects(subject):
                    if pred == RDF.type:
                        continue

                    pred_local = str(pred).split('#')[-1]

                    if isinstance(obj, rdflib.Literal):
                        data_properties[pred_local] = obj.toPython()
                    elif isinstance(obj, rdflib.URIRef):
                        obj_local = str(obj).split('#')[-1]
                        if pred_local not in object_properties:
                            object_properties[pred_local] = []
                        object_properties[pred_local].append(obj_local)

                individuals_data.append({
                    "id": subject_id,
                    "class": class_name,
                    "data_properties": data_properties,
                    "object_properties": object_properties
                })

            print(f"  Extracted {len(individuals_data)} individuals")

            # Use batch add method
            result = self.add_individuals_batch(individuals_data)
            return result

        except Exception as e:
            print(f"ERROR: Failed to load TTL file: {e}")
            traceback.print_exc()
            return {"status": "error", "message": str(e)}

    def add_individuals_batch(self, individuals_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Add multiple individuals at once and run reasoning only once at the end.
        Uses 2-pass approach to handle dependencies.

        Args:
            individuals_data: List of individual data dictionaries

        Returns:
            Status dictionary with count of added individuals
        """
        try:
            added_count = 0
            failed_count = 0

            print(f"Adding {len(individuals_data)} individuals in batch...")

            # Pass 1: Create all individuals without properties (to avoid order dependencies)
            for data in individuals_data:
                individual_id = data["id"]
                class_name = data["class"]

                # Check if already exists
                existing = self.ontology.search_one(iri=f"*{individual_id}")
                if existing:
                    failed_count += 1
                    print(f"ERROR: Failed to add individual: {individual_id} - Individual {individual_id} already exists")
                    continue

                # Get class from ontology
                cls = getattr(self.ontology, class_name, None)
                if not cls:
                    failed_count += 1
                    print(f"ERROR: Failed to add individual: {individual_id} - Class {class_name} not found")
                    continue

                # Create individual without properties
                try:
                    cls(individual_id)
                    added_count += 1
                except Exception as e:
                    failed_count += 1
                    print(f"ERROR: Failed to add individual: {individual_id} - {e}")

            # Pass 2: Set properties for all individuals
            for data in individuals_data:
                individual_id = data["id"]
                individual = self.ontology.search_one(iri=f"*{individual_id}")

                if not individual:
                    continue

                # Set properties using helper methods
                self._set_data_properties(individual, data)
                self._set_object_properties(individual, data)

            print(f"Added {added_count} individuals (failed: {failed_count})")

            # Run reasoning once for all individuals
            print("Running reasoning for all individuals...")
            self.sync_to_neo4j()

            return {
                "status": "success",
                "added": added_count,
                "failed": failed_count
            }

        except Exception as e:
            print(f"ERROR: Failed to add individuals batch: {e}")
            traceback.print_exc()
            return {"status": "error", "message": str(e)}

    def update_individual(self, individual_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing individual."""
        try:
            # Find individual
            individual = self.ontology.search_one(iri=f"*{individual_id}")
            if not individual:
                return {"status": "error", "message": f"Individual {individual_id} not found"}

            # Update properties using helper methods
            self._set_data_properties(individual, data)
            self._set_object_properties(individual, data)

            print(f"Updated individual: {individual_id}")

            # Auto sync
            self.sync_to_neo4j()

            return {"status": "success", "id": individual_id}

        except Exception as e:
            print(f"ERROR: Failed to update individual: {e}")
            return {"status": "error", "message": str(e)}

    def delete_individual(self, individual_id: str) -> Dict[str, Any]:
        """Delete an individual from the ontology."""
        try:
            individual = self.ontology.search_one(iri=f"*{individual_id}")
            if not individual:
                return {"status": "error", "message": f"Individual {individual_id} not found"}

            owl.destroy_entity(individual)

            print(f"Deleted individual: {individual_id}")

            # Auto sync
            self.sync_to_neo4j()

            return {"status": "success", "id": individual_id}

        except Exception as e:
            print(f"ERROR: Failed to delete individual: {e}")
            return {"status": "error", "message": str(e)}

    def sync_to_neo4j(self, skip_reasoning: bool = False) -> Dict[str, Any]:
        """
        Run reasoner (if needed) and sync all individuals to Neo4j.
        
        Args:
            skip_reasoning: If True, skip reasoning step (use when reasoning was already done)
        """
        try:
            if not skip_reasoning:
                print("Running HermiT reasoner...")
                # Run reasoner
                with self.ontology:
                    owl.sync_reasoner_hermit(self.world, infer_property_values=True)
                print("Reasoner completed")
            else:
                print("Skipping reasoning (already done)")

            # Sync to Neo4j
            with self.driver.session() as session:
                # Clear existing individuals
                session.run("MATCH (i:Individual) DETACH DELETE i")

                individuals_count = 0
                relationships_count = 0

                # BATCH 1: Create all individual nodes with class links and data properties
                print("  Batch 1: Creating individual nodes...")
                for individual in self.ontology.individuals():
                    # Collect all class labels (including superclasses via INDIRECT_is_a)
                    class_labels = []
                    for cls in individual.INDIRECT_is_a:
                        if hasattr(cls, 'name') and cls.name and cls != owl.Thing:
                            class_labels.append(cls.name)

                    # Build label string for Neo4j multi-labeling
                    labels = "Individual" + "".join(f":`{label}`" for label in class_labels)

                    # Create individual node with multiple labels
                    session.run(f"""
                        MERGE (i:{labels} {{id: $individual_id}})
                        SET i.uri = $individual_uri
                    """, individual_id=individual.name,
                        individual_uri=str(individual.iri))

                    individuals_count += 1

                    # Link to classes (using INDIRECT_is_a to include superclasses)
                    for cls in individual.INDIRECT_is_a:
                        if hasattr(cls, 'name') and cls.name and cls != owl.Thing:
                            session.run("""
                                MATCH (i:Individual {id: $individual_id})
                                MATCH (c:Class {id: $class_id})
                                MERGE (i)-[:INSTANCE_OF]->(c)
                            """, individual_id=individual.name, class_id=cls.name)

                    # Sync data properties (as node properties)
                    data_props = {}
                    for prop in self.ontology.data_properties():
                        prop_values = getattr(individual, prop.name, [])
                        if not isinstance(prop_values, list):
                            prop_values = [prop_values] if prop_values is not None else []

                        if len(prop_values) > 0:
                            data_props[prop.name] = prop_values[0] if len(prop_values) == 1 else prop_values

                    if data_props:
                        for key, value in data_props.items():
                            session.run("""
                                MATCH (i:Individual {id: $individual_id})
                                SET i[$prop_name] = $prop_value
                            """, individual_id=individual.name, prop_name=key, prop_value=value)

                print(f"  Created {individuals_count} individual nodes")

                # BATCH 2: Create all object property relationships
                print("  Batch 2: Creating object property relationships...")
                for individual in self.ontology.individuals():
                    for prop in self.ontology.object_properties():
                        indirect_attr = f"INDIRECT_{prop.name}"
                        prop_values = getattr(individual, indirect_attr, [])
                        if not isinstance(prop_values, list):
                            prop_values = [prop_values] if prop_values else []

                        for value in prop_values:
                            if hasattr(value, 'name'):
                                session.run(f"""
                                    MATCH (subj:Individual {{id: $subj_id}})
                                    MATCH (obj:Individual {{id: $obj_id}})
                                    MERGE (subj)-[:{prop.name}]->(obj)
                                """, subj_id=individual.name, obj_id=value.name)
                                relationships_count += 1

                print(f"  Created {relationships_count} relationships")

                # Handle embeddings (generate or load from cache)
                try:
                    from .embedding import EmbeddingManager
                    from .config import get_config

                    # Load embedding configuration from config.yaml
                    config = get_config()
                    embedding_config = config.get_embedding_config()
                    generate_embeddings = embedding_config.get('generate', True)

                    # Extract category and description configs
                    category_config = embedding_config.get('category', {})
                    description_config = embedding_config.get('description', {})

                    embedding_manager = EmbeddingManager(
                        category_model=category_config.get('model', 'text-embedding-3-small'),
                        category_dimensions=category_config.get('dimensions'),  # None = use recommended
                        description_model=description_config.get('model', 'text-embedding-3-small'),
                        description_dimensions=description_config.get('dimensions')  # None = use recommended
                    )

                    # Determine cache file path based on current data type
                    env_id = os.getenv('ONTOLOGY_ENV_ID')

                    if self.current_data_type == "static":
                        # Static data: data/envs/{env_name}/static_embeddings.json
                        if env_id:
                            cache_path = f"data/envs/{env_id}/static_embeddings.json"
                        else:
                            cache_path = "data/static_embeddings.json"
                    elif self.current_data_type == "dynamic":
                        # Dynamic data: data/envs/{env_name}/dynamic_embeddings.json
                        if env_id:
                            cache_path = f"data/envs/{env_id}/dynamic_embeddings.json"
                        else:
                            cache_path = "data/dynamic_embeddings.json"
                    else:
                        # Fallback: use env_id to determine
                        if env_id:
                            cache_path = f"data/envs/{env_id}/dynamic_embeddings.json"
                        else:
                            cache_path = "data/static_embeddings.json"

                    if generate_embeddings:
                        # Generate embeddings with progress bar
                        from tqdm import tqdm

                        print("Generating embeddings...")
                        embeddings_count = 0
                        failed_count = 0

                        individuals_list = list(self.ontology.individuals())

                        with tqdm(total=len(individuals_list), desc="Embedding progress", unit="obj") as pbar:
                            for individual in individuals_list:
                                try:
                                    if embedding_manager.embed_individual(individual, session):
                                        embeddings_count += 1
                                        pbar.set_postfix({"embedded": embeddings_count, "failed": failed_count})
                                    pbar.update(1)
                                except Exception as e:
                                    failed_count += 1
                                    pbar.write(f"Failed to embed {individual.name}: {e}")
                                    pbar.set_postfix({"embedded": embeddings_count, "failed": failed_count})
                                    pbar.update(1)
                                    if failed_count >= 3:
                                        pbar.write("Too many failures, stopping embedding generation")
                                        raise

                        print(f"Generated embeddings for {embeddings_count} individuals (Space/Portal/Artifact)")

                        # Save to cache file
                        embedding_manager.save_embeddings_to_file(session, cache_path)

                        # Generate category embeddings
                        if env_id:
                            category_cache_path = f"data/envs/{env_id}/category_embeddings.json"
                        else:
                            category_cache_path = "data/category_embeddings.json"

                        print("Generating category embeddings...")
                        embedding_manager.generate_and_save_category_embeddings(session, category_cache_path)
                    else:
                        # Load from cache
                        print(f"📂 Loading embeddings from cache: {cache_path}")
                        try:
                            embeddings_count = embedding_manager.load_embeddings_from_file(session, cache_path)
                        except FileNotFoundError as e:
                            print(f"❌ ERROR: {e}")
                            print(f"   Please set 'embedding.generate: true' in config.yaml to generate embeddings,")
                            print(f"   or ensure the cache file exists at: {cache_path}")
                            raise

                except Exception as e:
                    print(f"WARNING:  Embedding processing failed: {e}")
                    traceback.print_exc()
                    print("   (This is optional - continuing without embeddings)")

            print(f" Synced to Neo4j: {individuals_count} individuals, {relationships_count} relationships")

            return {
                "status": "success",
                "individuals": individuals_count,
                "relationships": relationships_count
            }

        except Exception as e:
            print(f"ERROR: Sync failed: {e}")
            traceback.print_exc()
            return {"status": "error", "message": str(e)}

    def get_status(self) -> Dict[str, Any]:
        """Get current ontology status."""
        try:
            individuals = list(self.ontology.individuals())
            classes = list(self.ontology.classes())

            return {
                "status": "running",
                "ontology": str(self.ontology.base_iri),
                "individuals_count": len(individuals),
                "classes_count": len(classes),
                "individuals": [ind.name for ind in individuals]
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def close(self, cleanup_neo4j: bool = True):
        """Close connections and optionally cleanup Neo4j data.

        Args:
            cleanup_neo4j: If True, delete all data from Neo4j before closing
        """
        if self.driver:
            if cleanup_neo4j:
                try:
                    with self.driver.session() as session:
                        session.run("MATCH (n) DETACH DELETE n")
                    print(" Cleaned up Neo4j data")
                except Exception as e:
                    print(f"WARNING: Failed to cleanup Neo4j: {e}")

            self.driver.close()
            print(" Closed Neo4j connection")
