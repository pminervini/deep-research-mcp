"""
Prompt management system for deep-research-mcp.

This module provides a PromptManager class that handles loading and formatting
of YAML-based prompt templates with auto-discovery and package resource support.
"""

import logging
import os
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


class PromptManager:
    """
    Manages loading and formatting of YAML-based prompt templates.

    Uses convention-over-configuration approach with automatic discovery
    of prompt files, falling back to package resources when needed.
    """

    def __init__(self, custom_prompts_dir: str | None = None):
        """
        Initialize the PromptManager with auto-discovery.

        Args:
            custom_prompts_dir: Optional custom directory for prompts.
                               If None, uses auto-discovery.
        """
        self.prompts_cache: dict[str, dict[str, Any]] = {}
        self.prompts_dir = self._discover_prompts_directory(custom_prompts_dir)

    def _discover_prompts_directory(self, custom_dir: str | None = None) -> Path | None:
        """
        Discover the prompts directory using multiple strategies.

        Priority order:
        1. Custom directory (if provided)
        2. Environment variable override
        3. User customization directory
        4. Bundled prompts next to this module
        """
        search_paths = []

        # Add custom directory if provided
        if custom_dir:
            search_paths.append(Path(custom_dir))

        # Add environment override
        env_dir = os.environ.get("DEEP_RESEARCH_PROMPTS_DIR")
        if env_dir:
            search_paths.append(Path(env_dir))

        # Add user customization directory
        search_paths.append(Path.home() / ".deep_research" / "prompts")

        # Add package-local bundled prompts directory
        search_paths.append(Path(__file__).resolve().parent)

        # Find first existing directory
        for path in search_paths:
            if path.exists() and path.is_dir():
                logger.info(f"Using prompts directory: {path}")
                return path

        logger.warning(
            "No filesystem prompts directory found, will use package resources"
        )
        return None

    def _load_from_package_resources(self, category: str, name: str) -> dict[str, Any]:
        """
        Load prompt from package resources as fallback.
        """
        try:
            prompt_file = resources.files("deep_research_mcp.prompts").joinpath(
                category, f"{name}.yaml"
            )
            content = prompt_file.read_text(encoding="utf-8")
            return yaml.safe_load(content)
        except (FileNotFoundError, ModuleNotFoundError) as e:
            logger.error(
                f"Failed to load prompt {category}/{name} from package resources: {e}"
            )
            raise FileNotFoundError(
                f"Prompt file {category}/{name}.yaml not found in package resources"
            )

    def _load_from_filesystem(self, category: str, name: str) -> dict[str, Any]:
        """
        Load prompt from filesystem.
        """
        if not self.prompts_dir:
            raise FileNotFoundError("No prompts directory available")

        prompt_file = self.prompts_dir / category / f"{name}.yaml"

        if not prompt_file.exists():
            raise FileNotFoundError(f"Prompt file {prompt_file} not found")

        with open(prompt_file, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _load_prompt_data(self, category: str, name: str) -> dict[str, Any]:
        """
        Load prompt data from filesystem or package resources.
        """
        cache_key = f"{category}/{name}"

        if cache_key in self.prompts_cache:
            return self.prompts_cache[cache_key]

        try:
            # Try filesystem first
            prompt_data = self._load_from_filesystem(category, name)
        except FileNotFoundError:
            # Fallback to package resources
            prompt_data = self._load_from_package_resources(category, name)

        # Validate prompt structure
        required_fields = ["name", "description", "template", "variables"]
        for field in required_fields:
            if field not in prompt_data:
                raise ValueError(f"Prompt {cache_key} missing required field: {field}")

        self.prompts_cache[cache_key] = prompt_data
        return prompt_data

    def get_prompt(self, category: str, name: str, **kwargs) -> str:
        """
        Load and format a prompt template.

        Args:
            category: Prompt category (e.g., 'clarification', 'research')
            name: Prompt name (e.g., 'triage', 'enrichment')
            **kwargs: Variables to substitute in the template

        Returns:
            Formatted prompt string

        Raises:
            FileNotFoundError: If prompt file is not found
            ValueError: If required variables are missing
        """
        prompt_data = self._load_prompt_data(category, name)

        # Check required variables
        required_vars = prompt_data.get("variables", [])
        missing_vars = [var for var in required_vars if var not in kwargs]

        if missing_vars:
            raise ValueError(
                f"Missing required variables for prompt {category}/{name}: {missing_vars}"
            )

        # Format template
        try:
            return prompt_data["template"].format(**kwargs)
        except KeyError as e:
            raise ValueError(
                f"Template variable {e} not provided for prompt {category}/{name}"
            )

    def get_triage_prompt(self, user_query: str) -> str:
        """Get the triage analysis prompt."""
        return self.get_prompt("clarification", "triage", user_query=user_query)

    def get_enrichment_prompt(self, user_query: str, enriched_context: str) -> str:
        """Get the query enrichment prompt."""
        return self.get_prompt(
            "clarification",
            "enrichment",
            user_query=user_query,
            enriched_context=enriched_context,
        )

    def get_instruction_builder_prompt(self, query: str) -> str:
        """Get the instruction builder prompt."""
        return self.get_prompt("research", "instruction_builder", query=query)
