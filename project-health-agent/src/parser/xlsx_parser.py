import re
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import openpyxl
import pandas as pd

from src.parser.data_model import Project, ProjectSummary, Task


# column name variations we might see in these messy spreadsheets
COLUMN_ALIASES = {
    "task_name": ["task name", "task", "name", "activity", "description"],
    "status": ["status", "task status"],
    "percent_complete": ["% complete", "% comp", "percent complete", "complete %", "progress"],
    "start_date": ["start date", "start", "actual start"],
    "end_date": ["end date", "end", "finish", "actual finish", "actual end"],
    "baseline_start": ["baseline start", "bl start", "planned start"],
    "baseline_end": ["baseline finish", "baseline end", "bl finish", "bl end", "planned finish", "planned end"],
    "duration": ["duration", "dur"],
    "predecessors": ["predecessors", "predecessor", "depends on", "dependencies"],
    "owner": ["owner", "assigned to", "resource", "responsible", "ownership"],
    "priority": ["priority"],
    "total_float": ["total float", "float", "slack", "total slack"],
    "is_critical": ["critical ?", "critical", "is critical", "on critical path"],
    "on_hold": ["on hold?", "on hold", "hold"],
    "not_applicable": ["not applicable?", "not applicable", "n/a"],
    "level": ["level", "wbs level", "outline level"],
    "variance": ["variance", "variance2", "schedule variance"],
    "rag": ["rag", "schedule health", "health", "status comment"],
    "comments": ["comments", "notes", "comment"],
}


def match_column(header: str, target_key: str) -> bool:
    """fuzzy match a spreadsheet header to our internal field name"""
    header_clean = header.strip().lower()
    aliases = COLUMN_ALIASES.get(target_key, [])
    return header_clean in aliases


def find_column_mapping(headers: list[str]) -> dict[str, int]:
    """map our internal field names to column indices"""
    mapping = {}
    headers_lower = [h.strip().lower() if h else "" for h in headers]

    for field_name, aliases in COLUMN_ALIASES.items():
        for i, header in enumerate(headers_lower):
            if header in aliases:
                mapping[field_name] = i
                break

    return mapping


def parse_date(val) -> Optional[date]:
    """handle the various date formats and garbage values"""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    if isinstance(val, str):
        val = val.strip()
        if not val or val.startswith("#") or val == "N/A":
            return None
        # try common formats
        for fmt in ["%m/%d/%y", "%m/%d/%Y", "%Y-%m-%d", "%d/%m/%y", "%d/%m/%Y"]:
            try:
                return datetime.strptime(val, fmt).date()
            except ValueError:
                continue
    return None


def parse_float_safe(val) -> Optional[float]:
    """parse a number, returning None for garbage"""
    import math
    if val is None:
        return None
    if isinstance(val, (int, float)):
        if math.isnan(val):
            return None
        return float(val)
    if isinstance(val, str):
        val = val.strip()
        if not val or val.startswith("#") or val == "nan":
            return None
        try:
            result = float(val)
            if math.isnan(result):
                return None
            return result
        except ValueError:
            return None
    return None


def parse_percent(val) -> float:
    """parse percentage — could be 0.44, 44%, or 44"""
    if val is None:
        return 0.0
    if isinstance(val, str):
        val = val.strip().rstrip("%")
        if not val or val.startswith("#"):
            return 0.0
        try:
            val = float(val)
        except ValueError:
            return 0.0
    if isinstance(val, (int, float)):
        # if it's <= 1, assume it's a decimal (0.44 = 44%)
        if 0 < val <= 1:
            return val * 100
        return float(val)
    return 0.0


def parse_predecessors(val) -> list[str]:
    """parse predecessor strings like '264FS +5d', '267FF', '109, 122'"""
    if val is None:
        return []
    if isinstance(val, float):
        import math
        if math.isnan(val):
            return []
        return [str(int(val))]
    if isinstance(val, int):
        return [str(val)]
    val = str(val).strip()
    if not val or val == "nan":
        return []
    # split on commas, keep the relationship info
    parts = [p.strip() for p in val.split(",")]
    return [p for p in parts if p]


