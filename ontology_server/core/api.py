#!/usr/bin/env python3
"""
FastAPI Server for Ontology Management
Real-time REST API for ontology operations
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from .ontology import OntologyManager
from .env import EnvManager
from .embedding import EmbeddingManager
from .config import get_config
from .models import IndividualData, IndividualUpdate, StatusResponse, OperationResponse, BatchIndividualsData
from typing import Dict, Any, Optional
import os

# Global manager instances
manager: OntologyManager = None
env_manager: EnvManager = None
current_env_id: Optional[str] = None


def get_lifespan(env_id: Optional[str] = None):
    """Create lifespan context manager with space parameter."""
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Lifespan context manager for startup/shutdown."""
        global manager, env_manager, current_env_id

        # Startup
        print("Starting Ontology Manager Server...")

        # Initialize space manager
        env_manager = EnvManager()
        current_env_id = env_id

        # Get ontology path
        ontology_path = str(env_manager.get_ontology_path())

        # Get Neo4j config
        config = get_config()
        neo4j_config = config.get_neo4j_config()
        server_config = config.get_server_config()

        # Initialize ontology manager with space
        manager = OntologyManager(
            owl_path=ontology_path,
            env_id=env_id,
            neo4j_uri=neo4j_config['uri'],
            neo4j_user=neo4j_config['user'],
            neo4j_password=neo4j_config['password']
        )

        if env_id:
            space_config = env_manager.get_env_config(env_id)
            if space_config:
                env_name = space_config.get('env_name', space_config.get('name', env_id))
                print(f"Active environment: {env_name} ({env_id})")

        print("Server ready!\n")
        base_url = server_config.get('base_url', 'http://localhost:8000')
        print(f"API Documentation: {base_url}/docs")
        print("Neo4j Browser: http://localhost:7474\n")

        yield

        # Shutdown
        print("\nShutting down Ontology Manager Server...")
        if manager:
            manager.close()
        print("Server stopped")

    return lifespan


# Get space from environment variable (for server startup)
ENV_ID = os.getenv("ONTOLOGY_ENV_ID", None)

# Create FastAPI app
app = FastAPI(
    title="Ontology Manager API",
    description="Real-time ontology management with owlready2 + HermiT reasoner + Neo4j (space-aware)",
    version="2.0.0",
    lifespan=get_lifespan(ENV_ID)
)


@app.get("/", response_model=Dict[str, str])
async def root():
    """Root endpoint."""
    return {
        "message": "Ontology Manager API",
        "docs": "/docs",
        "status": "/status"
    }


@app.get("/status", response_model=StatusResponse)
async def get_status():
    """Get current ontology status."""
    if not manager:
        raise HTTPException(status_code=503, detail="Manager not initialized")

    status = manager.get_status()
    # Add space information
    if current_env_id and env_manager:
        space_config = env_manager.get_env_config(current_env_id)
        if space_config:
            status["env_id"] = current_env_id
            status["env_name"] = space_config.get("env_name")
    return status


@app.get("/spaces")
async def list_spaces():
    """List all available spaces."""
    if not env_manager:
        raise HTTPException(status_code=503, detail="Space manager not initialized")

    return {"spaces": env_manager.list_spaces()}


@app.get("/spaces/summary")
async def get_spaces_summary():
    """Get summary of all spaces."""
    if not env_manager:
        raise HTTPException(status_code=503, detail="Space manager not initialized")

    return env_manager.get_summary()


@app.get("/spaces/{env_id}")
async def get_space_info(env_id: str):
    """Get information about a specific space."""
    if not env_manager:
        raise HTTPException(status_code=503, detail="Space manager not initialized")

    config = env_manager.get_env_config(env_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Space '{env_id}' not found")

    # Get file paths
    static_path = env_manager.get_static_file_path(env_id)
    dynamic_path = env_manager.get_dynamic_file_path(env_id)

    return {
        "config": config,
        "static_file": str(static_path) if static_path else None,
        "dynamic_file": str(dynamic_path) if dynamic_path else None,
        "is_active": env_id == current_env_id
    }


@app.post("/individuals", response_model=OperationResponse)
async def add_individual(data: IndividualData):
    """
    Add a new individual to the ontology.

    Automatically runs reasoner and syncs to Neo4j.
    """
    if not manager:
        raise HTTPException(status_code=503, detail="Manager not initialized")

    # Convert Pydantic model to dict
    individual_dict = {
        "id": data.id,
        "class": data.class_name,
        "data_properties": data.data_properties or {},
        "object_properties": data.object_properties or {}
    }

    result = manager.add_individual(individual_dict)

    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])

    return result


