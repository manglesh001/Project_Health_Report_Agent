import os
from typing import Optional

from src.parser.data_model import Project
from src.scoring.rag_engine import RAGResult


def generate_monthly_synthesis(
    projects: list[tuple[Project, RAGResult]],
) -> str:
    """generate cross-project executive synthesis"""

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return _fallback_synthesis(projects)

    try:
        from google import genai
        client = genai.Client(api_key=api_key)

        prompt = _build_synthesis_prompt(projects)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        return response.text
    except Exception as e:
        print(f"  Warning: Gemini API failed ({e}), using fallback synthesis")
        return _fallback_synthesis(projects)


def _build_synthesis_prompt(projects: list[tuple[Project, RAGResult]]) -> str:
    project_summaries = []
    for project, rag in projects:
        dims = "\n".join(f"    - {d.name}: {d.status} — {d.reason}" for d in rag.dimensions)
        blockers = ", ".join(rag.blockers.blocked_tasks[:3]) if rag.blockers.blocked_tasks else "None"
        ext = ", ".join(rag.dependencies.external_overdue_tasks[:3]) if rag.dependencies.external_overdue_tasks else "None"

        project_summaries.append(f"""
  Project: {project.summary.name}
  PM: {project.summary.project_manager}
  Status: {rag.overall_status} | {project.summary.percent_complete}% complete
  Stage: {project.summary.current_stage}
  Timeline: {project.summary.start_date} to {project.summary.end_date}
  Dimensions:
{dims}
  Top blockers: {blockers}
  External delays: {ext}
  Schedule: avg {rag.schedule.avg_slippage_days}d behind, worst task {rag.schedule.max_slippage_days}d
""")

    all_projects = "\n---\n".join(project_summaries)

    return f"""You are writing an executive monthly synthesis for a VP of Professional Services. You have {len(projects)} active projects.

PROJECT DATA:
{all_projects}

Write a structured synthesis that covers these 5-7 sections (one per slide):

1. **Portfolio Overview** — one paragraph summarizing overall portfolio health. How many green/amber/red. Overall trajectory.

2. **Cross-Project Trends** — what patterns do you see ACROSS projects? Don't just summarize each one separately. Look for common themes: are customer teams consistently late? Are integrations always the bottleneck? Are certain phases running long?

3. **Risk Heat Map** — rank risks by likelihood and impact. What could blow up in the next 30 days?

4. **Top Blockers & Dependencies** — the 3-5 things that need executive attention RIGHT NOW. Be specific — name the task, the owner, and the impact.

5. **Delivery Forecast** — are these projects going to land on time? What's realistic? If something is going to slip, say by how much.

6. **Recommendations** — 3-5 concrete actions. Not generic advice like "improve communication." Specific: "Escalate supplier bulk upload sign-off at UniSan — 6-task chain is blocked, delaying Phase II production migration by 2+ weeks."

7. **Next Month Outlook** — what should leadership watch in the coming 30 days?

Write in executive English. No jargon. Be direct — if something is going wrong, say so clearly. Each section should be 3-5 sentences. Total output under 800 words.

Format as markdown with ## headers for each section."""


