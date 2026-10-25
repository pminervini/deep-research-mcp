# -*- coding: utf-8 -*-

"""Gnosis result/config contracts and opt-in tests against a real deployed server."""

import json
import logging
import os
from pathlib import Path

import pytest

from deep_research_mcp.backends.gnosis_backend import GnosisResearchBackend
from deep_research_mcp.config import ResearchConfig
from deep_research_mcp.errors import ResearchError

# These fixtures exercise serialization contracts, not a simulated HTTP service.
# No model or search response is substituted for a real provider call.
# pylint: disable=protected-access


def _backend(tmp_path: Path) -> GnosisResearchBackend:
    return GnosisResearchBackend(
        ResearchConfig(provider="gnosis", gnosis_output_dir=str(tmp_path)),
        logging.getLogger(__name__),
    )


def _events(conversation_id: str) -> list[dict]:
    return [
        {"event": "search_final_result", "run_id": "run", "seq": 3, "payload": {}},
        {
            "event": "run_started",
            "run_id": "run",
            "seq": 1,
            "payload": {"conversation_id": conversation_id},
        },
    ]


def test_gnosis_recovers_full_prediction_without_preview_truncation(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "logs" / "result_internal-id"
    directory.mkdir(parents=True)
    report = "Serialization fixture. " * 100 + "[Source](https://example.org/source)"
    (directory / "final_result.json").write_text(
        json.dumps(
            {
                "prediction": report,
                "termination": "answer",
                "completion_time": 1.5,
                "retrieved_evidence_ids": [{"url": "https://example.org/not-cited"}],
            }
        ),
        encoding="utf-8",
    )
    result = _backend(tmp_path)._read_result("run", _events("internal-id"))
    assert result is not None
    assert result.status == "completed"
    assert result.final_report == report
    assert result.execution_time == 1.5
    assert [(item.title, item.url) for item in result.citations] == [
        ("Source", "https://example.org/source")
    ]


@pytest.mark.parametrize(
    "termination",
    [
        "time_limit",
        "timeout_guess",
        "actions_explored_limit",
        "fail_limit",
        "action_pool_depleted",
    ],
)
def test_gnosis_does_not_claim_success_for_unconfirmed_answers(
    tmp_path: Path, termination: str
) -> None:
    result = _backend(tmp_path)._extract_result(
        "run", {"prediction": "Unconfirmed fixture", "termination": termination}
    )
    assert result.status == "failed"
    assert result.final_report == ""
    assert termination in (result.message or "")


@pytest.mark.parametrize("prediction", [None, "", "  ", {"not": "an answer"}])
def test_gnosis_rejects_empty_or_malformed_confirmed_answer(
    tmp_path: Path, prediction: object
) -> None:
    result = _backend(tmp_path)._extract_result(
        "run", {"prediction": prediction, "termination": "answer"}
    )
    assert result.status == "failed"


def test_gnosis_collected_answer_on_timeout_is_explicit(tmp_path: Path) -> None:
    result = _backend(tmp_path)._extract_result(
        "run", {"prediction": "Selected answer", "termination": "timeout_answer"}
    )
    assert result.status == "completed"
    assert result.message == "Gnosis termination: timeout_answer"


def test_gnosis_missing_result_is_not_success(tmp_path: Path) -> None:
    assert _backend(tmp_path)._read_result("run", _events("internal-id")) is None
    assert _backend(tmp_path)._read_result("run", []) is None


def test_gnosis_partial_result_file_can_be_retried(tmp_path: Path) -> None:
    directory = tmp_path / "logs" / "result_internal-id"
    directory.mkdir(parents=True)
    (directory / "final_result.json").write_text('{"prediction":', encoding="utf-8")
    assert _backend(tmp_path)._read_result("run", _events("internal-id")) is None


def test_gnosis_rejects_result_path_traversal(tmp_path: Path) -> None:
    with pytest.raises(ResearchError, match="invalid internal conversation"):
        _backend(tmp_path)._read_result("run", _events("../../outside"))


def test_gnosis_rejects_result_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "logs").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ResearchError, match="escapes"):
        _backend(root)._read_result("run", _events("internal-id"))


@pytest.mark.asyncio
async def test_gnosis_requires_options_before_starting_a_run(tmp_path: Path) -> None:
    result = await _backend(tmp_path).research("Do not submit this configuration test")
    assert result.status == "failed"
    assert result.task_id is None
    assert "gnosis_config_path" in (result.message or "")


@pytest.mark.parametrize(
    "options",
    [
        [],
        {"llm": {}},
        {"query": "wrong"},
        {"run_id": "reused"},
        {"conversation_id": "wrong"},
    ],
)
def test_gnosis_invalid_options_fail_before_network(
    tmp_path: Path, options: object
) -> None:
    path = tmp_path / "options.json"
    path.write_text(json.dumps(options), encoding="utf-8")
    backend = _backend(tmp_path)
    backend.config.gnosis_config_path = str(path)
    with pytest.raises(ResearchError):
        backend._load_options()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_gnosis_real_service_unknown_run() -> None:
    base_url = os.environ.get("GNOSIS_TEST_BASE_URL")
    if not base_url:
        pytest.skip("Set GNOSIS_TEST_BASE_URL to test a deployed Gnosis service")
    backend = GnosisResearchBackend(
        ResearchConfig(provider="gnosis", base_url=base_url),
        logging.getLogger(__name__),
    )
    status = await backend.get_task_status("deep-research-mcp-unknown-test-id")
    assert status.status == "unknown"
    assert await backend.get_task_result(status.task_id) is None


@pytest.mark.api
@pytest.mark.integration
@pytest.mark.asyncio
async def test_gnosis_live_search_and_completed_result_recovery() -> None:
    options = os.environ.get("GNOSIS_TEST_CONFIG_PATH")
    output_dir = os.environ.get("GNOSIS_TEST_OUTPUT_DIR")
    if not options or not output_dir:
        pytest.skip(
            "Set GNOSIS_TEST_CONFIG_PATH and GNOSIS_TEST_OUTPUT_DIR for live research"
        )
    config = ResearchConfig(
        provider="gnosis",
        base_url=os.environ.get("GNOSIS_TEST_BASE_URL", "http://127.0.0.1:8089"),
        gnosis_config_path=options,
        gnosis_output_dir=output_dir,
        timeout=240,
        poll_interval=1,
        cancel_on_timeout=True,
    )
    backend = GnosisResearchBackend(config, logging.getLogger(__name__))
    started: list[str] = []

    async def on_started(task_id: str) -> None:
        started.append(task_id)

    result = await backend.research(
        "What is the full release date (day, month, year) of Python 3.0? "
        "Search the web and fetch the python.org source to verify it.",
        system_prompt="Use the search and fetch tools. Answer briefly.",
        include_code_interpreter=False,
        on_task_started=on_started,
    )
    assert result.status == "completed", result.message
    assert result.final_report.strip()
    assert result.task_id is not None
    assert started == [result.task_id]
    # Recovery uses a new client and does not need the request/credential file.
    config.gnosis_config_path = None
    recovered_backend = GnosisResearchBackend(config, logging.getLogger(__name__))
    assert (
        await recovered_backend.get_task_status(result.task_id)
    ).status == "completed"
    recovered = await recovered_backend.get_task_result(result.task_id)
    assert recovered is not None
    assert recovered.final_report == result.final_report