@app.post("/individuals/batch", response_model=OperationResponse)
async def add_individuals_batch(data: BatchIndividualsData):
    """
    Add multiple individuals at once (batch operation).

    Runs reasoner only once after all individuals are added.
    Much faster than adding individuals one by one.
    """
    if not manager:
        raise HTTPException(status_code=503, detail="Manager not initialized")

    # Convert Pydantic models to dicts
    individuals_dicts = []
    for individual in data.individuals:
        individual_dict = {
            "id": individual.id,
            "class": individual.class_name,
            "data_properties": individual.data_properties or {},
            "object_properties": individual.object_properties or {}
        }
        individuals_dicts.append(individual_dict)

    result = manager.add_individuals_batch(individuals_dicts)

    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])

    return result


@app.put("/individuals/{individual_id}", response_model=OperationResponse)
async def update_individual(individual_id: str, data: IndividualUpdate):
    """
    Update an existing individual.

    Automatically runs reasoner and syncs to Neo4j.
    """
    if not manager:
        raise HTTPException(status_code=503, detail="Manager not initialized")

    # Convert Pydantic model to dict
    update_dict = {}
    if data.data_properties is not None:
        update_dict["data_properties"] = data.data_properties
    if data.object_properties is not None:
        update_dict["object_properties"] = data.object_properties

    result = manager.update_individual(individual_id, update_dict)

    if result["status"] == "error":
        raise HTTPException(status_code=404, detail=result["message"])

    return result


@app.delete("/individuals/{individual_id}", response_model=OperationResponse)
async def delete_individual(individual_id: str):
    """
    Delete an individual from the ontology.

    Automatically runs reasoner and syncs to Neo4j.
    """
    if not manager:
        raise HTTPException(status_code=503, detail="Manager not initialized")

    result = manager.delete_individual(individual_id)

    if result["status"] == "error":
        raise HTTPException(status_code=404, detail=result["message"])

    return result


@app.post("/load_ttl", response_model=OperationResponse)
async def load_ttl(file_path: dict):
    """
    Load individuals from a TTL file.

    Request body:
    {
        "file_path": "data/envs/Darden/static.ttl"
    }

    Automatically runs reasoner and syncs to Neo4j after loading.
    """
    if not manager:
        raise HTTPException(status_code=503, detail="Manager not initialized")

    ttl_path = file_path.get("file_path")
    if not ttl_path:
        raise HTTPException(status_code=400, detail="file_path is required")

    result = manager.load_instances_from_ttl(ttl_path)

    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])

    return result


@app.post("/sync", response_model=OperationResponse)
async def sync_ontology():
    """
    Manually trigger reasoner and Neo4j sync.

    Note: Sync is automatically triggered after add/update/delete operations.
    """
    if not manager:
        raise HTTPException(status_code=503, detail="Manager not initialized")

    result = manager.sync_to_neo4j()

    if result["status"] == "error":
        raise HTTPException(status_code=500, detail=result["message"])

    return result


