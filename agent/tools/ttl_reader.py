"""TTL Reader Tool - Read and parse TTL files to extract object information."""

import sys
import re
from pathlib import Path
from typing import Dict, List, Any
from rdflib import Graph, Namespace, RDF

# Add ontology_server to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "ontology_server"))

from core.config import get_config
from core.env import EnvManager


def read_ttl_file(ttl_path: Path) -> Dict[str, Any]:
    """
    Read TTL file and extract object information.
    
    Args:
        ttl_path: Path to TTL file
        
    Returns:
        Dictionary with objects, categories, locations, and affordances
    """
    g = Graph()
    g.parse(str(ttl_path), format='turtle')
    
    ns = Namespace("http://www.semanticweb.org/namh_woo/ontologies/2025/9/untitled-ontology-10#")
    
    objects = []
    categories = set()
    locations = set()
    affordances_map = {}
    
    # Extract all individuals with their properties
    for s, p, o in g:
        s_str = str(s)
        p_str = str(p)
        o_str = str(o)
        
        # Skip ontology definitions (the ontology itself, not individuals)
        if s_str.endswith('untitled-ontology-10') or 'robot.owx' in s_str:
            continue
        
        # Skip RDF/OWL namespace triples
        if 'www.w3.org' in s_str and ('rdf-syntax' in s_str or 'rdf-schema' in s_str or 'owl' in s_str):
            continue
        
        # Extract object name (local name after #)
        # Subjects are like: http://.../untitled-ontology-10#oven_2
        if '#' in s_str:
            obj_id = s_str.split('#')[-1]
        else:
            continue
        
        # Skip if empty or is the ontology namespace itself
        if not obj_id or obj_id == 'untitled-ontology-10':
            continue
        
        # Find or create object data
        obj_data = next((obj for obj in objects if obj['id'] == obj_id), None)
        if not obj_data:
            obj_data = {
                'id': obj_id,
                'type': None,
                'category': None,
                'description': None,
                'location': None,
                'affordances': []
            }
            objects.append(obj_data)
        
        # Extract property values
        # Type information (rdf:type predicate)
        if p_str.endswith('#type') or p_str.endswith('/type') or 'type' in p_str.split('#')[-1].split('/')[-1]:
            if 'Artifact' in o_str:
                obj_data['type'] = 'Artifact'
            elif 'Space' in o_str:
                obj_data['type'] = 'Space'
                locations.add(obj_id)
            elif 'Door' in o_str:
                obj_data['type'] = 'Door'
                locations.add(obj_id)
        
        # Category
        if 'category' in p_str.split('#')[-1].split('/')[-1]:
            category_val = o_str.strip('"').strip("'")
            obj_data['category'] = category_val
            if category_val:
                categories.add(category_val)
        
        # Description
        if 'description' in p_str.split('#')[-1].split('/')[-1]:
            desc_val = o_str.strip('"').strip("'")
            obj_data['description'] = desc_val
        
        # Location relationships
        if 'objectIsInSpace' in p_str or 'spaceIsInStorey' in p_str:
            if '#' in o_str:
                loc_id = o_str.split('#')[-1]
            elif '/' in o_str:
                loc_id = o_str.split('/')[-1]
            else:
                loc_id = o_str
            obj_data['location'] = loc_id
            locations.add(loc_id)
        
        # Affordances
        if 'affords' in p_str.split('#')[-1].split('/')[-1]:
            if '#' in o_str:
                aff_id = o_str.split('#')[-1]
            elif '/' in o_str:
                aff_id = o_str.split('/')[-1]
            else:
                aff_id = o_str
            if obj_id not in affordances_map:
                affordances_map[obj_id] = []
            if aff_id not in affordances_map[obj_id]:
                affordances_map[obj_id].append(aff_id)
            if aff_id not in obj_data['affordances']:
                obj_data['affordances'].append(aff_id)
    
    return {
        'objects': objects,
        'categories': sorted(list(categories)),
        'locations': sorted(list(locations)),
        'affordances_map': affordances_map
    }


