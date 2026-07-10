from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class Task:
    row_id: int
    name: str
    status: str  # "Completed", "In Progress", "Not Started"
    percent_complete: float
    start_date: Optional[date]
    end_date: Optional[date]
    baseline_start: Optional[date]
    baseline_end: Optional[date]
    duration: Optional[int]
    predecessors: list[str] = field(default_factory=list)
    owner: str = ""
    priority: str = ""
    total_float: Optional[float] = None
    is_critical: bool = False
    is_on_hold: bool = False
    is_not_applicable: bool = False
    level: int = 0  # hierarchy depth
    variance_days: Optional[int] = None  # negative = behind schedule
    rag_status: str = ""  # row-level RAG if present in source
    comments: list[str] = field(default_factory=list)

    @property
    def is_milestone(self) -> bool:
        return self.duration is not None and self.duration == 0

    @property
    def is_overdue(self) -> bool:
        if self.end_date and self.percent_complete < 100:
            return date.today() > self.end_date
        return False

    @property
    def days_overdue(self) -> int:
        if self.is_overdue and self.end_date:
            return (date.today() - self.end_date).days
        return 0

    @property
    def is_external(self) -> bool:
        owner_lower = self.owner.lower()
        external_markers = ["unisan", "titan", "otk", "customer"]
        internal_markers = ["zycus"]
        has_external = any(m in owner_lower for m in external_markers)
        has_internal = any(m in owner_lower for m in internal_markers)
        # if it has external but NOT internal, it's external
        # if it has both, it's shared (treat as external for risk purposes)
        return has_external


@dataclass
class ProjectSummary:
    name: str
    project_manager: str
    start_date: Optional[date]
    end_date: Optional[date]
    percent_complete: float
    total_tasks: int
    not_started: int
    in_progress: int
    completed: int
    on_hold: int
    current_stage: str
    report_date: Optional[date] = None


@dataclass
class Project:
    summary: ProjectSummary
    tasks: list[Task] = field(default_factory=list)

    @property
    def active_tasks(self) -> list[Task]:
        return [t for t in self.tasks if not t.is_on_hold and not t.is_not_applicable]

    @property
    def critical_tasks(self) -> list[Task]:
        return [t for t in self.active_tasks
                if t.is_critical or (t.total_float is not None and t.total_float < 1)]

    @property
    def overdue_tasks(self) -> list[Task]:
        return [t for t in self.active_tasks if t.is_overdue]

    @property
    def milestones(self) -> list[Task]:
        return [t for t in self.active_tasks if t.is_milestone]
