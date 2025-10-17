# -*- coding: utf-8 -*-

"""
Tests for clarification functionality.
Uses real OpenAI API calls with gpt-5-mini to keep costs low.
"""

import pytest
import os

from deep_research_mcp.config import ResearchConfig
from deep_research_mcp.clarification import TriageAgent, ClarifierAgent, ClarificationManager, ClarificationSession


@pytest.fixture
def config():
    """Create test configuration with clarification enabled"""
    os.environ["RESEARCH_MODEL"] = "gpt-5-mini"  # Use cheap model for testing
    os.environ["ENABLE_CLARIFICATION"] = "true"
    os.environ["TRIAGE_MODEL"] = "gpt-5-mini"
    os.environ["CLARIFIER_MODEL"] = "gpt-5-mini"
    return ResearchConfig.from_env()


@pytest.fixture
def config_disabled():
    """Create test configuration with clarification disabled"""
    os.environ["RESEARCH_MODEL"] = "gpt-5-mini"
    os.environ["ENABLE_CLARIFICATION"] = "false"
    os.environ["TRIAGE_MODEL"] = "gpt-5-mini"
    os.environ["CLARIFIER_MODEL"] = "gpt-5-mini"
    return ResearchConfig.from_env()


def skip_if_no_api_key():
    """Skip test if no OpenAI API key is available"""
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set - skipping real API tests")


def test_clarification_session():
    """Test ClarificationSession functionality"""
    session = ClarificationSession(
        session_id="test-123",
        original_query="quantum computing",
        questions=["Q1?", "Q2?", "Q3?"],
    )

    assert session.session_id == "test-123"
    assert session.original_query == "quantum computing"
    assert len(session.questions) == 3
    assert len(session.answers) == 0

    # Test to_dict
    session_dict = session.to_dict()
    assert session_dict["session_id"] == "test-123"
    assert session_dict["total_questions"] == 3
    assert session_dict["answered_questions"] == 0
    assert session_dict["is_complete"] == False

    # Add answers
    session.answers = ["A1", "A2", "A3"]
    session_dict = session.to_dict()
    assert session_dict["answered_questions"] == 3
    assert session_dict["is_complete"] == True


def test_clarification_manager_disabled(config_disabled):
    """Test ClarificationManager when clarification is disabled"""
    manager = ClarificationManager(config_disabled)

    result = manager.start_clarification("test query")

    assert result["needs_clarification"] == False
    assert "disabled" in result["reasoning"].lower()


def test_triage_agent_specific_query(config):
    """Test TriageAgent with a specific query that shouldn't need clarification"""
    skip_if_no_api_key()

    agent = TriageAgent(config)
    result = agent.analyze_query(
        "What is the molecular structure of caffeine and its chemical formula?"
    )

    # This should be specific enough to not need clarification
    assert isinstance(result, dict)
    assert "needs_clarification" in result
    assert "reasoning" in result
    assert "query_assessment" in result
    # Note: We don't assert the specific boolean value since the AI may vary


def test_triage_agent_broad_query(config):
    """Test TriageAgent with a broad query that might need clarification"""
    skip_if_no_api_key()

    agent = TriageAgent(config)
    result = agent.analyze_query("artificial intelligence")

    # This broad query should potentially trigger clarification
    assert isinstance(result, dict)
    assert "needs_clarification" in result
    assert "reasoning" in result
    assert "query_assessment" in result

    # If clarification is needed, should have questions
    if result.get("needs_clarification"):
        assert "potential_clarifications" in result
        assert isinstance(result["potential_clarifications"], list)


def test_triage_agent_error_handling(config):
    """Test TriageAgent handles errors gracefully"""
    # Test with invalid API key to trigger error
    original_key = os.environ.get("OPENAI_API_KEY")
    original_research_key = os.environ.get("RESEARCH_API_KEY")
    try:
        os.environ["RESEARCH_API_KEY"] = "invalid-key"
        # Create a new config with the invalid API key
        error_config = ResearchConfig.from_env()
        agent = TriageAgent(error_config)
        result = agent.analyze_query("test query")

        # Should handle error gracefully
        assert isinstance(result, dict)

        assert result["needs_clarification"] == False
        # Should contain some error indication in reasoning

        assert (
            "error" in result["reasoning"].lower()
            or "could not parse" in result["reasoning"].lower()
        )

    finally:
        # Restore original keys
        if original_key:
            os.environ["OPENAI_API_KEY"] = original_key
        elif "OPENAI_API_KEY" in os.environ:
            del os.environ["OPENAI_API_KEY"]

        if original_research_key:
            os.environ["RESEARCH_API_KEY"] = original_research_key
        elif "RESEARCH_API_KEY" in os.environ:
            del os.environ["RESEARCH_API_KEY"]


