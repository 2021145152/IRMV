#!/usr/bin/env python3
"""
Graph Query Tools CLI - Execute graph query tools with config file

Usage:
    # Run tool specified in config (current_tool)
    python cli/query_tools.py

    # Run specific tool
    python cli/query_tools.py get_object_info
    python cli/query_tools.py filter_objects
    python cli/query_tools.py find_path
    python cli/query_tools.py semantic_search

    # Use custom config file
    python cli/query_tools.py --config my_config.yaml
"""

import sys
import json
import yaml
import argparse
from pathlib import Path
from typing import Dict, Any

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.graph_tools import GraphTools
from tools.semantic_tool import SemanticTool
from core.config import get_config


class QueryRunner:
    """Execute graph query tools with config-based parameters."""

    def __init__(self, config_path: str = "tools/config.yaml"):
        """Initialize query runner."""
        self.config_path = Path(config_path)
        self.query_config = self._load_config()

        # Load Neo4j config
        main_config = get_config()
        neo4j_config = main_config.get_neo4j_config()
        embedding_config = main_config.get_embedding_config()

        # Initialize tools
        self.graph_tools = GraphTools(
            neo4j_uri=neo4j_config['uri'],
            neo4j_user=neo4j_config['user'],
            neo4j_password=neo4j_config['password']
        )

        # Extract category and description configs
        category_config = embedding_config.get('category', {})
        description_config = embedding_config.get('description', {})

        self.semantic_tool = SemanticTool(
            neo4j_uri=neo4j_config['uri'],
            neo4j_user=neo4j_config['user'],
            neo4j_password=neo4j_config['password'],
            category_model=category_config.get('model', 'text-embedding-3-small'),
            category_dimensions=category_config.get('dimensions'),
            description_model=description_config.get('model', 'text-embedding-3-small'),
            description_dimensions=description_config.get('dimensions')
        )

    def _load_config(self) -> Dict[str, Any]:
        """Load query configuration."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config not found: {self.config_path}")

        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f)

    def run_get_object_info(self):
        """Run get_object_info tool."""
        config = self.query_config['queries']['get_object_info']
        object_ids = config['object_ids']

        print("=" * 80)
        print("Tool: get_object_info")
        print("=" * 80)
        print(f"Parameters:")
        print(f"  object_ids: {object_ids}")
        print()

        result = self.graph_tools.get_object_info(object_ids)

        if result:
            print("Result:")
            print(json.dumps(result, indent=2, ensure_ascii=False))
        elif isinstance(object_ids, str):
            print(f"Object not found: {object_ids}")
        else:
            print(f"No objects found")

    def run_filter_objects(self):
        """Run filter_objects tool."""
        config = self.query_config['queries']['filter_objects']

        print("=" * 80)
        print("Tool: filter_objects")
        print("=" * 80)
        print(f"Parameters:")
        for key, value in config.items():
            print(f"  {key}: {value}")
        print()

        results = self.graph_tools.filter_objects(**config)

        print(f"Found {len(results)} objects:")
        print()
        for obj in results:
            print(f"{obj['id']}")
            if obj['comment']:
                print(f"  Description: {obj['comment'][:80]}...")
            print(f"  Location: {obj['location']['space']} (Floor: {obj['location']['storey']})")
            if obj['key_properties']:
                print(f"  Properties: {obj['key_properties']}")
            if obj['affordances']:
                print(f"  Affordances: {', '.join(obj['affordances'])}")
            print()

    def run_find_path(self):
        """Run find_path tool."""
        config = self.query_config['queries']['find_path']
        from_id = config['from_id']
        to_id = config['to_id']

        print("=" * 80)
        print("Tool: find_path")
        print("=" * 80)
        print(f"Parameters:")
        print(f"  from_id: {from_id}")
        print(f"  to_id: {to_id}")
        print()

        result = self.graph_tools.find_path(from_id, to_id)

        if result:
            print("Path found:")
            print(f"  Distance: {result['distance']:.2f}")
            print(f"  Nodes: {result['num_nodes']}")
            print()
            print("Path:")
            for i, node in enumerate(result['path'], 1):
                # Only show node ID
                print(f"  {i}. {node['id']}")
            print()
        else:
            print(f"No path found from {from_id} to {to_id}")

    def run_semantic_search(self):
        """Run semantic_search tool."""
        config = self.query_config['queries']['semantic_search']
        query = config['query']
        top_k = config.get('top_k', 5)

        print("=" * 80)
        print("Tool: semantic_search")
        print("=" * 80)
        print(f"Parameters:")
        print(f"  query: {query}")
        print(f"  top_k: {top_k}")
        print()

        results = self.semantic_tool.search(query, top_k)

        print(f"Found {len(results)} results:")
        print()
        for i, result in enumerate(results, 1):
            print(f"{i}. {result['id']} (Score: {result['similarity']:.3f})")
            if result['comment']:
                print(f"   Description: {result['comment']}")

            # Format location
            location_parts = []
            if result.get('location'):
                location_parts.append(result['location'])
            if result.get('inside_of'):
                location_parts.append(f"inside {result['inside_of']}")
            if result.get('on_top_of'):
                location_parts.append(f"on {result['on_top_of']}")

            if location_parts:
                print(f"   Location: {', '.join(location_parts)}")
            print()

    def run_query(self, tool_name: str):
        """Run query for specified tool."""
        methods = {
            'get_object_info': self.run_get_object_info,
            'filter_objects': self.run_filter_objects,
            'find_path': self.run_find_path,
            'semantic_search': self.run_semantic_search
        }

        if tool_name not in methods:
            print(f"Unknown tool: {tool_name}")
            print(f"Available tools: {', '.join(methods.keys())}")
            return

        try:
            methods[tool_name]()
        except Exception as e:
            print(f"Error running {tool_name}: {e}")
            import traceback
            traceback.print_exc()

    def close(self):
        """Close connections."""
        self.graph_tools.close()
        self.semantic_tool.close()


def main():
    parser = argparse.ArgumentParser(
        description="Graph Query Tools CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        "tool",
        nargs="?",
        help="Tool name to run (get_object_info, filter_objects, find_path, semantic_search)"
    )
    parser.add_argument(
        "--config", "-c",
        default="tools/config.yaml",
        help="Config file path (default: tools/config.yaml)"
    )

    args = parser.parse_args()

    # Initialize runner
    runner = QueryRunner(config_path=args.config)

    try:
        # Determine which tool to run
        if args.tool:
            tool_name = args.tool
        else:
            tool_name = runner.query_config.get('current_tool', 'get_object_info')

        print(f"Running tool: {tool_name}")
        print(f"Config: {args.config}")
        print()

        # Run query
        runner.run_query(tool_name)

    finally:
        runner.close()


if __name__ == "__main__":
    main()
