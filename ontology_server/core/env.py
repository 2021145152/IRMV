#!/usr/bin/env python3
"""
EnvManager: Manage multiple environments with shared ontology
"""

from pathlib import Path
from typing import Dict, Any, List, Optional
from .config import get_config


class EnvManager:
    """Manage different environments that share the same ontology schema."""

    def __init__(self):
        """Initialize environment manager."""
        config = get_config()
        self.data_root = Path(config.get_data_config()['root'])
        self.envs_dir = Path(config.get_data_config()['envs_dir'])
        self.ontology_path = Path(config.get_data_config()['ontology'])

        # Get environment configurations from config.yaml
        self._envs = config.config.get('environments', {})

    def list_envs(self) -> List[Dict[str, Any]]:
        """List all available environments."""
        envs = []
        for env_id, env_config in self._envs.items():
            env_path = self.envs_dir / env_id
            if env_path.exists():
                envs.append({
                    'env_id': env_id,
                    'env_name': env_config.get('name', env_id),
                    'description': env_config.get('description', ''),
                    'path': str(env_path)
                })
        return envs

    def get_env_config(self, env_id: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a specific environment."""
        return self._envs.get(env_id)

    def get_env_path(self, env_id: str) -> Optional[Path]:
        """Get directory path for a specific environment."""
        env_path = self.envs_dir / env_id
        return env_path if env_path.exists() else None

    def get_static_file_path(self, env_id: str) -> Optional[Path]:
        """Get static data file path for an environment (TTL format)."""
        env_path = self.get_env_path(env_id)
        if not env_path:
            return None

        static_path = env_path / "static.ttl"
        return static_path if static_path.exists() else None

    def get_dynamic_file_path(self, env_id: str) -> Optional[Path]:
        """Get dynamic data file path for an environment (TTL format)."""
        env_path = self.get_env_path(env_id)
        if not env_path:
            return None

        dynamic_path = env_path / "dynamic.ttl"
        return dynamic_path if dynamic_path.exists() else None

    def env_exists(self, env_id: str) -> bool:
        """Check if an environment exists."""
        return env_id in self._envs and (self.envs_dir / env_id).exists()

    def get_ontology_path(self) -> Path:
        """Get shared ontology file path."""
        return self.ontology_path

    def get_summary(self) -> Dict[str, Any]:
        """Get summary of all environments."""
        summary = {
            "total_envs": len(self._envs),
            "ontology_file": str(self.ontology_path),
            "environments": []
        }

        for env_id, env_config in self._envs.items():
            env_path = self.envs_dir / env_id

            if not env_path.exists():
                continue

            # Check if data files exist
            static_path = self.get_static_file_path(env_id)
            dynamic_path = self.get_dynamic_file_path(env_id)

            summary["environments"].append({
                "env_id": env_id,
                "env_name": env_config.get('name', env_id),
                "description": env_config.get('description', ''),
                "static_file": static_path.name if static_path else "Not found",
                "dynamic_file": dynamic_path.name if dynamic_path else "Not found"
            })

        return summary


if __name__ == "__main__":
    # Test
    manager = EnvManager()

    print("=" * 60)
    print("Available Environments")
    print("=" * 60)

    envs = manager.list_envs()
    for env in envs:
        print(f"\n{env['env_name']} ({env['env_id']})")
        print(f"   {env['description']}")
        print(f"   Path: {env['path']}")

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)

    summary = manager.get_summary()
    print(f"\nTotal environments: {summary['total_envs']}")
    print(f"Shared ontology: {summary['ontology_file']}")

    for env_info in summary['environments']:
        print(f"\n  {env_info['env_name']}:")
        print(f"    Static: {env_info['static_file']}")
        print(f"    Dynamic: {env_info['dynamic_file']}")
