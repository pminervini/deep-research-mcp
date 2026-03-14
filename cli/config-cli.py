#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Configuration CLI for Deep Research MCP.

This script loads configuration exactly the same way the project does:
- Explicitly reads ~/.deep_research (TOML)
- Merges TOML values with environment variable overrides
- Constructs a ResearchConfig without mutating process environment state
- Optionally validates and prints the configuration

Usage:
  python cli/config-cli.py              # JSON output (secrets masked)
  python cli/config-cli.py --pretty     # Human-readable output (secrets masked)
  python cli/config-cli.py --show-secrets  # Print full secrets
"""

import argparse
import json
from dataclasses import asdict
from typing import Any

from deep_research_mcp.config import ResearchConfig

import logging

# Set up logging to show debug messages
logging.basicConfig(level=logging.DEBUG)


def _mask_secret(value: str | None, keep: int = 4) -> str:
    if not value:
        return ""
    if len(value) <= keep:
        return "*" * len(value)
    return ("*" * (len(value) - keep)) + value[-keep:]


def _masked_config_dict(cfg: ResearchConfig, show_secrets: bool) -> dict[str, Any]:
    data = asdict(cfg)
    if not show_secrets:
        # Mask sensitive fields
        if "api_key" in data:
            data["api_key"] = _mask_secret(data["api_key"])
        if "clarification_api_key" in data:
            data["clarification_api_key"] = _mask_secret(data["clarification_api_key"])
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Deep Research MCP Config Viewer")
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print configuration instead of JSON",
    )
    parser.add_argument(
        "--show-secrets",
        action="store_true",
        help="Show full secrets (API keys). By default they are masked.",
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Do not run config.validate()",
    )

    args = parser.parse_args()

    cfg = ResearchConfig.load()
    if not args.no_validate:
        # Validation matches project behavior used before running components
        cfg.validate()

    data = _masked_config_dict(cfg, show_secrets=args.show_secrets)

    if args.pretty:
        # Human-readable output
        for k in sorted(data.keys()):
            print(f"{k}: {data[k]}")
    else:
        # JSON for machine readability
        print(json.dumps(data, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
