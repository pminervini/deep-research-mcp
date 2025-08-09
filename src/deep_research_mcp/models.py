# -*- coding: utf-8 -*-

"""
Model definitions and management for Deep Research MCP.
"""

from typing import Dict, List, Any


# Centralized model definitions
AVAILABLE_MODELS = [
    {
        "name": "gpt-4o",
        "description": "General-purpose frontier model with multimodal capabilities, suitable for a wide variety of tasks including text, vision, and audio processing",
        "cost": "$2.50 per 1M input tokens, $10.00 per 1M output tokens"
    },
    {
        "name": "gpt-5",
        "description": "OpenAI's flagship reasoning model with 272K input context and 128K output capacity. State-of-the-art performance in coding, math, and agentic tasks with advanced reasoning capabilities",
        "cost": "$1.25 per 1M input tokens, $10.00 per 1M output tokens"
    },
    {
        "name": "gpt-5-mini",
        "description": "Balanced 400B parameter model retaining 92% of full GPT-5 performance with 60% reduced computational requirements. 272K input context, supports reasoning and custom tools",
        "cost": "$0.25 per 1M input tokens, $2.00 per 1M output tokens"
    },
    {
        "name": "gpt-5-nano",
        "description": "Edge-optimized 50B parameter model for real-time applications with sub-100ms response times. Maintains 85% benchmark accuracy with 272K input context",
        "cost": "$0.05 per 1M input tokens, $0.40 per 1M output tokens"
    },
    {
        "name": "o3-deep-research-2025-06-26",
        "description": "Flagship deep research model optimized for highest quality synthesis and in-depth analysis. 200K token context, 100K max output. Ideal for complex research requiring extensive reasoning",
        "cost": "$10.00 per 1M input tokens ($2.50 cached), $40.00 per 1M output tokens"
    },
    {
        "name": "o4-mini-deep-research-2025-06-26",
        "description": "Lightweight deep research model optimized for speed and cost-efficiency while maintaining high intelligence. Perfect for latency-sensitive research applications",
        "cost": "$2.00 per 1M input tokens ($0.50 cached), $8.00 per 1M output tokens"
    },
]


def get_valid_model_names() -> List[str]:
    """Get list of valid model names for configuration validation."""
    return [model["name"] for model in AVAILABLE_MODELS]


def get_model_info(model_name: str) -> Dict[str, str]:
    """Get information about a specific model."""
    for model in AVAILABLE_MODELS:
        if model["name"] == model_name:
            return model
    raise ValueError(f"Model '{model_name}' not found")


def format_models_list() -> str:
    """Format all models for display in the MCP server list_models function."""
    result = "## Available Deep Research Models\n\n"
    for model in AVAILABLE_MODELS:
        result += f"### {model['name']}\n"
        result += f"- Description: {model['description']}\n"
        result += f"- Cost: {model['cost']}\n\n"
    return result


def is_valid_model(model_name: str) -> bool:
    """Check if a model name is valid."""
    return model_name in get_valid_model_names()