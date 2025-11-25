"""World Update Node - Updates environment state based on executed action."""

import re
import sys
import json
import time
import requests
from pathlib import Path
from typing import Tuple, Set, Dict, List, Optional
from datetime import datetime
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

# Add ontology_server to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "ontology_server"))

from ..state import OverallState
from core.config import get_config
from core.ontology import OntologyManager
import owlready2 as owl


def parse_move_action(action: str) -> dict:
    """
    Parse move action to extract robot, from, and to locations.
    
    Args:
        action: PDDL action string, e.g., "(move robot1 corridor_14 door_9)"
        
    Returns:
        Dictionary with robot, from_location, to_location
    """
    # Match pattern: (move <robot> <from> <to>)
    match = re.match(r'\(move\s+(\w+)\s+(\w+)\s+(\w+)\)', action)
    if not match:
        raise ValueError(f"Invalid move action format: {action}")
    
    return {
        "robot": match.group(1),
        "from_location": match.group(2),
        "to_location": match.group(3)
    }


def get_next_ttl_version(ttl_dir: Path, base_name: str) -> int:
    """
    Get the next version number for TTL file.
    
    Args:
        ttl_dir: Directory containing TTL files
        base_name: Base name (e.g., "dynamic" or "static")
        
    Returns:
        Next version number (e.g., 1, 2, 3, ...)
    """
    version = 1
    while (ttl_dir / f"{base_name}_{version}.ttl").exists():
        version += 1
    return version


