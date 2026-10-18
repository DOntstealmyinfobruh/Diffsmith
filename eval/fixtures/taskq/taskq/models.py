from dataclasses import dataclass, field
from datetime import date

PRIORITIES = ("low", "normal", "high")


@dataclass
class Task:
    id: int
    title: str
    priority: str = "normal"
    done: bool = False
    due: date | None = None
    tags: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.title.strip():
            raise ValueError("title must not be empty")
        if self.priority not in PRIORITIES:
            raise ValueError(f"priority must be one of {PRIORITIES}")