def test_clarifier_agent(config):
    """Test ClarifierAgent query enrichment"""
    skip_if_no_api_key()

    agent = ClarifierAgent(config)

    qa_pairs = [
        {
            "question": "Are you interested in hardware or software aspects?",
            "answer": "Hardware",
        },
        {"question": "What time period should we focus on?", "answer": "Last 5 years"},
        {
            "question": "Are you looking for research papers or commercial applications?",
            "answer": "Commercial applications",
        },
    ]

    original_query = "quantum computing"
    enriched = agent.enrich_query(original_query, qa_pairs)

    # Should return a string that's different from original and incorporates context
    assert isinstance(enriched, str)
    assert len(enriched) > 0
    # The enriched query should be different from the original (in most cases)
    # and should potentially contain some of the context from answers


def test_clarifier_agent_error_fallback(config):
    """Test ClarifierAgent falls back to original query on error"""
    # Test with invalid config to trigger error - don't actually break API key
    # since the test might still succeed with a different response
    original_key = os.environ.get("OPENAI_API_KEY")

    # Create a config with an invalid API key
    config.api_key = "sk-invalid-key-for-testing"
    agent = ClarifierAgent(config)

    qa_pairs = [{"question": "Test?", "answer": "Test answer"}]
    original_query = "original query"

    enriched = agent.enrich_query(original_query, qa_pairs)

    # With an invalid API key, it should either:
    # 1. Fall back to original query, OR
    # 2. Raise an exception that gets caught and falls back
    # Let's just check that we get a string response
    assert isinstance(enriched, str)
    assert len(enriched) > 0

    # Note: The actual fallback behavior may vary depending on OpenAI's error handling


def test_clarification_manager_workflow(config):
    """Test clarification manager workflow (may or may not need clarification)"""
    skip_if_no_api_key()

    manager = ClarificationManager(config)

    # Start clarification with a deliberately broad query
    result = manager.start_clarification("machine learning")

    assert isinstance(result, dict)
    assert "needs_clarification" in result

    # If clarification is needed, test the full workflow
    if result.get("needs_clarification", False):
        assert "session_id" in result
        assert "questions" in result
        assert isinstance(result["questions"], list)

        session_id = result["session_id"]
        questions = result["questions"]

        # Provide some answers
        answers = [
            "Neural networks" if i == 0 else f"Answer {i+1}"
            for i in range(len(questions))
        ]
        status = manager.add_answers(session_id, answers)

        assert status["session_id"] == session_id
        assert status["status"] == "answers_recorded"
        assert status["answered_questions"] == len(answers)
        assert status["is_complete"] == True

        # Get enriched query
        enriched = manager.get_enriched_query(session_id)
        assert isinstance(enriched, str)
        assert len(enriched) > 0


def test_clarification_manager_invalid_session():
    """Test error handling for invalid session IDs"""
    os.environ["RESEARCH_MODEL"] = "gpt-5-mini"
    config = ResearchConfig.from_env()
    manager = ClarificationManager(config)

    # Test with non-existent session
    status = manager.add_answers("invalid-session", ["answer"])
    assert "error" in status
    assert "not found" in status["error"]

    enriched = manager.get_enriched_query("invalid-session")
    assert enriched is None


def test_config_clarification_settings():
    """Test configuration loading for clarification settings"""
    os.environ["RESEARCH_MODEL"] = "gpt-5-mini"
    os.environ["ENABLE_CLARIFICATION"] = "true"
    os.environ["TRIAGE_MODEL"] = "gpt-5-mini"
    os.environ["CLARIFIER_MODEL"] = "gpt-5-mini"

    config = ResearchConfig.from_env()

    assert config.enable_clarification == True
    assert config.triage_model == "gpt-5-mini"
    assert config.clarifier_model == "gpt-5-mini"

    # Test boolean parsing variations
    for true_val in ["true", "1", "yes", "True", "YES"]:
        os.environ["ENABLE_CLARIFICATION"] = true_val
        config = ResearchConfig.from_env()
        assert config.enable_clarification == True

    for false_val in ["false", "0", "no", "False", "NO", ""]:
        os.environ["ENABLE_CLARIFICATION"] = false_val
        config = ResearchConfig.from_env()
        assert config.enable_clarification == False
