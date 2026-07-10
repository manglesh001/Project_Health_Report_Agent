#!/usr/bin/env python3
"""
Project Health Agent — reads xlsx project plans, scores them, generates reports.

Usage:
    python -m src.main weekly data/input/          # weekly report for all xlsx files
    python -m src.main monthly data/input/         # monthly synthesis + slides
    python -m src.main schedule data/input/        # run weekly on a schedule (Mondays 9am)
"""

import argparse
import sys
from datetime import date
from pathlib import Path

from src.parser.xlsx_parser import parse_xlsx
from src.scoring.rag_engine import compute_rag
from src.reporting.weekly_report import generate_weekly_report, save_weekly_report
from src.reporting.monthly_synthesis import generate_monthly_synthesis
from src.presentation.slide_generator import create_executive_deck


def run_weekly(input_dir: str, output_dir: str = "data/output", use_llm: bool = True):
    """process all xlsx files and generate weekly reports"""
    input_path = Path(input_dir)
    xlsx_files = list(input_path.glob("*.xlsx")) + list(input_path.glob("*.xls"))

    if not xlsx_files:
        print(f"No xlsx files found in {input_dir}")
        sys.exit(1)

    print(f"Found {len(xlsx_files)} project file(s)")
    config_path = str(Path(__file__).parent.parent / "config" / "settings.yaml")

    for xlsx_file in xlsx_files:
        print(f"\n{'='*60}")
        print(f"Processing: {xlsx_file.name}")
        print(f"{'='*60}")

        try:
            project = parse_xlsx(str(xlsx_file))
            print(f"  Parsed {len(project.tasks)} tasks")
            print(f"  Project: {project.summary.name}")
            print(f"  PM: {project.summary.project_manager}")
            print(f"  Completion: {project.summary.percent_complete}%")

            rag = compute_rag(project, config_path)
            print(f"  RAG Status: {rag.overall_status}")
            for dim in rag.dimensions:
                icon = {"Red": "🔴", "Amber": "🟡", "Green": "🟢"}.get(dim.status, "⚪")
                print(f"    {icon} {dim.name}: {dim.reason}")

            report = generate_weekly_report(project, rag, use_llm=use_llm)
            report_path = save_weekly_report(report, project.summary.name, output_dir)
            print(f"  Report saved: {report_path}")

        except Exception as e:
            print(f"  ERROR processing {xlsx_file.name}: {e}")
            import traceback
            traceback.print_exc()


def run_monthly(input_dir: str, output_dir: str = "data/output", use_llm: bool = True):
    """process all projects and generate monthly synthesis + slides"""
    input_path = Path(input_dir)
    xlsx_files = list(input_path.glob("*.xlsx")) + list(input_path.glob("*.xls"))

    if not xlsx_files:
        print(f"No xlsx files found in {input_dir}")
        sys.exit(1)

    config_path = str(Path(__file__).parent.parent / "config" / "settings.yaml")
    projects = []

    for xlsx_file in xlsx_files:
        try:
            project = parse_xlsx(str(xlsx_file))
            rag = compute_rag(project, config_path)
            projects.append((project, rag))
            print(f"  ✓ {project.summary.name}: {rag.overall_status}")
        except Exception as e:
            print(f"  ✗ {xlsx_file.name}: {e}")

    if not projects:
        print("No projects successfully parsed")
        sys.exit(1)

    print(f"\nGenerating monthly synthesis for {len(projects)} projects...")

    if use_llm:
        synthesis = generate_monthly_synthesis(projects)
    else:
        from src.reporting.monthly_synthesis import _fallback_synthesis
        synthesis = _fallback_synthesis(projects)

    # save synthesis as markdown
    synthesis_path = Path(output_dir) / f"monthly_synthesis_{date.today().strftime('%Y%m')}.md"
    synthesis_path.parent.mkdir(parents=True, exist_ok=True)
    synthesis_path.write_text(synthesis)
    print(f"  Synthesis saved: {synthesis_path}")

    # generate slides
    print("Generating executive presentation...")
    slides_path = create_executive_deck(projects, synthesis, output_dir)
    print(f"  Presentation saved: {slides_path}")


def run_schedule(input_dir: str, output_dir: str = "data/output"):
    """run weekly reports on a schedule"""
    import schedule
    import time

    print("Scheduling weekly reports for Monday 9:00 AM...")
    print(f"  Input: {input_dir}")
    print(f"  Output: {output_dir}")
    print("  Press Ctrl+C to stop")

    schedule.every().monday.at("09:00").do(run_weekly, input_dir, output_dir)

    # also run monthly on first Monday
    def monthly_check():
        if date.today().day <= 7:
            run_monthly(input_dir, output_dir)

    schedule.every().monday.at("09:30").do(monthly_check)

    # run once immediately
    print("\nRunning initial report...")
    run_weekly(input_dir, output_dir)

    while True:
        schedule.run_pending()
        time.sleep(60)


def main():
    parser = argparse.ArgumentParser(description="Project Health Reporting Agent")
    parser.add_argument("command", choices=["weekly", "monthly", "schedule"],
                        help="What to run: weekly report, monthly synthesis, or scheduled")
    parser.add_argument("input_dir", help="Directory containing .xlsx project plans")
    parser.add_argument("--output", "-o", default="data/output", help="Output directory")
    parser.add_argument("--no-llm", action="store_true",
                        help="Skip LLM narrative (use basic template instead)")

    args = parser.parse_args()

    use_llm = not args.no_llm

    if args.command == "weekly":
        run_weekly(args.input_dir, args.output, use_llm)
    elif args.command == "monthly":
        run_monthly(args.input_dir, args.output, use_llm)
    elif args.command == "schedule":
        run_schedule(args.input_dir, args.output)


if __name__ == "__main__":
    main()
