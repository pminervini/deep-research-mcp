# -*- coding: utf-8 -*-

"""Shared pytest fixtures for test model/cost controls."""

import os

import pytest

MODEL_ENV_VARS = (
    "RESEARCH_MODEL",
    "TRIAGE_MODEL",
    "CLARIFIER_MODEL",
    "INSTRUCTION_BUILDER_MODEL",
    "CLARIFICATION_TRIAGE_MODEL",
    "CLARIFICATION_CLARIFIER_MODEL",
    "CLARIFICATION_INSTRUCTION_BUILDER_MODEL",
)


@pytest.fixture(autouse=True)
def force_gpt5_mini_for_tests():
    """Ensure tests default to the cheapest allowed model."""
    original_env = {env_var: os.environ.get(env_var) for env_var in MODEL_ENV_VARS}

    for env_var in MODEL_ENV_VARS:
        os.environ[env_var] = "gpt-5-mini"

    try:
        yield
    finally:
        for env_var, original_value in original_env.items():
            if original_value is None:
                os.environ.pop(env_var, None)
            else:
                os.environ[env_var] = original_value