def parse_bool(val) -> bool:
    """parse Yes/No/TRUE/FALSE/checkmarks"""
    if val is None:
        return False
    if isinstance(val, bool):
        return val
    val = str(val).strip().lower()
    return val in ["yes", "true", "1", "x", "✓", "✔"]


def parse_task_sheet(df: pd.DataFrame) -> list[Task]:
    """parse the main task data from a dataframe"""
    headers = [str(c).strip() for c in df.columns.tolist()]
    col_map = find_column_mapping(headers)

    tasks = []
    for idx, row in df.iterrows():
        # skip completely empty rows
        if row.isna().all():
            continue

        # get task name — skip if empty
        name_col = col_map.get("task_name")
        if name_col is None:
            continue
        task_name = row.iloc[name_col] if name_col < len(row) else None
        if not task_name or (isinstance(task_name, str) and not task_name.strip()):
            continue

        task_name = str(task_name).strip()

        def get_val(field):
            col_idx = col_map.get(field)
            if col_idx is None or col_idx >= len(row):
                return None
            return row.iloc[col_idx]

        task = Task(
            row_id=idx + 1,
            name=task_name,
            status=str(get_val("status") or "Unknown").strip(),
            percent_complete=parse_percent(get_val("percent_complete")),
            start_date=parse_date(get_val("start_date")),
            end_date=parse_date(get_val("end_date")),
            baseline_start=parse_date(get_val("baseline_start")),
            baseline_end=parse_date(get_val("baseline_end")),
            duration=int(parse_float_safe(get_val("duration")) or 0) if parse_float_safe(get_val("duration")) is not None else None,
            predecessors=parse_predecessors(get_val("predecessors")),
            owner=str(get_val("owner") or ""),
            priority=str(get_val("priority") or ""),
            total_float=parse_float_safe(get_val("total_float")),
            is_critical=parse_bool(get_val("is_critical")),
            is_on_hold=parse_bool(get_val("on_hold")),
            is_not_applicable=parse_bool(get_val("not_applicable")),
            level=int(parse_float_safe(get_val("level")) or 0),
            variance_days=int(parse_float_safe(get_val("variance")) or 0) if parse_float_safe(get_val("variance")) is not None else None,
            rag_status=str(get_val("rag") or ""),
        )

        comments_val = get_val("comments")
        if comments_val and str(comments_val).strip():
            task.comments = [str(comments_val).strip()]

        tasks.append(task)

    return tasks


def parse_summary_sheet(df: pd.DataFrame, file_name: str) -> ProjectSummary:
    """parse the summary/dashboard sheet — usually key-value pairs"""
    summary_data = {}

    for _, row in df.iterrows():
        if row.isna().all():
            continue
        # look for key-value patterns
        vals = [str(v).strip() if pd.notna(v) else "" for v in row]
        for i, val in enumerate(vals):
            val_lower = val.lower()
            if "project manager" in val_lower and i + 1 < len(vals):
                summary_data["pm"] = vals[i + 1] if vals[i + 1] else vals[i + 2] if i + 2 < len(vals) else ""
            elif "project start" in val_lower:
                for j in range(i + 1, min(i + 3, len(vals))):
                    d = parse_date(vals[j])
                    if d:
                        summary_data["start"] = d
                        break
            elif "project end" in val_lower:
                for j in range(i + 1, min(i + 3, len(vals))):
                    d = parse_date(vals[j])
                    if d:
                        summary_data["end"] = d
                        break
            elif "not started" in val_lower:
                for j in range(i + 1, min(i + 3, len(vals))):
                    n = parse_float_safe(vals[j])
                    if n is not None:
                        summary_data["not_started"] = int(n)
                        break
            elif "in progress" == val_lower:
                for j in range(i + 1, min(i + 3, len(vals))):
                    n = parse_float_safe(vals[j])
                    if n is not None:
                        summary_data["in_progress"] = int(n)
                        break
            elif val_lower == "completed":
                for j in range(i + 1, min(i + 3, len(vals))):
                    n = parse_float_safe(vals[j])
                    if n is not None:
                        summary_data["completed"] = int(n)
                        break
            elif "on hold" in val_lower:
                for j in range(i + 1, min(i + 3, len(vals))):
                    n = parse_float_safe(vals[j])
                    if n is not None:
                        summary_data["on_hold"] = int(n)
                        break
            elif "% complete" in val_lower:
                for j in range(i + 1, min(i + 3, len(vals))):
                    n = parse_percent(vals[j])
                    if n > 0:
                        summary_data["percent"] = n
                        break
            elif "project stage" in val_lower:
                for j in range(i + 1, min(i + 3, len(vals))):
                    if vals[j] and not vals[j].startswith("#"):
                        summary_data["stage"] = vals[j]
                        break
            elif "today" in val_lower and "date" in val_lower:
                for j in range(i + 1, min(i + 3, len(vals))):
                    d = parse_date(vals[j])
                    if d:
                        summary_data["report_date"] = d
                        break

    # derive project name from filename
    proj_name = Path(file_name).stem.replace("_", " ").replace("-", " ")

    not_started = summary_data.get("not_started", 0)
    in_progress = summary_data.get("in_progress", 0)
    completed = summary_data.get("completed", 0)
    on_hold = summary_data.get("on_hold", 0)

    return ProjectSummary(
        name=proj_name,
        project_manager=summary_data.get("pm", "Unknown"),
        start_date=summary_data.get("start"),
        end_date=summary_data.get("end"),
        percent_complete=summary_data.get("percent", 0.0),
        total_tasks=not_started + in_progress + completed + on_hold,
        not_started=not_started,
        in_progress=in_progress,
        completed=completed,
        on_hold=on_hold,
        current_stage=summary_data.get("stage", "Unknown"),
        report_date=summary_data.get("report_date"),
    )