def save_incremental_update_to_ttl(original_ttl_path: Path, new_ttl_path: Path, robot_id: str, from_location: str, to_location: str) -> bool:
    """
    Save incremental update to TTL file - only modified parts are updated.
    
    This reads the original TTL file and updates only the changed relationship,
    keeping everything else unchanged. Much more efficient than exporting the entire ontology.
    
    Args:
        original_ttl_path: Path to original TTL file (e.g., dynamic.ttl)
        new_ttl_path: Path to save updated TTL file (e.g., new.ttl)
        robot_id: Robot ID (e.g., "robot1")
        from_location: Old location ID
        to_location: New location ID
        
    Returns:
        True if successful, False otherwise
    """
    try:
        if not original_ttl_path.exists():
            print(f"ERROR: Original TTL file not found: {original_ttl_path}")
            return False
        
        # Read original TTL file
        with open(original_ttl_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Find and update robotIsInSpace line
        updated = False
        robot_block_start = -1
        
        for i, line in enumerate(lines):
            # Find robot block start (e.g., ":robot1 rdf:type :Robot ;")
            if f":{robot_id}" in line and ("rdf:type" in line or "rdf:type" in lines[max(0, i-1)]):
                robot_block_start = i
            
            # Find robotIsInSpace line within robot block
            if robot_block_start >= 0 and f":robotIsInSpace" in line:
                # Check if this line contains the old location
                if f":{from_location}" in line:
                    # Replace old location with new location
                    new_line = line.replace(f":{from_location}", f":{to_location}")
                    lines[i] = new_line
                    updated = True
                    print(f"  Updated line {i+1}: {line.strip()} -> {new_line.strip()}")
                    break
                # If we've moved past the robot block, reset
                elif ";" in line and i > robot_block_start + 10:  # Robot block should be within 10 lines
                    robot_block_start = -1
        
        if not updated:
            print(f"WARNING: Could not find robotIsInSpace relationship for {robot_id} in TTL file")
            print(f"  Attempting alternative search...")
            # Alternative: search for any line with robotIsInSpace and from_location
            for i, line in enumerate(lines):
                if f":robotIsInSpace" in line and f":{from_location}" in line:
                    new_line = line.replace(f":{from_location}", f":{to_location}")
                    lines[i] = new_line
                    updated = True
                    print(f"  Updated line {i+1}: {line.strip()} -> {new_line.strip()}")
                    break
        
        if not updated:
            print(f"ERROR: Failed to find and update robotIsInSpace relationship")
            return False
        
        # Save updated TTL file
        new_ttl_path.parent.mkdir(parents=True, exist_ok=True)
        with open(new_ttl_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        
        print(f"✓ Saved incremental update to TTL file: {new_ttl_path}")
        return True
        
    except Exception as e:
        print(f"ERROR saving incremental update to TTL: {e}")
        import traceback
        traceback.print_exc()
        return False


def extract_changes_with_rdflib(original_ttl_path: Path, updated_ttl_path: Path) -> Tuple[Set[Tuple], Set[Tuple]]:
    """
    Extract changes between original and updated TTL files using rdflib.
    
    Returns:
        Tuple of (added_triples, removed_triples)
        Each triple is (subject, predicate, object) as URIRef or Literal
    """
    try:
        from rdflib import Graph, URIRef
        
        # Load original TTL
        original_graph = Graph()
        original_graph.parse(str(original_ttl_path), format='turtle')
        
        # Load updated TTL
        updated_graph = Graph()
        updated_graph.parse(str(updated_ttl_path), format='turtle')
        
        # Find added triples (in updated but not in original)
        added_triples = set(updated_graph) - set(original_graph)
        
        # Find removed triples (in original but not in updated)
        removed_triples = set(original_graph) - set(updated_graph)
        
        print(f"  Extracted changes:")
        print(f"    Added triples: {len(added_triples)}")
        print(f"    Removed triples: {len(removed_triples)}")
        
        return added_triples, removed_triples
        
    except Exception as e:
        print(f"ERROR extracting changes with rdflib: {e}")
        import traceback
        traceback.print_exc()
        return set(), set()


def load_relationship_mapping(project_root: Path) -> Optional[Dict]:
    """
    Load relationship mapping from relationship_mapping.json.
    
    Args:
        project_root: Project root directory (relationship_mapping.json is in action/ directory)
        
    Returns:
        Dictionary with relationship mappings, or None if file not found
    """
    mapping_path = project_root / "action" / "relationship_mapping.json"
    if not mapping_path.exists():
        print(f"  WARNING: relationship_mapping.json not found at {mapping_path}")
        return None
    
    try:
        with open(mapping_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"  ERROR loading relationship_mapping.json: {e}")
        return None


def get_inferred_relationships_for_delete(asserted_predicate: str, subject: str, object_: str, mapping: Dict, namespace: str = "http://www.semanticweb.org/namh_woo/ontologies/2025/9/untitled-ontology-10#") -> List[Tuple[str, str, str]]:
    """
    Get inferred relationships that should be deleted when an asserted relationship is deleted.
    
    Args:
        asserted_predicate: The asserted predicate (e.g., "robotIsInSpace")
        subject: Subject URI or local name
        object_: Object URI or local name
        mapping: Relationship mapping dictionary
        namespace: Ontology namespace
        
    Returns:
        List of (subject, predicate, object) tuples for inferred relationships to delete
    """
    inferred_triples = []
    
    # Get mapping for this asserted predicate
    predicate_mapping = mapping.get("mappings", {}).get(asserted_predicate)
    if not predicate_mapping:
        return inferred_triples
    
    # Extract local name from predicate if it's a full URI
    if "#" in asserted_predicate:
        asserted_predicate_local = asserted_predicate.split("#")[-1]
    else:
        asserted_predicate_local = asserted_predicate
    
    # Get inferred relationships
    inferred_rels = predicate_mapping.get("inferred_relationships", [])
    
    for inferred_rel in inferred_rels:
        inferred_predicate = inferred_rel["relationship"]
        inference_type = inferred_rel["type"]
        
        # Format predicate as full URI
        if not inferred_predicate.startswith("http"):
            inferred_predicate_uri = f"{namespace}#{inferred_predicate}"
        else:
            inferred_predicate_uri = inferred_predicate
        
        # Format subject and object
        if not subject.startswith("http"):
            subject_uri = f"{namespace}#{subject}" if not subject.startswith(":") else f"{namespace}{subject}"
        else:
            subject_uri = subject
        
        if not object_.startswith("http"):
            object_uri = f"{namespace}#{object_}" if not object_.startswith(":") else f"{namespace}{object_}"
        else:
            object_uri = object_
        
        # Handle different inference types
        if inference_type == "inverse_inference":
            # For inverse relationships, swap subject and object
            # Example: objectIsInSpace(robot, space) → spaceHasObject(space, robot)
            inferred_triples.append((object_uri, inferred_predicate_uri, subject_uri))
        else:
            # For subproperty and property chain, keep same subject and object
            # Example: robotIsInSpace(robot, space) → objectIsInSpace(robot, space)
            inferred_triples.append((subject_uri, inferred_predicate_uri, object_uri))
    
    return inferred_triples


def generate_sparql_update(added_triples: Set[Tuple], removed_triples: Set[Tuple], project_root: Optional[Path] = None, namespace: str = "http://www.semanticweb.org/namh_woo/ontologies/2025/9/untitled-ontology-10#") -> str:
    """
    Generate SPARQL UPDATE query from added and removed triples.
    When an asserted relationship is deleted, also delete its inferred relationships.
    
    Args:
        added_triples: Set of triples to add
        removed_triples: Set of triples to remove
        project_root: Project root directory (relationship_mapping.json is in action/ directory) (optional)
        namespace: Namespace for the ontology
        
    Returns:
        SPARQL UPDATE query string
    """
    try:
        from rdflib import URIRef, Literal, BNode
        
        def format_term(term):
            """Format RDF term for SPARQL."""
            if isinstance(term, URIRef):
                return f"<{term}>"
            elif isinstance(term, Literal):
                if term.datatype:
                    return f'"{term.value}"^^<{term.datatype}>'
                elif term.language:
                    return f'"{term.value}"@{term.language}'
                else:
                    return f'"{term.value}"'
            elif isinstance(term, BNode):
                return f"_:{term}"
            else:
                return str(term)
        
        # Load relationship mapping if project_root is provided
        mapping = None
        if project_root:
            mapping = load_relationship_mapping(project_root)
        
        # Build DELETE clause - include both asserted and inferred relationships
        delete_clauses = []
        delete_triples_set = set()  # Track what we've added to avoid duplicates
        
        # First, add all removed triples (asserted relationships)
        for s, p, o in removed_triples:
            triple_key = (str(s), str(p), str(o))
            if triple_key not in delete_triples_set:
                delete_clauses.append(f"    {format_term(s)} {format_term(p)} {format_term(o)} .")
                delete_triples_set.add(triple_key)
        
        # For each removed asserted relationship, add its inferred relationships
        if mapping:
            # Asserted predicates that we track
            asserted_predicates = ["robotIsInSpace", "artifactIsInSpace", "isInsideOf", "isOntopOf", "carries", "spaceIsInStorey"]
            
            for s, p, o in removed_triples:
                # Extract predicate local name
                predicate_str = str(p)
                if "#" in predicate_str:
                    predicate_local = predicate_str.split("#")[-1]
                elif predicate_str.endswith("robotIsInSpace") or predicate_str.endswith("artifactIsInSpace"):
                    predicate_local = predicate_str.split("/")[-1] if "/" in predicate_str else predicate_str
                else:
                    predicate_local = None
                
                # Check if this is an asserted predicate
                if predicate_local in asserted_predicates:
                    # Extract subject and object local names
                    subject_str = str(s)
                    object_str = str(o)
                    
                    # Extract local names
                    if "#" in subject_str:
                        subject_local = subject_str.split("#")[-1]
                    elif subject_str.startswith(":"):
                        subject_local = subject_str[1:]
                    else:
                        subject_local = subject_str.split("/")[-1] if "/" in subject_str else subject_str
                    
                    if "#" in object_str:
                        object_local = object_str.split("#")[-1]
                    elif object_str.startswith(":"):
                        object_local = object_str[1:]
                    else:
                        object_local = object_str.split("/")[-1] if "/" in object_str else object_str
                    
                    # Get inferred relationships
                    inferred_triples = get_inferred_relationships_for_delete(
                        predicate_local, subject_local, object_local, mapping, namespace
                    )
                    
                    # Add inferred relationships to DELETE clause
                    for inf_s, inf_p, inf_o in inferred_triples:
                        triple_key = (inf_s, inf_p, inf_o)
                        if triple_key not in delete_triples_set:
                            delete_clauses.append(f"    <{inf_s}> <{inf_p}> <{inf_o}> .")
                            delete_triples_set.add(triple_key)
                            print(f"    Added inferred DELETE: {inf_p.split('#')[-1]} {subject_local} -> {object_local}")
        
        # Build INSERT clause
        insert_clauses = []
        for s, p, o in added_triples:
            insert_clauses.append(f"    {format_term(s)} {format_term(p)} {format_term(o)} .")
        
        # Build SPARQL UPDATE query
        query_parts = []
        
        if delete_clauses:
            query_parts.append("DELETE {")
            query_parts.extend(delete_clauses)
            query_parts.append("}")
        
        if insert_clauses:
            if delete_clauses:
                query_parts.append("INSERT {")
            else:
                query_parts.append("INSERT DATA {")
            query_parts.extend(insert_clauses)
            query_parts.append("}")
        
        if delete_clauses and insert_clauses:
            query_parts.append("WHERE { }")
        
        query = "\n".join(query_parts)
        
        print(f"  Generated SPARQL UPDATE query ({len(delete_clauses)} deletes, {len(insert_clauses)} inserts)")
        return query
        
    except Exception as e:
        print(f"ERROR generating SPARQL UPDATE: {e}")
        import traceback
        traceback.print_exc()
        return ""


def send_sparql_update(sparql_query: str, endpoint_url: str) -> bool:
    """
    Send SPARQL UPDATE query to SPARQL endpoint.
    
    Args:
        sparql_query: SPARQL UPDATE query string
        endpoint_url: SPARQL endpoint URL (should be /sparql/update)
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Send to /sparql/update endpoint
        response = requests.post(
            endpoint_url,
            json={"update": sparql_query},
            headers={'Content-Type': 'application/json'},
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get("status") == "success":
                print(f"✓ SPARQL UPDATE sent successfully to {endpoint_url}")
                print(f"  Server response: {result.get('message', '')}")
                return True
            else:
                print(f"ERROR: SPARQL UPDATE failed: {result.get('message', 'Unknown error')}")
                return False
        else:
            print(f"ERROR: SPARQL UPDATE failed with status {response.status_code}")
            print(f"  Response: {response.text}")
            return False
                
    except Exception as e:
        print(f"ERROR sending SPARQL UPDATE: {e}")
        import traceback
        traceback.print_exc()
        return False


def update_robot_location_ontology(ontology_manager: OntologyManager, robot_id: str, from_location: str, to_location: str, save_ttl_path: Path = None) -> bool:
    """
    Update robot location by modifying the original data (A) in ontology, then reasoning.
    
    Correct workflow:
    1. Update asserted fact in ontology (A: 원본 수정) - robotIsInSpace
    2. Run reasoning (A → B: 새로운 유도 관계 생성)
    3. Sync to Neo4j (B 동기화)
    
    This ensures we update the source (A: asserted facts), not the inferred data (B).
    After reasoning, all derived relationships will be correctly generated from the updated source.
    
    Args:
        ontology_manager: OntologyManager instance
        robot_id: Robot ID (e.g., "robot1")
        from_location: Old location ID
        to_location: New location ID
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Step 1: Find robot individual in ontology (asserted fact - 원본 A)
        robot = ontology_manager.ontology.search_one(iri=f"*{robot_id}")
        if not robot:
            print(f"ERROR: Robot {robot_id} not found in ontology")
            return False
        
        # Step 2: Update asserted fact (A: 원본 수정)
        # 
        # owlready2에서:
        # - robot.robotIsInSpace = asserted fact (원본 A) - 직접 설정된 관계
        # - robot.INDIRECT_robotIsInSpace = inferred fact (추론된 B) - reasoning으로 생성된 관계
        #
        # 우리는 원본(A)을 수정해야 합니다!
        # 
        # Get current robotIsInSpace (asserted fact - 직접 설정된 관계)
        # Note: robotIsInSpace is the asserted fact, not INDIRECT_robotIsInSpace
        print(f"=== 확인: 원본(asserted) vs 추론된(inferred) 데이터 ===")
        current_robotIsInSpace = getattr(robot, "robotIsInSpace", [])
        if not isinstance(current_robotIsInSpace, list):
            current_robotIsInSpace = [current_robotIsInSpace] if current_robotIsInSpace else []
        
        # Verify current location matches expected
        current_locations = [loc.name for loc in current_robotIsInSpace if hasattr(loc, 'name')]
        
        # 비교: asserted vs inferred
        current_indirect = getattr(robot, "INDIRECT_robotIsInSpace", [])
        if not isinstance(current_indirect, list):
            current_indirect = [current_indirect] if current_indirect else []
        indirect_locations = [loc.name for loc in current_indirect if hasattr(loc, 'name')]
        
        print(f"  [원본 A] robot.robotIsInSpace (asserted): {current_locations}")
        print(f"  [추론 B] robot.INDIRECT_robotIsInSpace (inferred): {indirect_locations}")
        print(f"  → 우리가 수정하는 것: robot.robotIsInSpace (원본 A) ✓")
        print(f"  → sync_to_neo4j()가 사용하는 것: INDIRECT_ 속성 (추론된 B)")
        if from_location not in current_locations:
            print(f"WARNING: Expected {robot_id} to be at {from_location}, but found: {current_locations}")
        
        # Clear all existing robotIsInSpace relationships (asserted facts)
        print(f"Step 1: Updating asserted fact (source A) in ontology...")
        print(f"  Before update - asserted robotIsInSpace: {current_locations}")
        
        # Remove all existing relationships
        for old_location in list(current_robotIsInSpace):  # Use list() to avoid modification during iteration
            if hasattr(old_location, 'name'):
                print(f"  Removing asserted fact: robotIsInSpace {robot_id} -> {old_location.name}")
                try:
                    robot.robotIsInSpace.remove(old_location)
                except ValueError:
                    # Already removed
                    pass
        
        # Set to empty to ensure it's cleared
        setattr(robot, "robotIsInSpace", [])
        
        # Verify it's empty
        remaining = getattr(robot, "robotIsInSpace", [])
        if not isinstance(remaining, list):
            remaining = [remaining] if remaining else []
        remaining_locs = [loc.name for loc in remaining if hasattr(loc, 'name')]
        print(f"  After clearing - asserted robotIsInSpace: {remaining_locs}")
        
        if remaining_locs:
            print(f"  ERROR: Failed to clear robotIsInSpace. Still has: {remaining_locs}")
            return False
        
        # Find new location
        new_location = ontology_manager.ontology.search_one(iri=f"*{to_location}")
        if not new_location:
            print(f"ERROR: Location {to_location} not found in ontology")
            return False
        
        # Set new robotIsInSpace relationship (asserted fact)
        setattr(robot, "robotIsInSpace", [new_location])
        
        # Verify asserted fact is set correctly
        new_robotIsInSpace = getattr(robot, "robotIsInSpace", [])
        if not isinstance(new_robotIsInSpace, list):
            new_robotIsInSpace = [new_robotIsInSpace] if new_robotIsInSpace else []
        
        new_locs = [loc.name for loc in new_robotIsInSpace if hasattr(loc, 'name')]
        print(f"  After setting new - asserted robotIsInSpace: {new_locs}")
        
        if len(new_locs) != 1 or new_locs[0] != to_location:
            print(f"ERROR: Failed to set new robotIsInSpace relationship. Got: {new_locs}, expected: [{to_location}]")
            return False
        
        print(f"  ✓ Updated asserted fact: robotIsInSpace {robot_id} -> {to_location}")
        
        # Verify INDIRECT_ properties BEFORE reasoning (should still have old values)
        indirect_robotIsInSpace_before = getattr(robot, "INDIRECT_robotIsInSpace", [])
        if not isinstance(indirect_robotIsInSpace_before, list):
            indirect_robotIsInSpace_before = [indirect_robotIsInSpace_before] if indirect_robotIsInSpace_before else []
        indirect_locs_before = [loc.name for loc in indirect_robotIsInSpace_before if hasattr(loc, 'name')]
        print(f"  Before reasoning - INDIRECT_robotIsInSpace: {indirect_locs_before}")
        
        # Step 3: Run reasoning to generate new derived relationships (A → B)
        print(f"Step 2: Running reasoning to generate derived relationships (A → B)...")
        
        # IMPORTANT: Before reasoning, we need to clear old inferred relationships
        # Reasoning will regenerate relationships, but old ones might persist if not cleared first
        print(f"  Step 2.1: Running preliminary reasoning to clear old inferred relationships...")
        with ontology_manager.ontology:
            owl.sync_reasoner_hermit(ontology_manager.world, infer_property_values=True)
        
        # Verify old relationships are cleared in ontology
        indirect_robotIsInSpace_after_clear = getattr(robot, "INDIRECT_robotIsInSpace", [])
        if not isinstance(indirect_robotIsInSpace_after_clear, list):
            indirect_robotIsInSpace_after_clear = [indirect_robotIsInSpace_after_clear] if indirect_robotIsInSpace_after_clear else []
        indirect_locs_after_clear = [loc.name for loc in indirect_robotIsInSpace_after_clear if hasattr(loc, 'name')]
        print(f"    After preliminary reasoning - INDIRECT_robotIsInSpace: {indirect_locs_after_clear}")
        
        # Check if old location is still present
        old_locs_after_clear = [loc for loc in indirect_locs_after_clear if loc == from_location]
        if old_locs_after_clear:
            print(f"    ⚠️  WARNING: Old location {from_location} still present after preliminary reasoning!")
        else:
            print(f"    ✓ Old location {from_location} cleared from inferred relationships")
        
        # Step 2.2: Delete old relationships in Neo4j before full sync
        print(f"  Step 2.2: Deleting old relationships in Neo4j...")
        with ontology_manager.driver.session() as session:
            # Delete ALL relationships between robot and old location (both directions)
            # This includes: robotIsInSpace, objectIsInSpace, spaceHasObject, hasObject, isInSpace, isInStorey, etc.
            
            # Forward: robot -> old_location
            delete_forward = session.run("""
                MATCH (r:Individual {id: $robot_id})-[rel]->(loc:Individual {id: $old_location})
                DELETE rel
                RETURN count(rel) as deleted_count
            """, robot_id=robot_id, old_location=from_location)
            
            deleted_forward = delete_forward.single()["deleted_count"] if delete_forward.peek() else 0
            print(f"    Deleted {deleted_forward} forward relationships: {robot_id} -> {from_location}")
            
            # Reverse: old_location -> robot
            delete_reverse = session.run("""
                MATCH (loc:Individual {id: $old_location})-[rel]->(r:Individual {id: $robot_id})
                DELETE rel
                RETURN count(rel) as deleted_count
            """, robot_id=robot_id, old_location=from_location)
            
            deleted_reverse = delete_reverse.single()["deleted_count"] if delete_reverse.peek() else 0
            print(f"    Deleted {deleted_reverse} reverse relationships: {from_location} -> {robot_id}")
            
            # Also delete any relationships via objectIsInSpace, isInSpace, etc.
            # These might be inferred relationships that weren't directly connected
            delete_all_types = session.run("""
                MATCH (r:Individual {id: $robot_id})-[rel:objectIsInSpace|isInSpace|hasObject|spaceHasObject|isInStorey]->(loc:Individual {id: $old_location})
                DELETE rel
                RETURN count(rel) as deleted_count
            """, robot_id=robot_id, old_location=from_location)
            
            deleted_all_types = delete_all_types.single()["deleted_count"] if delete_all_types.peek() else 0
            if deleted_all_types > 0:
                print(f"    Deleted {deleted_all_types} additional inferred relationships")
        
        # Step 2.3: Now run full reasoning and sync to Neo4j
        # This will regenerate all relationships based on current asserted facts
        print(f"  Step 2.3: Running full reasoning and syncing to Neo4j...")
        result = ontology_manager.sync_to_neo4j()
        
        # Verify INDIRECT_ properties AFTER reasoning (should have new values only)
        indirect_robotIsInSpace_after = getattr(robot, "INDIRECT_robotIsInSpace", [])
        if not isinstance(indirect_robotIsInSpace_after, list):
            indirect_robotIsInSpace_after = [indirect_robotIsInSpace_after] if indirect_robotIsInSpace_after else []
        indirect_locs_after = [loc.name for loc in indirect_robotIsInSpace_after if hasattr(loc, 'name')]
        print(f"  After reasoning - INDIRECT_robotIsInSpace: {indirect_locs_after}")
        
        # Check for old relationships
        old_locs = [loc for loc in indirect_locs_after if loc == from_location]
        if old_locs:
            print(f"  ⚠️  WARNING: Old location {from_location} still present in INDIRECT_robotIsInSpace after reasoning!")
            print(f"     This indicates reasoning may not have fully cleared old relationships")
        else:
            print(f"  ✓ Old location {from_location} successfully removed from derived relationships")
        
        if result.get("status") == "success":
            print(f"✓ Updated source (A): {robot_id} robotIsInSpace {from_location} → {to_location}")
            print(f"✓ Reasoning completed: new derived relationships (B) created from updated source")
            
            # Step 4: Save incremental update to TTL file (if path provided)
            if save_ttl_path:
                print(f"Step 3: Saving incremental update to TTL file...")
                # Get original TTL file path (dynamic.ttl)
                original_ttl_path = save_ttl_path.parent / "dynamic.ttl"
                if save_incremental_update_to_ttl(original_ttl_path, save_ttl_path, robot_id, from_location, to_location):
                    print(f"✓ Saved incremental update to: {save_ttl_path}")
                else:
                    print(f"WARNING: Failed to save incremental update to TTL file")
            
            return True
        else:
            print(f"ERROR: Failed to sync to Neo4j: {result.get('message', 'Unknown error')}")
            return False
            
    except Exception as e:
        print(f"ERROR updating robot location: {e}")
        import traceback
        traceback.print_exc()
        return False


def world_update(state: OverallState, config: RunnableConfig) -> dict:
    """
    Update world state based on current action.
    
    For move actions:
    1. Parse action to extract robot, from, to locations
    2. Update Neo4j: delete old robotIsInSpace, create new robotIsInSpace
    
    Returns:
        State updates with execution status
    """
    try:
        # Start timing
        start_time = time.time()
        
        current_action = state.get("current_action")
        
        if not current_action:
            error_msg = "ERROR: No current action to execute. Please ensure next_action has been called."
            return {
                "messages": [AIMessage(content=error_msg)]
            }
        
        # Check if it's a move action
        if not current_action.strip().startswith("(move"):
            # For now, only handle move actions
            warning_msg = f"WARNING: Action type not yet supported: {current_action}\n"
            warning_msg += "Only 'move' actions are currently implemented."
            return {
                "messages": [AIMessage(content=warning_msg)]
            }
        
        # Parse move action
        action_data = parse_move_action(current_action)
        robot_id = action_data["robot"]
        from_location = action_data["from_location"]
        to_location = action_data["to_location"]
        
        # Get config for OntologyManager
        config_obj = get_config()
        neo4j_config = config_obj.get_neo4j_config()
        active_env = config_obj.get_active_env()
        
        # Get world directory path (where TTL files are stored)
        world_dir = project_root / "action" / "world"
        world_dir.mkdir(parents=True, exist_ok=True)
        
        # Get log directory path
        log_dir = project_root / "action" / "log"
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # Get ontology_server directory path
        ontology_server_dir = project_root / "ontology_server"
        env_dir = ontology_server_dir / "data" / "envs" / active_env
        
        # Get server config for SPARQL endpoint
        server_config = config_obj.get_server_config()
        base_url = server_config.get("base_url", "http://localhost:8000")
        sparql_endpoint = f"{base_url}/sparql"
        
        # Step 1: Get next version number and prepare TTL file paths
        # Version 0 is initial state (created in plan_reader)
        # Version 1, 2, ... are updates
        executed_count = state.get("executed_action_count", 0)
        version = executed_count + 1  # Next version to create
        print(f"Step 1: Preparing TTL files (version {version})...")
        
        # Original TTL paths: use previous version (version 0 for first update, version N-1 for subsequent)
        original_dynamic_path = world_dir / f"dynamic_{executed_count}.ttl"
        original_static_path = world_dir / f"static_{executed_count}.ttl"
        
        updated_dynamic_path = world_dir / f"dynamic_{version}.ttl"
        updated_static_path = world_dir / f"static_{version}.ttl"
        
        if not original_dynamic_path.exists():
            error_msg = f"ERROR: Original dynamic TTL file not found: {original_dynamic_path}"
            return {
                "messages": [AIMessage(content=error_msg)],
                "execution_status": "failed"
            }
        
        print(f"  Using original: {original_dynamic_path.name}")
        print(f"  Creating new version: {updated_dynamic_path.name}")
        
        # Step 2: Update TTL file (dynamic only, static is unchanged)
        print(f"Step 2: Updating TTL file...")
        if not save_incremental_update_to_ttl(original_dynamic_path, updated_dynamic_path, robot_id, from_location, to_location):
            error_msg = f"ERROR: Failed to update TTL file"
            return {
                "messages": [AIMessage(content=error_msg)],
                "execution_status": "failed"
            }
        
        # Copy static TTL (no changes, just version it)
        if original_static_path.exists():
            import shutil
            shutil.copy2(original_static_path, updated_static_path)
            print(f"  Copied static TTL: {updated_static_path}")
        
        # Step 3: Extract changes using rdflib
        print(f"Step 3: Extracting changes with rdflib...")
        added_triples, removed_triples = extract_changes_with_rdflib(original_dynamic_path, updated_dynamic_path)
        
        if not added_triples and not removed_triples:
            print(f"  WARNING: No changes detected between TTL files")
        
        # Step 4: Generate SPARQL UPDATE query (including inferred relationships)
        print(f"Step 4: Generating SPARQL UPDATE query...")
        sparql_query = generate_sparql_update(added_triples, removed_triples, project_root=project_root)
        
        if not sparql_query:
            error_msg = f"ERROR: Failed to generate SPARQL UPDATE query"
            return {
                "messages": [AIMessage(content=error_msg)],
                "execution_status": "failed"
            }
        
        # Step 5: Send SPARQL UPDATE to endpoint
        print(f"Step 5: Sending SPARQL UPDATE to endpoint...")
        update_endpoint = sparql_endpoint.rstrip('/') + '/update'
        if not send_sparql_update(sparql_query, update_endpoint):
            error_msg = f"ERROR: Failed to send SPARQL UPDATE to endpoint"
            return {
                "messages": [AIMessage(content=error_msg)],
                "execution_status": "failed"
            }
        
        # Step 6: Server will handle incremental reasoning
        print(f"Step 6: Server will process changes and run incremental HermiT reasoning...")
        print(f"  (This is handled by the ontology server)")
        
        # Calculate elapsed time
        elapsed_time = time.time() - start_time
        
        # Update executed action count
        new_executed_count = executed_count + 1
        
        # Step 7: Save log to JSON file
        log_data = {
            "action_number": new_executed_count,
            "timestamp": datetime.now().isoformat(),
            "action": {
                "raw": current_action,
                "type": "move",
                "robot": robot_id,
                "from_location": from_location,
                "to_location": to_location
            },
            "updates": {
                "ttl_files": {
                    "original": {
                        "dynamic": original_dynamic_path.name,
                        "static": original_static_path.name
                    },
                    "updated": {
                        "dynamic": updated_dynamic_path.name,
                        "static": updated_static_path.name
                    }
                },
                "relationships": {
                    "removed": len(removed_triples),
                    "added": len(added_triples),
                    "changed": {
                        "robotIsInSpace": {
                            "robot": robot_id,
                            "from": from_location,
                            "to": to_location
                        }
                    }
                },
                "sparql_endpoint": sparql_endpoint
            },
            "performance": {
                "elapsed_time_seconds": round(elapsed_time, 3),
                "elapsed_time_formatted": f"{elapsed_time:.3f}s"
            },
            "status": "success"
        }
        
        # Save log file
        log_file = log_dir / f"{new_executed_count}.json"
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(log_data, f, indent=2, ensure_ascii=False)
        print(f"  Log saved: {log_file}")
        
        success_msg = f"World updated successfully:\n"
        success_msg += f"  Action: {current_action}\n"
        success_msg += f"  Robot {robot_id} moved from {from_location} to {to_location}\n\n"
        success_msg += f"  Workflow completed:\n"
        success_msg += f"    1. TTL files updated: dynamic_{version}.ttl, static_{version}.ttl\n"
        success_msg += f"    2. Changes extracted: {len(removed_triples)} removed, {len(added_triples)} added\n"
        success_msg += f"    3. SPARQL UPDATE sent to: {sparql_endpoint}\n"
        success_msg += f"    4. Server will process changes and run incremental reasoning\n"
        success_msg += f"    5. Log saved: {log_file.name}\n\n"
        success_msg += f"  Updated relationship:\n"
        success_msg += f"    - robotIsInSpace: {robot_id} -> {to_location}\n"
        success_msg += f"  Derived relationships will be inferred by server's incremental reasoning\n\n"
        success_msg += f"  Performance: {elapsed_time:.3f}s"
        
        return {
            "messages": [AIMessage(content=success_msg)],
            "last_executed_action": current_action,
            "execution_status": "success",
            "executed_action_count": new_executed_count
        }
        
    except ValueError as e:
        # Calculate elapsed time even on error
        elapsed_time = time.time() - start_time if 'start_time' in locals() else 0
        
        # Get log directory
        log_dir = project_root / "action" / "log"
        log_dir.mkdir(parents=True, exist_ok=True)
        
        executed_count = state.get("executed_action_count", 0)
        new_executed_count = executed_count + 1
        
        # Save error log
        error_log_data = {
            "action_number": new_executed_count,
            "timestamp": datetime.now().isoformat(),
            "action": {
                "raw": state.get("current_action", "unknown"),
                "error": str(e)
            },
            "performance": {
                "elapsed_time_seconds": round(elapsed_time, 3),
                "elapsed_time_formatted": f"{elapsed_time:.3f}s"
            },
            "status": "failed",
            "error_type": "ValueError"
        }
        
        log_file = log_dir / f"{new_executed_count}.json"
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(error_log_data, f, indent=2, ensure_ascii=False)
        
        error_msg = f"ERROR parsing action: {str(e)}"
        return {
            "messages": [AIMessage(content=error_msg)],
            "execution_status": "failed"
        }
    except Exception as e:
        # Calculate elapsed time even on error
        elapsed_time = time.time() - start_time if 'start_time' in locals() else 0
        
        # Get log directory
        log_dir = project_root / "action" / "log"
        log_dir.mkdir(parents=True, exist_ok=True)
        
        executed_count = state.get("executed_action_count", 0)
        new_executed_count = executed_count + 1
        
        # Save error log
        error_log_data = {
            "action_number": new_executed_count,
            "timestamp": datetime.now().isoformat(),
            "action": {
                "raw": state.get("current_action", "unknown"),
                "error": str(e)
            },
            "performance": {
                "elapsed_time_seconds": round(elapsed_time, 3),
                "elapsed_time_formatted": f"{elapsed_time:.3f}s"
            },
            "status": "failed",
            "error_type": type(e).__name__
        }
        
        log_file = log_dir / f"{new_executed_count}.json"
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(error_log_data, f, indent=2, ensure_ascii=False)
        
        error_msg = f"ERROR in world_update: {type(e).__name__}: {str(e)}"
        import traceback
        traceback.print_exc()
        return {
            "messages": [AIMessage(content=error_msg)],
            "execution_status": "failed"
        }

