#!/usr/bin/env python3
"""
Verify that only robot location changes between dynamic TTL files.
Compares all dynamic_N.ttl files and checks against solution.plan.
"""

import re
from pathlib import Path
from typing import Dict, Set, Tuple, List

def extract_robot_location(ttl_path: Path) -> str:
    """Extract robot1's location from TTL file."""
    with open(ttl_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find robot1 block
    match = re.search(r':robot1\s+rdf:type\s+:Robot\s*;(.*?)(?=\n\n|\n:[a-z_]|\Z)', content, re.DOTALL)
    if not match:
        return None
    
    robot_block = match.group(1)
    
    # Extract robotIsInSpace value
    location_match = re.search(r':robotIsInSpace\s+:(\w+)', robot_block)
    if location_match:
        return location_match.group(1)
    
    return None

def extract_all_triples(ttl_path: Path) -> Set[Tuple[str, str, str]]:
    """Extract all triples from TTL file for comparison."""
    triples = set()
    
    with open(ttl_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Extract all subject-predicate-object triples
    # Pattern: :subject rdf:type :Type ; or :subject :predicate :object ;
    pattern = r':(\w+)\s+(?:rdf:type\s+)?:(\w+)\s+:(?:(\w+)|"([^"]+)"|(\d+\.?\d*))'
    
    for match in re.finditer(pattern, content):
        subject = match.group(1)
        predicate = match.group(2)
        obj = match.group(3) or match.group(4) or match.group(5)
        if obj:
            triples.add((subject, predicate, obj))
    
    return triples

def compare_files(file1: Path, file2: Path) -> Dict:
    """Compare two TTL files and return differences."""
    triples1 = extract_all_triples(file1)
    triples2 = extract_all_triples(file2)
    
    added = triples2 - triples1
    removed = triples1 - triples2
    
    return {
        'added': added,
        'removed': removed,
        'same': triples1 & triples2
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
    print("Robot Location Verification")
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
        
        location = extract_robot_location(ttl_file)
        actual_locations.append(location)
        expected = expected_locations[i]
        
        if location == expected:
            print(f"✅ dynamic_{i}.ttl: {location} (expected: {expected})")
        else:
            print(f"❌ dynamic_{i}.ttl: {location} (expected: {expected})")
            all_match = False
    
    print(f"\n{'='*80}")
    print("Checking for other changes between files...")
    print(f"{'='*80}\n")
    
    # Compare consecutive files to check for other changes
    other_changes_found = False
    
    for i in range(len(expected_locations) - 1):
        file1 = world_dir / f"dynamic_{i}.ttl"
        file2 = world_dir / f"dynamic_{i+1}.ttl"
        
        if not file1.exists() or not file2.exists():
            continue
        
        diff = compare_files(file1, file2)
        
        # Filter out robot location changes
        robot_location_added = set()
        robot_location_removed = set()
        other_added = set()
        other_removed = set()
        
        for triple in diff['added']:
            if triple[0] == 'robot1' and triple[1] == 'robotIsInSpace':
                robot_location_added.add(triple)
            else:
                other_added.add(triple)
        
        for triple in diff['removed']:
            if triple[0] == 'robot1' and triple[1] == 'robotIsInSpace':
                robot_location_removed.add(triple)
            else:
                other_removed.add(triple)
        
        if other_added or other_removed:
            print(f"⚠️  dynamic_{i}.ttl → dynamic_{i+1}.ttl: Other changes detected!")
            if other_added:
                print(f"   Added (non-robot): {len(other_added)} triples")
                for triple in list(other_added)[:5]:  # Show first 5
                    print(f"     + {triple}")
                if len(other_added) > 5:
                    print(f"     ... and {len(other_added) - 5} more")
            if other_removed:
                print(f"   Removed (non-robot): {len(other_removed)} triples")
                for triple in list(other_removed)[:5]:  # Show first 5
                    print(f"     - {triple}")
                if len(other_removed) > 5:
                    print(f"     ... and {len(other_removed) - 5} more")
            other_changes_found = True
        else:
            print(f"✅ dynamic_{i}.ttl → dynamic_{i+1}.ttl: Only robot location changed")
    
    print(f"\n{'='*80}")
    print("Summary")
    print(f"{'='*80}")
    
    if all_match and not other_changes_found:
        print("✅ SUCCESS: All robot locations match plan, and no other changes detected!")
    else:
        if not all_match:
            print("❌ FAILED: Some robot locations don't match the plan")
        if other_changes_found:
            print("❌ FAILED: Other changes detected besides robot location")

if __name__ == "__main__":
    main()

