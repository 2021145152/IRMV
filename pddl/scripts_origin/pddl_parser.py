#!/usr/bin/env python3
"""PDDL Domain Parser - Extract types and hierarchy from domain.pddl."""

import re
from pathlib import Path
from typing import Dict, Set, List


class PDDLDomainParser:
    """Parse PDDL domain file to extract types and hierarchy."""

    def __init__(self, domain_path: str):
        """Initialize parser with domain file path."""
        self.domain_path = Path(domain_path)
        self.types_hierarchy = {}  # type -> parent_type
        self.all_types = set()
        self._parse_domain()

    def _parse_domain(self):
        """Parse domain file and extract types."""
        with open(self.domain_path, 'r') as f:
            content = f.read()

        types_match = re.search(r'\(:types\s+(.*?)\)', content, re.DOTALL)
        if not types_match:
            print("WARNING: No types section found in domain")
            return

        types_content = types_match.group(1)
        lines = types_content.strip().split('\n')

        for line in lines:
            line = line.strip()
            if not line or line.startswith(';'):
                continue

            if '-' in line:
                parts = line.split('-')
                children = parts[0].strip().split()
                parent = parts[1].strip()

                self.all_types.add(parent)
                if parent not in self.types_hierarchy:
                    self.types_hierarchy[parent] = None

                for child in children:
                    child = child.strip()
                    if child:
                        self.all_types.add(child)
                        self.types_hierarchy[child] = parent
            else:
                types = line.split()
                for t in types:
                    t = t.strip()
                    if t:
                        self.all_types.add(t)
                        if t not in self.types_hierarchy:
                            self.types_hierarchy[t] = None

        print(f"Parsed domain types: {sorted(self.all_types)}")

    def get_all_types(self) -> Set[str]:
        """Get all types defined in domain."""
        return self.all_types

    def get_type_hierarchy(self) -> Dict[str, str]:
        """Get type hierarchy (child -> parent mapping)."""
        return self.types_hierarchy

    def get_root_types(self) -> Set[str]:
        """Get root types (types with no parent)."""
        return {t for t, parent in self.types_hierarchy.items() if parent is None}

    def get_children_types(self, parent_type: str) -> Set[str]:
        """Get all direct children of a type."""
        return {t for t, p in self.types_hierarchy.items() if p == parent_type}

    def is_subtype_of(self, child_type: str, parent_type: str) -> bool:
        """Check if child_type is a subtype of parent_type."""
        if child_type == parent_type:
            return True

        current = child_type
        while current in self.types_hierarchy:
            parent = self.types_hierarchy[current]
            if parent == parent_type:
                return True
            current = parent

        return False

    def map_class_to_domain_type(self, class_names: List[str]) -> str:
        """
        Map ontology class names to domain type.
        Returns the most specific domain type that matches.

        Args:
            class_names: List of class names from ontology

        Returns:
            Domain type string
        """
        matching_types = []
        for class_name in class_names:
            if class_name in self.all_types:
                matching_types.append(class_name)

        if not matching_types:
            return None

        for candidate in matching_types:
            is_most_specific = True
            for other in matching_types:
                if candidate != other and self.is_subtype_of(other, candidate):
                    is_most_specific = False
                    break
            if is_most_specific:
                return candidate

        return matching_types[0]


if __name__ == "__main__":
    # Test parser
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    domain_path = Path(__file__).parent.parent / "domain.pddl"
    parser = PDDLDomainParser(domain_path)

    print("\n" + "=" * 60)
    print("PDDL Domain Type Parser Test")
    print("=" * 60)

    print(f"\nAll types: {sorted(parser.get_all_types())}")
    print(f"\nRoot types: {sorted(parser.get_root_types())}")
    print(f"\nType hierarchy:")
    for child, parent in sorted(parser.get_type_hierarchy().items()):
        parent_str = parent if parent else "None"
        print(f"  {child} -> {parent_str}")

    # Test mapping
    print(f"\nTest mappings:")
    test_cases = [
        ['Space', 'Location'],
        ['Door', 'Location'],
        ['Artifact'],
        ['Robot'],
        ['Hand']
    ]
    for classes in test_cases:
        result = parser.map_class_to_domain_type(classes)
        print(f"  {classes} -> {result}")
