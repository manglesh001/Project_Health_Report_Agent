from datetime import date
from pathlib import Path

from src.parser.data_model import Project
from src.reporting.narrative import generate_narrative
from src.scoring.rag_engine import RAGResult


def generate_weekly_report(project: Project, rag: RAGResult, use_llm: bool = True) -> str:
    """generate a full weekly report as markdown"""
    today = date.today()
    report_date = project.summary.report_date or today

    lines = []
    lines.append(f"# Weekly Project Health Report")
    lines.append(f"**Report Date:** {report_date.strftime('%B %d, %Y')}")
    lines.append(f"**Project:** {project.summary.name}")
    lines.append(f"**PM:** {project.summary.project_manager}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # RAG banner
    emoji = {"Red": "🔴", "Amber": "🟡", "Green": "🟢"}.get(rag.overall_status, "⚪")
    lines.append(f"## Overall Status: {emoji} {rag.overall_status.upper()}")
    lines.append("")

    # quick stats
    lines.append("### Snapshot")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Completion | {project.summary.percent_complete}% |")
    lines.append(f"| Current Stage | {project.summary.current_stage} |")
    lines.append(f"| Tasks Completed | {project.summary.completed}/{project.summary.total_tasks} |")
    lines.append(f"| Tasks In Progress | {project.summary.in_progress} |")
    lines.append(f"| Tasks Not Started | {project.summary.not_started} |")
    lines.append(f"| Timeline | {project.summary.start_date} → {project.summary.end_date} |")
    lines.append("")

    # dimension breakdown
    lines.append("### Health Dimensions")
    lines.append("")
    lines.append("| Dimension | Status | Detail |")
    lines.append("|-----------|--------|--------|")
    for dim in rag.dimensions:
        d_emoji = {"Red": "🔴", "Amber": "🟡", "Green": "🟢"}.get(dim.status, "⚪")
        lines.append(f"| {dim.name} | {d_emoji} {dim.status} | {dim.reason} |")
    lines.append("")

    # narrative
    lines.append("### Analysis")
    lines.append("")
    if use_llm:
        narrative = generate_narrative(project, rag)
    else:
        from src.reporting.narrative import _fallback_narrative
        narrative = _fallback_narrative(project, rag)
    lines.append(narrative)
    lines.append("")

    # detailed signals
    lines.append("---")
    lines.append("### Detailed Signals")
    lines.append("")

    lines.append("**Schedule:**")
    lines.append(f"- Critical tasks overdue: {rag.schedule.critical_tasks_overdue}/{rag.schedule.critical_tasks_total}")
    lines.append(f"- Average slippage: {rag.schedule.avg_slippage_days} days")
    lines.append(f"- Worst task: {rag.schedule.worst_task[:80]}")
    lines.append("")

    lines.append("**Milestones:**")
    lines.append(f"- Upcoming (30 days): {rag.milestones.milestones_upcoming}")
    lines.append(f"- At risk: {rag.milestones.milestones_at_risk}")
    lines.append(f"- Missed: {rag.milestones.milestones_missed}")
    if rag.milestones.at_risk_names:
        for m in rag.milestones.at_risk_names:
            lines.append(f"  - ⚠️ {m}")
    lines.append("")

    lines.append("**Blockers:**")
    lines.append(f"- Blocked tasks: {rag.blockers.blocked_count}")
    lines.append(f"- Cascade chains: {rag.blockers.cascade_chains}")
    if rag.blockers.blocked_tasks:
        lines.append("- Top blocked:")
        for b in rag.blockers.blocked_tasks[:5]:
            lines.append(f"  - {b}")
    lines.append("")

    lines.append("**External Dependencies:**")
    lines.append(f"- Overdue: {rag.dependencies.external_overdue_count}")
    lines.append(f"- Max days overdue: {rag.dependencies.max_external_overdue_days}")
    if rag.dependencies.external_overdue_tasks:
        lines.append("- Tasks:")
        for e in rag.dependencies.external_overdue_tasks[:5]:
            lines.append(f"  - {e}")
    lines.append("")

    return "\n".join(lines)


def save_weekly_report(report: str, project_name: str, output_dir: str = "data/output") -> str:
    """save report to file, return the path"""
    today = date.today()
    filename = f"{project_name.replace(' ', '_')}_{today.strftime('%Y%m%d')}_weekly.md"
    path = Path(output_dir) / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")
    return str(path)
