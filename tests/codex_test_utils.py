# -*- coding: utf-8 -*-

"""Shared unsigned JWTs for local Codex HTTP fixtures."""

import jwt


def _jwt(*, expires_at: float, account_id: str = "account-123") -> str:
    return jwt.encode(
        {
            "exp": expires_at,
            "https://api.openai.com/auth": {"chatgpt_account_id": account_id},
        },
        key="",
        algorithm="none",
    )
