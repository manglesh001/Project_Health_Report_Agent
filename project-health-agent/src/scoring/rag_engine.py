from dataclasses import dataclass

import yaml

from src.parser.data_model import Project
from src.scoring.signals import (
    BlockerSignal,
    DependencySignal,
    MilestoneSignal,
    ScheduleSignal,
    extract_blocker_signal,
    extract_dependency_signal,
    extract_milestone_signal,
    extract_schedule_signal,
)


@dataclass
class DimensionScore:
    name: str
    status: str  # "Green", "Amber", "Red"
    reason: str
    weight: float


@dataclass
class RAGResult:
    overall_status: str  # "Green", "Amber", "Red"
    dimensions: list[DimensionScore]
    schedule: ScheduleSignal
    milestones: MilestoneSignal
    blockers: BlockerSignal
    dependencies: DependencySignal

    @property
    def summary_reasons(self) -> list[str]:
        return [d.reason for d in self.dimensions if d.status != "Green"]


def load_thresholds(config_path: str = "config/settings.yaml") -> dict:
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    return config["scoring"]["thresholds"]


def score_schedule(signal: ScheduleSignal, thresholds: dict) -> DimensionScore:
    t = thresholds["schedule_slippage"]

    if signal.avg_slippage_days > t["amber_avg_max"] or signal.max_slippage_days > t["amber_single_max"]:
        status = "Red"
        reason = f"Critical path avg {signal.avg_slippage_days}d behind (max: {signal.max_slippage_days}d on '{signal.worst_task[:50]}')"
    elif signal.avg_slippage_days > t["green_avg_max"] or signal.max_slippage_days > t["green_single_max"]:
        status = "Amber"
        reason = f"Schedule slipping — avg {signal.avg_slippage_days}d behind on critical tasks"
    else:
        status = "Green"
        reason = "Schedule on track"

    return DimensionScore(name="Schedule Slippage", status=status, reason=reason, weight=0.35)


def score_milestones(signal: MilestoneSignal, thresholds: dict) -> DimensionScore:
    t = thresholds["milestone_health"]

    if signal.milestones_missed > 0 or signal.milestones_at_risk > t["amber_at_risk_max"]:
        status = "Red"
        missed_str = f"{signal.milestones_missed} missed, " if signal.milestones_missed else ""
        reason = f"{missed_str}{signal.milestones_at_risk} at risk: {', '.join(signal.at_risk_names[:3])}"
    elif signal.milestones_at_risk > t["green_at_risk_max"]:
        status = "Amber"
        reason = f"1 milestone at risk: {signal.at_risk_names[0] if signal.at_risk_names else 'unknown'}"
    else:
        status = "Green"
        reason = f"All {signal.milestones_upcoming} upcoming milestones on track"

    return DimensionScore(name="Milestone Health", status=status, reason=reason, weight=0.25)


def score_blockers(signal: BlockerSignal, thresholds: dict) -> DimensionScore:
    t = thresholds["blocker_density"]

    if signal.blocked_count > t["amber_blocked_max"] or signal.cascade_chains > t["amber_cascade_max"]:
        status = "Red"
        reason = f"{signal.blocked_count} tasks blocked, {signal.cascade_chains} cascade chain(s)"
    elif signal.blocked_count > t["green_blocked_max"] or signal.cascade_chains > t["green_cascade_max"]:
        status = "Amber"
        reason = f"{signal.blocked_count} tasks blocked"
    else:
        status = "Green"
        reason = "No significant blockers"

    return DimensionScore(name="Blocker Density", status=status, reason=reason, weight=0.25)


def score_dependencies(signal: DependencySignal, thresholds: dict) -> DimensionScore:
    t = thresholds["dependency_risk"]

    if signal.external_overdue_count > t["amber_overdue_max"] or signal.max_external_overdue_days > t["amber_days_max"]:
        status = "Red"
        reason = f"{signal.external_overdue_count} external tasks overdue (max {signal.max_external_overdue_days}d)"
    elif signal.external_overdue_count > t["green_overdue_max"]:
        status = "Amber"
        reason = f"{signal.external_overdue_count} external task(s) overdue"
    else:
        status = "Green"
        reason = "No external dependency delays"

    return DimensionScore(name="Dependency Risk", status=status, reason=reason, weight=0.15)


def compute_rag(project: Project, config_path: str = "config/settings.yaml") -> RAGResult:
    """main scoring function — takes a project, returns RAG status with reasoning"""
    thresholds = load_thresholds(config_path)

    # extract signals
    schedule = extract_schedule_signal(project)
    milestones = extract_milestone_signal(project)
    blockers = extract_blocker_signal(project)
    dependencies = extract_dependency_signal(project)

    # score each dimension
    dim_schedule = score_schedule(schedule, thresholds)
    dim_milestones = score_milestones(milestones, thresholds)
    dim_blockers = score_blockers(blockers, thresholds)
    dim_dependencies = score_dependencies(dependencies, thresholds)

    dimensions = [dim_schedule, dim_milestones, dim_blockers, dim_dependencies]

    # determine overall: any Red = Red, any Amber = Amber, else Green
    if any(d.status == "Red" for d in dimensions):
        overall = "Red"
    elif any(d.status == "Amber" for d in dimensions):
        overall = "Amber"
    else:
        overall = "Green"

    return RAGResult(
        overall_status=overall,
        dimensions=dimensions,
        schedule=schedule,
        milestones=milestones,
        blockers=blockers,
        dependencies=dependencies,
    )