def _fallback_synthesis(projects: list[tuple[Project, RAGResult]]) -> str:
    """rule-based synthesis without LLM — still identifies cross-project patterns"""
    lines = []
    lines.append("# Monthly Portfolio Synthesis")
    lines.append("")

    red = sum(1 for _, r in projects if r.overall_status == "Red")
    amber = sum(1 for _, r in projects if r.overall_status == "Amber")
    green = sum(1 for _, r in projects if r.overall_status == "Green")

    # --- Portfolio Overview ---
    lines.append("## Portfolio Overview")
    lines.append("")
    lines.append(f"{len(projects)} active projects: {green} Green, {amber} Amber, {red} Red.")
    if red > 0:
        lines.append(f"{red}/{len(projects)} projects require immediate attention.")
    avg_completion = sum(p.summary.percent_complete for p, _ in projects) / len(projects)
    lines.append(f"Average portfolio completion: {avg_completion:.0f}%.")
    lines.append("")

    # --- Cross-Project Trends ---
    lines.append("## Cross-Project Trends")
    lines.append("")

    # find common patterns
    dep_risk_projects = [p.summary.name for p, r in projects
                         if any(d.status in ["Red", "Amber"] for d in r.dimensions if d.name == "Dependency Risk")]
    schedule_risk_projects = [p.summary.name for p, r in projects
                              if any(d.status in ["Red", "Amber"] for d in r.dimensions if d.name == "Schedule Slippage")]
    blocker_projects = [p.summary.name for p, r in projects
                        if any(d.status in ["Red", "Amber"] for d in r.dimensions if d.name == "Blocker Density")]

    if len(dep_risk_projects) > 1:
        lines.append(f"- **Customer dependency delays are systemic** — {len(dep_risk_projects)}/{len(projects)} projects blocked on client-side deliverables ({', '.join(dep_risk_projects)})")
    elif dep_risk_projects:
        lines.append(f"- External dependency risk on: {', '.join(dep_risk_projects)}")

    if len(schedule_risk_projects) > 1:
        lines.append(f"- **Schedule slippage across portfolio** — {len(schedule_risk_projects)}/{len(projects)} projects have critical path delays")
    elif schedule_risk_projects:
        lines.append(f"- Schedule slippage on: {', '.join(schedule_risk_projects)}")

    if blocker_projects:
        lines.append(f"- Task blockage affecting: {', '.join(blocker_projects)}")

    # check if integration/supplier tasks are a theme
    all_blocked = []
    all_ext = []
    for _, rag in projects:
        all_blocked.extend(rag.blockers.blocked_tasks)
        all_ext.extend(rag.dependencies.external_overdue_tasks)

    integration_blocked = [t for t in all_blocked + all_ext if "integration" in t.lower() or "mapping" in t.lower()]
    supplier_blocked = [t for t in all_blocked + all_ext if "supplier" in t.lower() or "bulk" in t.lower() or "data" in t.lower()]

    if integration_blocked:
        lines.append(f"- **Integration tasks are a recurring bottleneck** — {len(integration_blocked)} integration-related items blocked across portfolio")
    if supplier_blocked:
        lines.append(f"- **Data provisioning from clients is a common delay** — {len(supplier_blocked)} data/supplier tasks pending client action")
    lines.append("")

    # --- Risk Heat Map ---
    lines.append("## Risk Heat Map")
    lines.append("")
    lines.append("| Project | Schedule | Milestones | Blockers | Dependencies |")
    lines.append("|---------|----------|------------|----------|--------------|")
    for project, rag in projects:
        row = f"| {project.summary.name} |"
        for d in rag.dimensions:
            row += f" {d.status} |"
        lines.append(row)
    lines.append("")

    # --- Top Blockers ---
    lines.append("## Top Blockers & Dependencies")
    lines.append("")
    all_items = []
    for project, rag in projects:
        for task in rag.blockers.blocked_tasks[:3]:
            all_items.append(f"- **{project.summary.name}**: {task}")
        for task in rag.dependencies.external_overdue_tasks[:3]:
            all_items.append(f"- **{project.summary.name}** (external): {task}")
    for item in all_items[:10]:
        lines.append(item)
    lines.append("")

    # --- Delivery Forecast ---
    lines.append("## Delivery Forecast")
    lines.append("")
    for project, rag in projects:
        if rag.overall_status == "Red":
            lines.append(f"- **{project.summary.name}**: At risk of slipping. "
                         f"Current pace ({project.summary.percent_complete}% at this date) "
                         f"suggests delivery may extend beyond {project.summary.end_date}.")
        elif rag.overall_status == "Amber":
            lines.append(f"- **{project.summary.name}**: On track with risks. Monitor closely.")
        else:
            lines.append(f"- **{project.summary.name}**: On track for {project.summary.end_date}.")
    lines.append("")

    # --- Recommendations ---
    lines.append("## Recommendations")
    lines.append("")
    rec_num = 1
    if dep_risk_projects:
        lines.append(f"{rec_num}. Escalate client deliverable timelines — schedule executive sync with customer PMs to unblock pending items")
        rec_num += 1
    if supplier_blocked:
        lines.append(f"{rec_num}. Set hard deadlines for data provisioning with contractual consequences for delays")
        rec_num += 1
    if len(schedule_risk_projects) > 1:
        lines.append(f"{rec_num}. Conduct schedule recovery workshop across affected projects — identify tasks that can be parallelized or descoped")
        rec_num += 1
    for project, rag in projects:
        if rag.blockers.cascade_chains > 0:
            lines.append(f"{rec_num}. Break cascade chain in {project.summary.name} — assign dedicated resource to clear the sequential blocker")
            rec_num += 1
    lines.append(f"{rec_num}. Review resource allocation — {red} Red projects may need additional consultant capacity")
    lines.append("")

    # --- Next Month Outlook ---
    lines.append("## Next Month Outlook")
    lines.append("")
    lines.append("Key dates to watch in the next 30 days:")
    for project, rag in projects:
        if rag.milestones.at_risk_names:
            for m in rag.milestones.at_risk_names[:2]:
                lines.append(f"- {project.summary.name}: {m}")
        if rag.overall_status == "Red":
            lines.append(f"- {project.summary.name}: Continued Red status likely without executive intervention on blockers")
    lines.append("")

    return "\n".join(lines)
