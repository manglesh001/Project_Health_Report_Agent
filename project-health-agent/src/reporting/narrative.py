import os

from src.parser.data_model import Project
from src.scoring.rag_engine import RAGResult


def generate_narrative(project: Project, rag: RAGResult) -> str:
    """use Gemini to write a plain-English explanation of the project status"""

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return _fallback_narrative(project, rag)

    try:
        from google import genai
        client = genai.Client(api_key=api_key)

        prompt = _build_prompt(project, rag)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        return response.text
    except Exception as e:
        print(f"  Warning: Gemini API failed ({e}), using fallback narrative")
        return _fallback_narrative(project, rag)


def _build_prompt(project: Project, rag: RAGResult) -> str:
    dims_text = "\n".join(
        f"  - {d.name}: {d.status} — {d.reason}" for d in rag.dimensions
    )

    blockers_text = "\n".join(f"  - {b}" for b in rag.blockers.blocked_tasks[:5])
    ext_text = "\n".join(f"  - {e}" for e in rag.dependencies.external_overdue_tasks[:5])

    return f"""You are a project health reporting assistant. Write a concise weekly status for a VP audience.

Project: {project.summary.name}
PM: {project.summary.project_manager}
Overall completion: {project.summary.percent_complete}%
Current stage: {project.summary.current_stage}
RAG Status: {rag.overall_status}

Dimension Scores:
{dims_text}

Key data points:
- Critical path: {rag.schedule.critical_tasks_overdue}/{rag.schedule.critical_tasks_total} tasks overdue, avg {rag.schedule.avg_slippage_days}d behind
- Upcoming milestones: {rag.milestones.milestones_upcoming} in next 30 days, {rag.milestones.milestones_at_risk} at risk
- Blocked tasks: {rag.blockers.blocked_count} tasks stuck, {rag.blockers.cascade_chains} cascade chains
- External dependencies overdue: {rag.dependencies.external_overdue_count}

Top blocked tasks:
{blockers_text if blockers_text else "  None"}

Top external delays:
{ext_text if ext_text else "  None"}

Write a 3-4 paragraph status update that:
1. Opens with the overall health and one-line summary
2. Explains WHY this project is rated {rag.overall_status} in plain business English
3. Calls out the top 2-3 specific risks or blockers by name
4. Ends with recommended actions

Keep it under 250 words. No bullet points in the narrative — write it like you're briefing someone in a meeting. Don't use jargon like "RAG" or "critical path" — say "behind schedule" or "key deliverables"."""


def _fallback_narrative(project: Project, rag: RAGResult) -> str:
    """when no API key is available, generate a basic narrative from the data"""
    lines = []
    lines.append(f"## {project.summary.name} — Status: {rag.overall_status.upper()}")
    lines.append("")
    lines.append(f"Project is {project.summary.percent_complete}% complete, "
                 f"currently in {project.summary.current_stage}.")
    lines.append("")

    red_dims = [d for d in rag.dimensions if d.status == "Red"]
    amber_dims = [d for d in rag.dimensions if d.status == "Amber"]

    if red_dims:
        lines.append("**Critical issues:**")
        for d in red_dims:
            lines.append(f"- {d.name}: {d.reason}")
        lines.append("")

    if amber_dims:
        lines.append("**Watch items:**")
        for d in amber_dims:
            lines.append(f"- {d.name}: {d.reason}")
        lines.append("")

    if rag.blockers.blocked_tasks:
        lines.append("**Top blockers:**")
        for b in rag.blockers.blocked_tasks[:5]:
            lines.append(f"- {b}")
        lines.append("")

    if rag.dependencies.external_overdue_tasks:
        lines.append("**External dependencies overdue:**")
        for e in rag.dependencies.external_overdue_tasks[:5]:
            lines.append(f"- {e}")

    return "\n".join(lines)
