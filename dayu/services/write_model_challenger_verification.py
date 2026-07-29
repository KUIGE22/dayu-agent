"""Verify an exported write-model Challenger proposal without executing it."""

from __future__ import annotations

import hmac
import json
from collections.abc import Mapping
from typing import Any

from dayu.services.write_model_challenger_proposal import (
    validate_write_model_challenger_proposal,
)

_VERIFICATION_SCHEMA_VERSION = (
    "write_model_challenger_proposal_verification_v1"
)


def _evidence_window(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    value = payload.get("evidence_window")
    if not isinstance(value, Mapping):
        raise ValueError("proposal evidence_window must be an object")
    return value


def verify_write_model_challenger_proposal(
    receipt: Mapping[str, Any],
    current: Mapping[str, Any],
) -> dict[str, Any]:
    """Compare a valid receipt with the proposal rebuilt from current history."""

    validate_write_model_challenger_proposal(receipt)
    validate_write_model_challenger_proposal(current)
    receipt_window = _evidence_window(receipt)
    current_window = _evidence_window(current)
    receipt_history = str(receipt_window["history_fingerprint"])
    current_history = str(current_window["history_fingerprint"])
    receipt_fingerprint = str(receipt["proposal_fingerprint"])
    current_fingerprint = str(current["proposal_fingerprint"])
    history_matches = hmac.compare_digest(
        receipt_history,
        current_history,
    )
    proposal_matches = hmac.compare_digest(
        receipt_fingerprint,
        current_fingerprint,
    )

    if not history_matches:
        status = "stale_history"
        reason_codes = ["history_fingerprint_changed"]
        action = "regenerate_proposal"
    elif not proposal_matches:
        status = "policy_changed"
        reason_codes = ["proposal_policy_or_content_changed"]
        action = "regenerate_proposal"
    else:
        status = "current"
        reason_codes = ["proposal_identity_current"]
        action = (
            "manual_preflight_required"
            if current.get("status") == "ready"
            else "none"
        )

    preview_available = (
        status == "current" and current.get("status") == "ready"
    )
    return {
        "schema_version": _VERIFICATION_SCHEMA_VERSION,
        "status": status,
        "is_current": status == "current",
        "reason_codes": reason_codes,
        "action": action,
        "identity": {
            "history_matches": history_matches,
            "proposal_matches": proposal_matches,
            "receipt_history_fingerprint": receipt_history,
            "current_history_fingerprint": current_history,
            "receipt_proposal_fingerprint": receipt_fingerprint,
            "current_proposal_fingerprint": current_fingerprint,
        },
        "proposal_status": str(current.get("status") or ""),
        "preflight_preview": {
            "available": preview_available,
            "challenger_cli_args": (
                list(current.get("challenger_cli_args") or [])
                if preview_available
                else []
            ),
        },
        "safety_requirements": list(
            current.get("safety_requirements") or []
        ),
    }


def format_write_model_challenger_verification_report(
    payload: Mapping[str, Any],
) -> tuple[str, ...]:
    """Format a compact, non-executing operator verification report."""

    identity = payload.get("identity")
    identity_view = identity if isinstance(identity, Mapping) else {}
    preview = payload.get("preflight_preview")
    preview_view = preview if isinstance(preview, Mapping) else {}
    args = preview_view.get("challenger_cli_args")
    safe_args = args if isinstance(args, list) else []
    lines = [
        "",
        "=" * 60,
        "Challenger 提案验证（只读）",
        "=" * 60,
        f"  验证状态   : {payload.get('status', 'invalid')}",
        f"  当前提案   : {payload.get('proposal_status', 'unknown')}",
        (
            "  历史一致   : "
            f"{'是' if identity_view.get('history_matches') is True else '否'}"
        ),
        (
            "  提案一致   : "
            f"{'是' if identity_view.get('proposal_matches') is True else '否'}"
        ),
    ]
    if preview_view.get("available") is True:
        lines.append(
            "  预检参数   : "
            + json.dumps(safe_args, ensure_ascii=False)
        )
        lines.append("  下一步     : 人工执行 Champion/Challenger 共同 preflight")
    else:
        lines.append("  预检参数   : 不可用")
    lines.extend(
        [
            "  安全边界   : 未调用模型，未修改配置，未晋升 Challenger",
            "=" * 60,
            "",
        ]
    )
    return tuple(lines)


__all__ = [
    "format_write_model_challenger_verification_report",
    "verify_write_model_challenger_proposal",
]
