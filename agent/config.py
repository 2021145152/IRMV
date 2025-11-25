from pydantic import BaseModel, Field
from typing import Any, Optional
from pathlib import Path

from langchain_core.runnables import RunnableConfig


class Configuration(BaseModel):
    """Configuration class for LangGraph agents."""

    # All agents use gpt-4o (Note: gpt-5-nano doesn't exist yet, using gpt-4o)
    task_analyzer_model: str = "gpt-4o"
    scene_explorer_model: str = "gpt-4o"
    task_planner_model: str = "gpt-4o"
    robot_executor_model: str = "gpt-4o"

    # Temperature settings
    temperature: float = 0.0

    @classmethod
    def from_runnable_config(
        cls, config: Optional[RunnableConfig] = None
    ) -> "Configuration":
        """Create Configuration from RunnableConfig."""
        if config is None:
            return cls()

        configurable = config.get("configurable", {})
        return cls(**configurable)