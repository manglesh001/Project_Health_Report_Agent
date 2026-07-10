from dataclasses import dataclass
from datetime import date, timedelta

from src.parser.data_model import Project, Task


@dataclass
class ScheduleSignal:
    avg_slippage_days: float
    max_slippage_days: float
    critical_tasks_overdue: int
    critical_tasks_total: int
    worst_task: str = ""


@dataclass
class MilestoneSignal:
    milestones_at_risk: int
    milestones_missed: int
    milestones_upcoming: int
    at_risk_names: list[str] = None

    def __post_init__(self):
        if self.at_risk_names is None:
            self.at_risk_names = []


@dataclass
class BlockerSignal:
    blocked_count: int
    cascade_chains: int
    blocked_tasks: list[str] = None

    def __post_init__(self):
        if self.blocked_tasks is None:
            self.blocked_tasks = []


@dataclass
class DependencySignal:
    external_overdue_count: int
    max_external_overdue_days: int
    external_overdue_tasks: list[str] = None

    def __post_init__(self):
        if self.external_overdue_tasks is None:
            self.external_overdue_tasks = []


def extract_schedule_signal(project: Project) -> ScheduleSignal:
    """measure how far behind critical path tasks are"""
    today = date.today()
    critical = project.critical_tasks
    active = project.active_tasks

    # if no tasks explicitly marked critical, use tasks with low float
    # or fall back to all in-progress tasks
    if not critical:
        critical = [t for t in active if t.total_float is not None and t.total_float < 5]
    if not critical:
        critical = [t for t in active if t.status == "In Progress"]

    overdue_days = []
    worst_task = ""
    max_slip = 0

    for task in critical:
        if task.percent_complete >= 100:
            continue

        slip = 0
        # use baseline variance if available
        if task.variance_days is not None and task.variance_days < 0:
            slip = abs(task.variance_days)
        # otherwise compute from dates
        elif task.end_date and today > task.end_date:
            slip = (today - task.end_date).days
        elif task.baseline_end and task.end_date and isinstance(task.baseline_end, date):
            try:
                diff = (task.end_date - task.baseline_end).days
                if diff > 0:
                    slip = diff
            except TypeError:
                pass

        if slip > 0:
            overdue_days.append(slip)
            if slip > max_slip:
                max_slip = slip
                worst_task = task.name

    avg_slip = sum(overdue_days) / len(overdue_days) if overdue_days else 0
    return ScheduleSignal(
        avg_slippage_days=round(avg_slip, 1),
        max_slippage_days=max_slip,
        critical_tasks_overdue=len(overdue_days),
        critical_tasks_total=len(critical),
        worst_task=worst_task,
    )


def extract_milestone_signal(project: Project) -> MilestoneSignal:
    """check if upcoming milestones are achievable"""
    today = date.today()
    lookahead = today + timedelta(days=30)

    milestones = project.milestones
    # also catch milestone-like tasks by name
    milestone_keywords = ["go-live", "go /no-go", "sign off", "completion",
                          "check point", "uat completion", "kpi sign"]
    for task in project.active_tasks:
        if task not in milestones:
            name_lower = task.name.lower()
            if any(kw in name_lower for kw in milestone_keywords):
                milestones.append(task)

    upcoming = [m for m in milestones
                if m.end_date and today <= m.end_date <= lookahead
                and m.percent_complete < 100]

    # also catch already-missed ones
    missed = [m for m in milestones
              if m.end_date and m.end_date < today and m.percent_complete < 100]

    at_risk = []
    # build a quick predecessor lookup
    task_by_row = {t.row_id: t for t in project.active_tasks}

    for milestone in upcoming:
        # check if predecessors are on track
        for pred_ref in milestone.predecessors:
            # extract row number from predecessor string
            row_match = _extract_row_number(pred_ref)
            if row_match and row_match in task_by_row:
                pred_task = task_by_row[row_match]
                if pred_task.is_overdue or (pred_task.status == "Not Started" and pred_task.start_date and pred_task.start_date < today):
                    at_risk.append(milestone.name)
                    break

    return MilestoneSignal(
        milestones_at_risk=len(at_risk),
        milestones_missed=len(missed),
        milestones_upcoming=len(upcoming),
        at_risk_names=at_risk[:5],
    )


def extract_blocker_signal(project: Project) -> BlockerSignal:
    """find tasks that are stuck and blocking downstream work"""
    today = date.today()
    active = project.active_tasks

    # find blocked tasks: not started or barely started, past their start date
    blocked = []
    for task in active:
        if task.is_milestone:
            continue
        if task.percent_complete >= 10:
            continue
        if task.status in ["Completed"]:
            continue
        if task.start_date and task.start_date < today:
            # check if this task has downstream dependents
            has_dependents = any(
                str(task.row_id) in " ".join(other.predecessors)
                for other in active if other.row_id != task.row_id
            )
            if has_dependents:
                blocked.append(task.name)

    # detect cascade chains
    # a cascade is: task A is blocked -> task B depends on A and is also stuck -> task C depends on B...
    chains = _find_cascade_chains(active, today)

    return BlockerSignal(
        blocked_count=len(blocked),
        cascade_chains=chains,
        blocked_tasks=blocked[:10],
    )


def extract_dependency_signal(project: Project) -> DependencySignal:
    """find external/customer tasks that are overdue"""
    today = date.today()
    external_overdue = []
    max_days = 0

    for task in project.active_tasks:
        if not task.is_external:
            continue
        if task.percent_complete >= 100:
            continue
        if task.end_date and today > task.end_date:
            days = (today - task.end_date).days
            external_overdue.append(task.name)
            max_days = max(max_days, days)
        elif task.start_date and today > task.start_date and task.percent_complete < 10:
            # started late and barely progressed
            days = (today - task.start_date).days
            if days > 5:
                external_overdue.append(task.name)
                max_days = max(max_days, days)

    return DependencySignal(
        external_overdue_count=len(external_overdue),
        max_external_overdue_days=max_days,
        external_overdue_tasks=external_overdue[:10],
    )


def _extract_row_number(pred_string: str) -> int | None:
    """pull the row number from a predecessor reference like '264FS +5d'"""
    import re
    match = re.match(r"(\d+)", pred_string.strip())
    if match:
        return int(match.group(1))
    return None


def _find_cascade_chains(tasks: list[Task], today: date) -> int:
    """count chains of 3+ sequentially blocked tasks"""
    task_by_row = {t.row_id: t for t in tasks}
    chains = 0
    visited = set()

    for task in tasks:
        if task.row_id in visited:
            continue
        if task.percent_complete >= 10 or task.status == "Completed":
            continue
        if not (task.start_date and task.start_date < today):
            continue

        # walk the dependency chain forward
        chain_length = 1
        current = task
        visited.add(current.row_id)

        # find what depends on this task
        dependents = [t for t in tasks
                      if any(str(current.row_id) in p for p in t.predecessors)
                      and t.row_id not in visited]

        while dependents:
            # take the first dependent that's also stuck
            next_stuck = None
            for dep in dependents:
                if dep.percent_complete < 10 and dep.status != "Completed":
                    next_stuck = dep
                    break

            if next_stuck is None:
                break

            chain_length += 1
            visited.add(next_stuck.row_id)
            current = next_stuck
            dependents = [t for t in tasks
                          if any(str(current.row_id) in p for p in t.predecessors)
                          and t.row_id not in visited]

        if chain_length >= 3:
            chains += 1

    return chains
