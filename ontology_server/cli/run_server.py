#!/usr/bin/env python3
"""
Run Ontology Manager Server
Start FastAPI server for real-time ontology management
"""

import uvicorn
import sys
import os
import signal
import time
from pathlib import Path
import importlib

# CRITICAL: Add current directory to FRONT of sys.path to prevent wrong ontology_server import
current_dir = str(Path(__file__).parent.parent.parent)
# Remove any existing ontology_server paths from sys.path
sys.path = [p for p in sys.path if 'ontology_server' not in p or current_dir in p]
# Insert current directory at the very beginning
sys.path.insert(0, current_dir)

# Clear Python import cache to ensure fresh code
importlib.invalidate_caches()


def kill_existing_servers():
    """Kill any existing ontology server processes."""
    import subprocess

    print("Checking for existing server processes...")

    try:
        # Find processes
        result = subprocess.run(
            ["ps", "aux"],
            capture_output=True,
            text=True
        )

        killed_count = 0
        for line in result.stdout.split('\n'):
            if 'uvicorn' in line and 'ontology_server' in line and str(os.getpid()) not in line:
                try:
                    pid = int(line.split()[1])
                    os.kill(pid, signal.SIGTERM)
                    killed_count += 1
                    print(f"  Killed existing server (PID: {pid})")
                except:
                    pass
            elif 'run_server.py' in line and str(os.getpid()) not in line:
                try:
                    pid = int(line.split()[1])
                    os.kill(pid, signal.SIGTERM)
                    killed_count += 1
                    print(f"  Killed existing server script (PID: {pid})")
                except:
                    pass

        if killed_count > 0:
            print(f"  Waiting for processes to terminate...")
            time.sleep(3)

            # Check again and force kill if still alive
            result2 = subprocess.run(
                ["ps", "aux"],
                capture_output=True,
                text=True
            )

            force_killed = 0
            for line in result2.stdout.split('\n'):
                if 'uvicorn' in line and 'ontology_server' in line and str(os.getpid()) not in line:
                    try:
                        pid = int(line.split()[1])
                        os.kill(pid, signal.SIGKILL)
                        force_killed += 1
                        print(f"  WARNING: Force killed stubborn process (PID: {pid})")
                    except:
                        pass
                elif 'run_server.py' in line and str(os.getpid()) not in line:
                    try:
                        pid = int(line.split()[1])
                        os.kill(pid, signal.SIGKILL)
                        force_killed += 1
                        print(f"  WARNING: Force killed stubborn script (PID: {pid})")
                    except:
                        pass

            if force_killed > 0:
                time.sleep(2)
        else:
            print("  No existing servers found")

    except Exception as e:
        print(f"  WARNING: Error checking processes: {e}")


def main():
    """Run the FastAPI server."""
    # Import config inside main to avoid early module loading
    from ontology_server.core.config import get_config

    # Load configuration
    config = get_config()
    active_env = config.get_active_env()
    server_config = config.get_server_config()

    # Set environment variable for environment
    if active_env:
        os.environ['ONTOLOGY_ENV_ID'] = active_env

    # Print startup info
    print("=" * 60)
    if active_env:
        print(f"Starting Ontology Manager Server")
        print(f"Active Environment: {active_env}")
    else:
        print("Starting Ontology Manager Server (No specific environment)")
    print("=" * 60)
    print()

    # Kill existing servers
    kill_existing_servers()

    print()
    if active_env:
        from ontology_server.core.env import EnvManager
        env_manager = EnvManager()
        env_config = env_manager.get_env_config(active_env)
        if env_config:
            print(f"Environment: {env_config['name']}")
            print(f"   {env_config['description']}")
            print()

    host = server_config['host']
    port = server_config['port']

    print("API Documentation will be available at:")
    print(f"   http://localhost:{port}/docs")
    print()
    print("Neo4j Browser:")
    print("   http://localhost:7474")
    print()
    print("WARNING: Server starts with CLEAN STATE")
    print("   All previous ontology data will be cleared on startup")
    print()
    print("To change environment, edit: config.yaml")
    print("   Then restart the server")
    print()
    print("Press Ctrl+C to stop the server")
    print("=" * 60)
    print()

    # Clear any cached ontology_server modules from sys.modules
    # This ensures fresh imports when uvicorn loads the app
    modules_to_remove = [key for key in sys.modules.keys() if key.startswith('ontology_server')]
    for module in modules_to_remove:
        del sys.modules[module]

    # Invalidate import caches again right before uvicorn starts
    importlib.invalidate_caches()

    uvicorn.run(
        "ontology_server.core.api:app",
        host=host,
        port=port,
        reload=False,
        log_level="info"
    )


if __name__ == "__main__":
    main()