@app.post("/sparql")
async def execute_sparql(query: dict):
    """
    Execute SPARQL query on the loaded ontology.

    Request body:
    {
        "query": "SELECT ?s ?p ?o WHERE { ?s ?p ?o } LIMIT 10"
    }
    """
    if not manager:
        raise HTTPException(status_code=503, detail="Manager not initialized")

    sparql_query = query.get("query")
    if not sparql_query:
        raise HTTPException(status_code=400, detail="Query is required")

    try:
        # Execute SPARQL query using owlready2
        results = list(manager.world.sparql(sparql_query))

        # Convert results to JSON-serializable format
        json_results = []
        for row in results:
            json_row = []
            for item in row:
                if hasattr(item, 'name'):
                    json_row.append({"type": "individual", "value": item.name})
                elif hasattr(item, 'iri'):
                    json_row.append({"type": "iri", "value": str(item.iri)})
                else:
                    json_row.append({"type": "literal", "value": str(item)})
            json_results.append(json_row)

        return {
            "status": "success",
            "count": len(json_results),
            "results": json_results
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query execution failed: {str(e)}")


@app.post("/sparql/update")
async def execute_sparql_update(update: dict):
    """
    Execute SPARQL UPDATE query and run incremental reasoning.
    
    Workflow:
    1. Apply SPARQL UPDATE to ontology (parse and apply changes)
    2. Run incremental HermiT reasoning (only on changed triples)
    3. Sync to Neo4j
    
    Request body:
    {
        "update": "DELETE { ... } INSERT { ... } WHERE { }"
    }
    """
    if not manager:
        raise HTTPException(status_code=503, detail="Manager not initialized")
    
    sparql_update = update.get("update")
    if not sparql_update:
        raise HTTPException(status_code=400, detail="SPARQL UPDATE query is required")
    
    try:
        import owlready2 as owl
        from rdflib import Graph, URIRef, Literal, BNode
        
        # Step 1: Parse SPARQL UPDATE and apply changes to ontology
        print(f"Applying SPARQL UPDATE to ontology...")
        
        # Parse DELETE and INSERT clauses from SPARQL UPDATE
        # Simple parsing (assumes DELETE { ... } INSERT { ... } WHERE { } format)
        delete_section = []
        insert_section = []
        
        lines = sparql_update.split('\n')
        in_delete = False
        in_insert = False
        
        for line in lines:
            line = line.strip()
            if 'DELETE' in line.upper():
                in_delete = True
                in_insert = False
                continue
            elif 'INSERT' in line.upper():
                in_delete = False
                in_insert = True
                continue
            elif line.startswith('}'):
                in_delete = False
                in_insert = False
                continue
            
            if in_delete and line and not line.startswith('{'):
                delete_section.append(line)
            elif in_insert and line and not line.startswith('{'):
                insert_section.append(line)
        
        # Apply DELETE operations
        for triple_line in delete_section:
            if triple_line.strip().endswith('.'):
                triple_line = triple_line.strip()[:-1].strip()
            # Parse triple and remove from ontology
            # Format: <subject> <predicate> <object>
            parts = triple_line.split()
            if len(parts) >= 3:
                subj_str = parts[0].strip('<>')
                pred_str = parts[1].strip('<>')
                obj_str = parts[2].strip('<>"')
                
                # Find individual and remove property
                individual = manager.ontology.search_one(iri=f"*{subj_str.split('#')[-1]}")
                if individual:
                    prop_name = pred_str.split('#')[-1]
                    if hasattr(manager.ontology, prop_name):
                        prop = getattr(manager.ontology, prop_name)
                        obj_individual = manager.ontology.search_one(iri=f"*{obj_str.split('#')[-1]}")
                        if obj_individual:
                            try:
                                getattr(individual, prop_name).remove(obj_individual)
                                print(f"  Removed: {subj_str.split('#')[-1]} {prop_name} {obj_str.split('#')[-1]}")
                            except (ValueError, AttributeError):
                                pass
        
        # Apply INSERT operations
        for triple_line in insert_section:
            if triple_line.strip().endswith('.'):
                triple_line = triple_line.strip()[:-1].strip()
            # Parse triple and add to ontology
            parts = triple_line.split()
            if len(parts) >= 3:
                subj_str = parts[0].strip('<>')
                pred_str = parts[1].strip('<>')
                obj_str = parts[2].strip('<>"')
                
                # Find individual and add property
                individual = manager.ontology.search_one(iri=f"*{subj_str.split('#')[-1]}")
                if individual:
                    prop_name = pred_str.split('#')[-1]
                    if hasattr(manager.ontology, prop_name):
                        prop = getattr(manager.ontology, prop_name)
                        obj_individual = manager.ontology.search_one(iri=f"*{obj_str.split('#')[-1]}")
                        if obj_individual:
                            current_values = getattr(individual, prop_name, [])
                            if not isinstance(current_values, list):
                                current_values = [current_values] if current_values else []
                            if obj_individual not in current_values:
                                setattr(individual, prop_name, current_values + [obj_individual])
                                print(f"  Added: {subj_str.split('#')[-1]} {prop_name} {obj_str.split('#')[-1]}")
        
        # Step 2: Delete old relationships in Neo4j (before reasoning)
        # This helps ensure clean state before reasoning
        print(f"Step 2: Deleting old relationships in Neo4j...")
        # Extract robot_id and old_location from DELETE section
        robot_id = None
        old_location = None
        for triple_line in delete_section:
            if 'robotIsInSpace' in triple_line:
                parts = triple_line.split()
                if len(parts) >= 3:
                    robot_id = parts[0].strip('<>').split('#')[-1]
                    old_location = parts[2].strip('<>').split('#')[-1]
                    break
        
        if robot_id and old_location:
            with manager.driver.session() as session:
                # Delete all relationships between robot and old location
                delete_result = session.run("""
                    MATCH (r:Individual {id: $robot_id})-[rel]->(loc:Individual {id: $old_location})
                    DELETE rel
                    RETURN count(rel) as deleted_count
                """, robot_id=robot_id, old_location=old_location)
                
                deleted_count = delete_result.single()["deleted_count"] if delete_result.peek() else 0
                print(f"    Deleted {deleted_count} forward relationships: {robot_id} -> {old_location}")
                
                # Delete reverse relationships
                delete_reverse = session.run("""
                    MATCH (loc:Individual {id: $old_location})-[rel]->(r:Individual {id: $robot_id})
                    DELETE rel
                    RETURN count(rel) as deleted_count
                """, robot_id=robot_id, old_location=old_location)
                
                deleted_reverse = delete_reverse.single()["deleted_count"] if delete_reverse.peek() else 0
                print(f"    Deleted {deleted_reverse} reverse relationships: {old_location} -> {robot_id}")
        
        # Step 3: Run reasoning ONCE (after DELETE and INSERT are both applied)
        # HermiT will recalculate all relationships based on current state
        print(f"Step 3: Running HermiT reasoning (single pass)...")
        with manager.ontology:
            owl.sync_reasoner_hermit(manager.world, infer_property_values=True)
        
        print(f"Reasoning completed")
        
        # Step 4: Sync to Neo4j (skip reasoning since we already did it)
        print(f"Step 4: Syncing to Neo4j...")
        result = manager.sync_to_neo4j(skip_reasoning=True)
        
        if result.get("status") == "success":
            return {
                "status": "success",
                "message": "SPARQL UPDATE applied and incremental reasoning completed"
            }
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to sync to Neo4j: {result.get('message', 'Unknown error')}"
            )
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"SPARQL UPDATE execution failed: {str(e)}"
        )


