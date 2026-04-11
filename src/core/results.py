"""
Shared result and progress types used across service and GUI layers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

T = TypeVar("T")


@dataclass
class ServiceResult(Generic[T]):
    """
    Structured return value for every service method.
    Services never print or raise — they return one of these.
    """
    success: bool
    data: T | None = None
    message: str = ""
    error: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass
class ProgressEvent:
    """
    Emitted by long-running operations (backup, restore, export, mirror setup).
    type values: "started" | "progress" | "completed" | "failed" | "cancelled"
    """
    type: str
    message: str = ""
    percent: int | None = None   # 0-100; None = indeterminate
    data: Any = None
