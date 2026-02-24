"""Data models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Event:
    event_id: str
    title: str
    due_text: str
    url: str
    course_name: str = "Sin materia"
    description: str = ""
    assignment_url: str = ""
    submitted: Optional[bool] = None
    submission_status: str = ""