def get_ttl_summary() -> str:
    """
    Get summary of TTL files for the active environment.
    
    Returns:
        Formatted string with objects, locations, and affordances
    """
    config = get_config()
    active_env = config.get_active_env()
    
    if not active_env:
        return "No active environment configured"
    
    # Build TTL file paths directly
    # TTL files are in ontology_server/data/envs/{env_id}/
    ontology_server_root = project_root / "ontology_server"
    env_dir = ontology_server_root / "data" / "envs" / active_env
    
    static_path = env_dir / "static.ttl" if env_dir.exists() else None
    dynamic_path = env_dir / "dynamic.ttl" if env_dir.exists() else None
    
    # Verify files exist
    if static_path and not static_path.exists():
        static_path = None
    if dynamic_path and not dynamic_path.exists():
        dynamic_path = None
    
    summary_parts = [f"Environment: {active_env}\n"]
    
    if static_path and static_path.exists():
        static_data = read_ttl_file(static_path)
        summary_parts.append(f"\n=== Static Objects (Spaces, Doors, etc.) ===")
        spaces = [o for o in static_data['objects'] if o['type'] == 'Space']
        doors = [o for o in static_data['objects'] if o['type'] == 'Door']
        summary_parts.append(f"Total Spaces: {len(spaces)}")
        summary_parts.append(f"Total Doors: {len(doors)}")
        summary_parts.append(f"All Locations ({len(static_data['locations'])}): {', '.join(sorted(static_data['locations']))}")
        summary_parts.append(f"All Categories: {', '.join(sorted(static_data['categories']))}")
        
        # All static objects with details
        if spaces or doors:
            summary_parts.append(f"\nAll Static Objects:")
            for obj in sorted(static_data['objects'], key=lambda x: x['id']):
                if obj['type'] in ['Space', 'Door']:
                    desc = f"  - {obj['id']} ({obj['type']})"
                    if obj['category']:
                        desc += f" [{obj['category']}]"
                    if obj['location']:
                        desc += f" in {obj['location']}"
                    summary_parts.append(desc)
    
    if dynamic_path and dynamic_path.exists():
        dynamic_data = read_ttl_file(dynamic_path)
        artifacts = [o for o in dynamic_data['objects'] if o['type'] == 'Artifact']
        summary_parts.append(f"\n=== Dynamic Objects (Artifacts) ===")
        summary_parts.append(f"Total Artifacts: {len(artifacts)}")
        summary_parts.append(f"All Categories ({len(dynamic_data['categories'])}): {', '.join(sorted(dynamic_data['categories']))}")
        summary_parts.append(f"All Referenced Locations ({len(dynamic_data['locations'])}): {', '.join(sorted(dynamic_data['locations']))}")
        
        # All artifacts with complete details (for goal formula generation)
        summary_parts.append(f"\nAll Artifacts (for goal formula generation):")
        for obj in sorted(artifacts, key=lambda x: x['id']):
            desc = f"  - {obj['id']}"
            if obj['category']:
                desc += f" ({obj['category']})"
            if obj['location']:
                desc += f" in {obj['location']}"
            if obj['affordances']:
                # Include ALL affordances (not just first 3)
                desc += f" [affords: {', '.join(sorted(obj['affordances']))}]"
            if obj['description']:
                desc += f" - {obj['description']}"
            summary_parts.append(desc)
    
    return "\n".join(summary_parts)


