"""Expense Data Model for CEWS."""

from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class Expense:
    """TRACE: REQ-01"""
    request_id: str
    employee_id: str
    department: str
    expense_type: str
    amount: float
    budget: float
    is_emergency: bool = False
    status: str = "SUBMITTED"
    audit_log: List[Dict[str, Any]] = field(default_factory=list)