def parse_xlsx(file_path: str) -> Project:
    """main entry point — parse an xlsx file into our Project model"""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    wb = openpyxl.load_workbook(file_path, data_only=True)
    sheet_names = wb.sheetnames

    # heuristic: the biggest sheet is usually the task list,
    # a smaller sheet is the summary/dashboard
    tasks = []
    summary = None

    for sheet_name in sheet_names:
        ws = wb[sheet_name]
        # convert to dataframe for easier handling
        data = list(ws.values)
        if not data or len(data) < 2:
            continue

        # find header row (first row with multiple non-empty cells)
        header_row_idx = 0
        for i, row in enumerate(data):
            non_empty = sum(1 for cell in row if cell is not None and str(cell).strip())
            if non_empty >= 5:
                header_row_idx = i
                break

        headers = [str(h).strip() if h else f"col_{i}" for i, h in enumerate(data[header_row_idx])]
        rows = data[header_row_idx + 1:]

        df = pd.DataFrame(rows, columns=headers)

        # detect if this is a task sheet or summary sheet
        headers_lower = [h.lower() for h in headers]
        is_task_sheet = any(
            keyword in " ".join(headers_lower)
            for keyword in ["task name", "status", "start date", "% complete"]
        )

        if is_task_sheet and len(df) > 10:
            tasks = parse_task_sheet(df)
        else:
            # might be summary
            if summary is None:
                summary = parse_summary_sheet(df, path.name)

    if summary is None:
        summary = ProjectSummary(
            name=path.stem,
            project_manager="Unknown",
            start_date=None,
            end_date=None,
            percent_complete=0.0,
            total_tasks=len(tasks),
            not_started=0,
            in_progress=0,
            completed=0,
            on_hold=0,
            current_stage="Unknown",
        )

    # if summary has zero task counts but we parsed tasks, update from tasks
    if summary.total_tasks == 0 and tasks:
        summary.total_tasks = len(tasks)
        summary.completed = sum(1 for t in tasks if t.status == "Completed")
        summary.in_progress = sum(1 for t in tasks if t.status == "In Progress")
        summary.not_started = sum(1 for t in tasks if t.status == "Not Started")

    # if summary dates are still None, derive from tasks
    if summary.start_date is None and tasks:
        valid_starts = [t.start_date for t in tasks if t.start_date]
        if valid_starts:
            summary.start_date = min(valid_starts)
    if summary.end_date is None and tasks:
        valid_ends = [t.end_date for t in tasks if t.end_date]
        if valid_ends:
            summary.end_date = max(valid_ends)

    return Project(summary=summary, tasks=tasks)