def extract_pddl_predicates(domain_path: Path) -> str:
    """
    Extract all predicates from PDDL domain file.
    
    Args:
        domain_path: Path to domain.pddl file
        
    Returns:
        Formatted string with all predicates and their descriptions
    """
    if not domain_path.exists():
        return "PDDL domain file not found"
    
    with open(domain_path, 'r') as f:
        content = f.read()
    
    # Extract predicates section (up to closing parenthesis before :derived)
    predicates_match = re.search(r'\(:predicates\s+(.*?)\s*\)\s*\(:derived', content, re.DOTALL)
    if not predicates_match:
        # Try to find predicates section ending
        predicates_match = re.search(r'\(:predicates\s+(.*?)\s*\)\s*(?:\(:derived|$)', content, re.DOTALL)
    
    if not predicates_match:
        return "No predicates section found in domain file"
    
    predicates_content = predicates_match.group(1)
    
    # Remove all comments (both ;; and inline ; comments)
    # First remove block comments (;;)
    predicates_content = re.sub(r';;.*?$', '', predicates_content, flags=re.MULTILINE)
    # Then remove inline comments (;)
    predicates_content = re.sub(r';\s*[^\n]*', '', predicates_content)
    
    # Parse predicates line by line (comments removed)
    result = ["=== PDDL Predicates ===\n"]
    lines = predicates_content.split('\n')
    
    current_predicate = []
    paren_count = 0
    
    for line in lines:
        stripped = line.strip()
        
        # Skip empty lines
        if not stripped:
            continue
        
        # Count parentheses to track predicate boundaries
        paren_count += stripped.count('(') - stripped.count(')')
        
        # Add line to current predicate
        current_predicate.append(stripped)
        
        # If parentheses are balanced, we have a complete predicate
        if paren_count == 0 and current_predicate:
            pred_str = ' '.join(current_predicate).strip()
            if pred_str:
                result.append(f"  {pred_str}")
            current_predicate = []
    
    # Handle any remaining predicate
    if current_predicate:
        pred_str = ' '.join(current_predicate).strip()
        if pred_str:
            result.append(f"  {pred_str}")
    
    return "\n".join(result)


def get_complete_environment_info() -> str:
    """
    Get complete environment information including:
    - All spaces from TTL
    - All artifacts from TTL
    - All PDDL predicates
    
    Returns:
        Formatted string with complete environment information
    """
    config = get_config()
    active_env = config.get_active_env()
    
    if not active_env:
        return "No active environment configured"
    
    # Build paths
    ontology_server_root = project_root / "ontology_server"
    env_dir = ontology_server_root / "data" / "envs" / active_env
    domain_path = project_root / "pddl" / "domain.pddl"
    
    static_path = env_dir / "static.ttl" if env_dir.exists() else None
    dynamic_path = env_dir / "dynamic.ttl" if env_dir.exists() else None
    
    # Verify files exist
    if static_path and not static_path.exists():
        static_path = None
    if dynamic_path and not dynamic_path.exists():
        dynamic_path = None
    
    info_parts = [f"Environment: {active_env}\n"]
    
    # 1. PDDL Predicates
    info_parts.append("\n" + "=" * 60)
    pddl_predicates = extract_pddl_predicates(domain_path)
    info_parts.append(pddl_predicates)
    
    # 2. All Spaces from static.ttl
    info_parts.append("\n" + "=" * 60)
    info_parts.append("=== All Spaces (from static.ttl) ===")
    
    if static_path and static_path.exists():
        static_data = read_ttl_file(static_path)
        spaces = [o for o in static_data['objects'] if o['type'] == 'Space']
        
        info_parts.append(f"\nTotal Spaces: {len(spaces)}\n")
        
        for obj in sorted(spaces, key=lambda x: x['id']):
            space_info = f"  - {obj['id']}"
            if obj['category']:
                space_info += f" (category: {obj['category']})"
            if obj['location']:
                space_info += f" (in: {obj['location']})"
            if obj['description']:
                space_info += f"\n    Description: {obj['description']}"
            info_parts.append(space_info)
    else:
        info_parts.append("\nNo static.ttl file found")
    
    # 3. All Artifacts from dynamic.ttl
    info_parts.append("\n" + "=" * 60)
    info_parts.append("=== All Artifacts (from dynamic.ttl) ===")
    
    if dynamic_path and dynamic_path.exists():
        dynamic_data = read_ttl_file(dynamic_path)
        artifacts = [o for o in dynamic_data['objects'] if o['type'] == 'Artifact']
        
        info_parts.append(f"\nTotal Artifacts: {len(artifacts)}\n")
        
        for obj in sorted(artifacts, key=lambda x: x['id']):
            artifact_info = f"  - {obj['id']}"
            if obj['category']:
                artifact_info += f" (category: {obj['category']})"
            if obj['location']:
                artifact_info += f" (location: {obj['location']})"
            if obj['affordances']:
                artifact_info += f"\n    Affordances: {', '.join(sorted(obj['affordances']))}"
            if obj['description']:
                artifact_info += f"\n    Description: {obj['description']}"
            info_parts.append(artifact_info)
    else:
        info_parts.append("\nNo dynamic.ttl file found")
    
    return "\n".join(info_parts)

