#!/usr/bin/env python3
"""
Detailed verification using rdflib to compare all triples between dynamic TTL files.
"""

import re
from pathlib import Path
from typing import Dict, Set, Tuple, List
from rdflib import Graph, URIRef
from rdflib.namespace import RDF

def extract_robot_location_rdflib(ttl_path: Path) -> str:
    """Extract robot1's location from TTL file using rdflib."""
    g = Graph()
    g.parse(str(ttl_path), format="turtle")
    
    # Find robot1's robotIsInSpace property
    robot1 = URIRef("http://www.semanticweb.org/namh_woo/ontologies/2025/9/untitled-ontology-10#robot1")
    robotIsInSpace = URIRef("http://www.semanticweb.org/namh_woo/ontologies/2025/9/untitled-ontology-10#robotIsInSpace")
    
    for obj in g.objects(robot1, robotIsInSpace):
        # Extract local name from URI
        uri_str = str(obj)
        if '#' in uri_str:
            return uri_str.split('#')[-1]
        return str(obj)
    
    return None

def compare_triples_rdflib(file1: Path, file2: Path) -> Dict:
    """Compare two TTL files using rdflib and return differences."""
    g1 = Graph()
    g2 = Graph()
    
    g1.parse(str(file1), format="turtle")
    g2.parse(str(file2), format="turtle")
    
    # Get all triples
    triples1 = set(g1)
    triples2 = set(g2)
    
    added = triples2 - triples1
    removed = triples1 - triples2
    
    # Filter robot location changes
    robot1_uri = URIRef("http://www.semanticweb.org/namh_woo/ontologies/2025/9/untitled-ontology-10#robot1")
    robotIsInSpace_uri = URIRef("http://www.semanticweb.org/namh_woo/ontologies/2025/9/untitled-ontology-10#robotIsInSpace")
    
    robot_location_added = set()
    robot_location_removed = set()
    other_added = set()
    other_removed = set()
    
    for triple in added:
        if triple[0] == robot1_uri and triple[1] == robotIsInSpace_uri:
            robot_location_added.add(triple)
        else:
            other_added.add(triple)
    
    for triple in removed:
        if triple[0] == robot1_uri and triple[1] == robotIsInSpace_uri:
            robot_location_removed.add(triple)
        else:
            other_removed.add(triple)
    
    return {
        'robot_location_added': robot_location_added,
        'robot_location_removed': robot_location_removed,
        'other_added': other_added,
        'other_removed': other_removed,
        'total_added': len(added),
        'total_removed': len(removed)
    }

def main():
    project_root = Path(__file__).parent
    world_dir = project_root / "action" / "world"
    plan_file = project_root / "action" / "plan" / "solution.plan"
    
    # Read plan
    with open(plan_file, 'r') as f:
        plan_lines = [line.strip() for line in f if line.strip() and not line.strip().startswith(';')]
    
    # Parse plan actions
    expected_locations = []
    expected_locations.append("corridor_14")  # Initial location
    
    for line in plan_lines:
        match = re.match(r'\(move\s+robot1\s+\w+\s+(\w+)\)', line)
        if match:
            expected_locations.append(match.group(1))
    
    print("=" * 80)
    print("Detailed Robot Location Verification (using rdflib)")
    print("=" * 80)
    print(f"\nExpected locations from solution.plan:")
    for i, loc in enumerate(expected_locations):
        print(f"  dynamic_{i}.ttl: {loc}")
    
    print(f"\n{'='*80}")
    print("Checking actual locations in TTL files...")
    print(f"{'='*80}\n")
    
    # Check each file
    actual_locations = []
    all_match = True
    
    for i in range(len(expected_locations)):
        ttl_file = world_dir / f"dynamic_{i}.ttl"
        if not ttl_file.exists():
            print(f"❌ dynamic_{i}.ttl not found!")
            all_match = False
            continue
        
        location = extract_robot_location_rdflib(ttl_file)
        actual_locations.append(location)
        expected = expected_locations[i]
        
        if location == expected:
            print(f"✅ dynamic_{i}.ttl: {location} (expected: {expected})")
        else:
            print(f"❌ dynamic_{i}.ttl: {location} (expected: {expected})")
            all_match = False
    
    print(f"\n{'='*80}")
    print("Detailed comparison between consecutive files...")
    print(f"{'='*80}\n")
    
    # Compare consecutive files using rdflib
    other_changes_found = False
    
    for i in range(len(expected_locations) - 1):
        file1 = world_dir / f"dynamic_{i}.ttl"
        file2 = world_dir / f"dynamic_{i+1}.ttl"
        
        if not file1.exists() or not file2.exists():
            continue
        
        diff = compare_triples_rdflib(file1, file2)
        
        print(f"dynamic_{i}.ttl → dynamic_{i+1}.ttl:")
        print(f"  Robot location changes: {len(diff['robot_location_added'])} added, {len(diff['robot_location_removed'])} removed")
        
        if diff['other_added'] or diff['other_removed']:
            print(f"  ⚠️  OTHER CHANGES DETECTED:")
            print(f"     - Other triples added: {len(diff['other_added'])}")
            print(f"     - Other triples removed: {len(diff['other_removed'])}")
            
            # Show some examples
            if diff['other_added']:
                print(f"     Examples of added triples:")
                for triple in list(diff['other_added'])[:3]:
                    print(f"       + {triple}")
            if diff['other_removed']:
                print(f"     Examples of removed triples:")
                for triple in list(diff['other_removed'])[:3]:
                    print(f"       - {triple}")
            
            other_changes_found = True
        else:
            print(f"  ✅ Only robot location changed (no other changes)")
        print()
    
    print(f"{'='*80}")
    print("Summary")
    print(f"{'='*80}")
    
    if all_match and not other_changes_found:
        print("✅ SUCCESS: All robot locations match plan, and no other changes detected!")
        print("   All dynamic TTL files only differ in robot1's robotIsInSpace property.")
    else:
        if not all_match:
            print("❌ FAILED: Some robot locations don't match the plan")
        if other_changes_found:
            print("❌ FAILED: Other changes detected besides robot location")
            print("   This means files have additional differences beyond robot position.")

if __name__ == "__main__":
    main()