@app.post("/semantic_search")
async def semantic_search(query: str, top_k: int = 5, search_type: str = "description"):
    """
    Semantic search using natural language query with dual embedding support.

    Args:
        query: Natural language query string
        top_k: Number of top results to return (default: 5)
        search_type: Type of search - "category" or "description" (default: "description")
            - "category": Search by object type (e.g., "chair", "table")
            - "description": Search by object features (e.g., "comfortable place to sit")

    Returns:
        List of similar individuals with their descriptions and similarity scores
    """
    if not manager:
        raise HTTPException(status_code=503, detail="Ontology manager not initialized")

    # Validate search_type
    if search_type not in ["category", "description"]:
        raise HTTPException(status_code=400, detail="search_type must be 'category' or 'description'")

    try:
        # Generate embedding for the query
        from .config import get_config
        config = get_config()
        embedding_config = config.get_embedding_config()

        embedding_manager = EmbeddingManager(
            model=embedding_config.get('model', 'text-embedding-3-small'),
            dimensions=embedding_config.get('dimensions')  # None = use recommended default
        )
        query_embedding = embedding_manager.generate_embedding(query)

        # Choose index based on search_type
        index_name = "categoryEmbeddingIndex" if search_type == "category" else "descriptionEmbeddingIndex"

        # Perform vector similarity search in Neo4j
        with manager.driver.session() as session:
            result = session.run("""
                CALL db.index.vector.queryNodes(
                    $index_name,
                    $top_k,
                    $query_embedding
                )
                YIELD node, score
                RETURN node.id AS id,
                       node.category AS category,
                       labels(node) AS types,
                       node.description AS description,
                       score
                ORDER BY score DESC
            """, index_name=index_name, top_k=top_k, query_embedding=query_embedding)

            results = []
            for record in result:
                # Filter out 'Individual' from types list
                types = [t for t in record["types"] if t != "Individual"]
                results.append({
                    "id": record["id"],
                    "category": record["category"],
                    "types": types,
                    "description": record["description"],
                    "score": record["score"]
                })

            return {
                "status": "success",
                "query": query,
                "search_type": search_type,
                "count": len(results),
                "results": results
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Semantic search failed: {str(e)}")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "manager_ready": manager is not None}
