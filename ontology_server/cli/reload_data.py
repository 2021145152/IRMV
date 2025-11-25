#!/usr/bin/env python3
"""
Fast Data Reload Script
Reloads TTL data to Neo4j without restarting server or Docker.
This is faster than reset_neo4j.sh + start.sh
"""

import requests
import sys
from pathlib import Path
from typing import Dict, Any, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ontology_server.core.config import get_config
from ontology_server.core.env import EnvManager


class FastReloader:
    """Fast reloader for TTL data without restarting services."""

    def __init__(self, api_url: Optional[str] = None):
        """Initialize fast reloader."""
        if api_url is None:
            config = get_config()
            server_config = config.get_server_config()
            api_url = server_config.get('base_url', 'http://localhost:8000')
        self.api_url = api_url

    def check_server(self) -> bool:
        """Check if ontology manager server is running."""
        try:
            response = requests.get(f"{self.api_url}/health", timeout=5)
            if response.status_code == 200:
                print(f"✓ Server is running at {self.api_url}")
                return True
            else:
                print(f"✗ Server returned status {response.status_code}")
                return False
        except requests.exceptions.ConnectionError:
            print(f"✗ Cannot connect to server at {self.api_url}")
            print("  Make sure the server is running: python cli/run_server.py")
            return False
        except Exception as e:
            print(f"✗ Error checking server: {e}")
            return False

    def clear_neo4j_individuals(self) -> bool:
        """
        Clear only Individual nodes from Neo4j (keeps schema).
        This is faster than deleting all nodes.
        """
        try:
            # Use direct Neo4j connection to clear individuals
            from ontology_server.core.ontology import OntologyManager
            
            # Get manager instance (this will connect to Neo4j)
            config = get_config()
            neo4j_config = config.get_neo4j_config()
            
            from neo4j import GraphDatabase
            driver = GraphDatabase.driver(
                neo4j_config['uri'],
                auth=(neo4j_config['user'], neo4j_config['password'])
            )
            
            with driver.session() as session:
                result = session.run("MATCH (i:Individual) DETACH DELETE i RETURN count(i) as deleted")
                record = result.single()
                deleted_count = record["deleted"] if record else 0
                print(f"✓ Cleared {deleted_count} individual nodes from Neo4j")
            
            driver.close()
            return True
        except Exception as e:
            print(f"✗ Failed to clear Neo4j individuals: {e}")
            return False

    def reload_static(self, ttl_path: str) -> Dict[str, Any]:
        """Reload static TTL data."""
        try:
            print(f"\n📂 Loading static data from: {ttl_path}")
            response = requests.post(
                f"{self.api_url}/load_ttl",
                json={"file_path": str(ttl_path)},
                timeout=300
            )

            if response.status_code == 200:
                result = response.json()
                added_count = result.get("added", 0)
                failed_count = result.get("failed", 0)
                print(f"✓ Successfully loaded {added_count} static individuals")
                if failed_count > 0:
                    print(f"⚠ Failed to load {failed_count} individuals")
                return result
            else:
                error_detail = response.json().get("detail", "Unknown error")
                print(f"✗ Request failed: {error_detail}")
                return {"status": "error", "message": error_detail}

        except Exception as e:
            print(f"✗ Error loading static data: {e}")
            return {"status": "error", "message": str(e)}

    def reload_dynamic(self, ttl_path: str) -> Dict[str, Any]:
        """Reload dynamic TTL data."""
        try:
            print(f"\n📂 Loading dynamic data from: {ttl_path}")
            response = requests.post(
                f"{self.api_url}/load_ttl",
                json={"file_path": str(ttl_path)},
                timeout=300
            )

            if response.status_code == 200:
                result = response.json()
                added_count = result.get("added", 0)
                failed_count = result.get("failed", 0)
                print(f"✓ Successfully loaded {added_count} dynamic individuals")
                if failed_count > 0:
                    print(f"⚠ Failed to load {failed_count} individuals")
                return result
            else:
                error_detail = response.json().get("detail", "Unknown error")
                print(f"✗ Request failed: {error_detail}")
                return {"status": "error", "message": error_detail}

        except Exception as e:
            print(f"✗ Error loading dynamic data: {e}")
            return {"status": "error", "message": str(e)}


def main():
    """Main function for command-line usage."""
    print("=" * 60)
    print("Fast Data Reload")
    print("=" * 60)
    print("This script reloads TTL data without restarting server/Docker")
    print()

    # Load configuration
    config = get_config()
    active_env = config.get_active_env()
    server_config = config.get_server_config()
    api_url = server_config.get('base_url', f"http://localhost:{server_config['port']}")

    if not active_env:
        print("✗ ERROR: No active environment configured in config.yaml")
        print("  Please set 'active_env' in ontology_server/config.yaml")
        sys.exit(1)

    # Get file paths
    env_manager = EnvManager()
    static_path = env_manager.get_static_file_path(active_env)
    dynamic_path = env_manager.get_dynamic_file_path(active_env)

    if not static_path:
        print(f"✗ ERROR: Environment '{active_env}' has no static.ttl file")
        sys.exit(1)
    if not dynamic_path:
        print(f"✗ ERROR: Environment '{active_env}' has no dynamic.ttl file")
        sys.exit(1)

    print(f"Active Environment: {active_env}")
    print(f"Static TTL: {static_path}")
    print(f"Dynamic TTL: {dynamic_path}")
    print()

    reloader = FastReloader(api_url=api_url)

    # Check server
    if not reloader.check_server():
        sys.exit(1)

    # Clear existing individuals (optional - load_ttl will sync anyway)
    # Uncomment if you want to explicitly clear first
    # print("\n🗑️  Clearing existing individuals from Neo4j...")
    # if not reloader.clear_neo4j_individuals():
    #     print("⚠ Warning: Failed to clear individuals, but continuing...")

    # Reload static data
    print("\n" + "=" * 60)
    print("Step 1: Reloading Static Data")
    print("=" * 60)
    static_result = reloader.reload_static(str(static_path))
    if static_result.get("status") == "error":
        print(f"\n✗ Failed to reload static data")
        sys.exit(1)

    # Reload dynamic data
    print("\n" + "=" * 60)
    print("Step 2: Reloading Dynamic Data")
    print("=" * 60)
    dynamic_result = reloader.reload_dynamic(str(dynamic_path))
    if dynamic_result.get("status") == "error":
        print(f"\n✗ Failed to reload dynamic data")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("✓ Data reload complete!")
    print("=" * 60)
    print(f"Static: {static_result.get('added', 0)} individuals")
    print(f"Dynamic: {dynamic_result.get('added', 0)} individuals")
    print("\nNote: Server and Neo4j are still running - no restart needed!")


if __name__ == "__main__":
    main()

