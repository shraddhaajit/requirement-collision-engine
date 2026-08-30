"""Audit Logging Module for CEWS."""

from datetime import datetime, timezone
from typing import Dict, Any
from cews.expense import Expense


def record_audit_log(expense: Expense, actor: str, action: str) -> Dict[str, Any]:
    """TRACE: REQ-09
    Record a workflow action in the expense audit log.
    Captures request_id, actor, action, and timestamp.
    """
    entry = {
        "request_id": expense.request_id,
        "actor": actor,
        "action": action,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    expense.audit_log.append(entry)
    return entry
