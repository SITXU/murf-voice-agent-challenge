# backend/day4/run_agent.py
import sys
from pathlib import Path
import os

repo_root = Path(__file__).resolve().parents[2]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from livekit.agents import cli, WorkerOptions
from tutor_agent import entrypoint as day4_entrypoint

if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=day4_entrypoint,
            api_key=os.getenv("LIVEKIT_API_KEY"),
            api_secret=os.getenv("LIVEKIT_API_SECRET"),
        )
    )
