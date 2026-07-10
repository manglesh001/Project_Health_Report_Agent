# Project Health Reporting Agent

Automated project health reporting system that reads .xlsx project plans, scores them using a deterministic RAG (Red/Amber/Green) model, and generates weekly status reports plus monthly executive presentations.

Built for Professional Services teams who need visibility into project health without chasing PMs every week.

## What it does

1. **Parses messy .xlsx project plans** — handles inconsistent column headers, missing data, NaN values, #UNPARSEABLE fields, varied date formats
2. **Scores each project across 4 dimensions** — Schedule Slippage, Milestone Health, Blocker Density, Dependency Risk (deterministic, no AI in the scoring)
3. **Generates plain-English narrative** — uses Google Gemini LLM to explain WHY a project is Red/Amber/Green in business language
4. **Monthly cross-project synthesis** — identifies trends ACROSS projects (not just per-project summaries) and generates a 7-slide VP-ready PowerPoint deck

## Prerequisites

- Python 3.10+
- pip (Python package installer)
- Google Gemini API key (free tier works — get one at https://aistudio.google.com/apikey)

## Installation

```bash
cd project-health-agent
pip install -r requirements.txt
```

On Windows (if `pip` isn't in PATH):
```powershell
& "C:\Users\<your-username>\AppData\Local\Programs\Python\Python312\python.exe" -m pip install -r requirements.txt
```

## How to Run

### Generate test data (first time only)

```bash
python -m tests.create_test_data
```

This creates two sample .xlsx files in `data/input/` that mirror real project plan structures.

---

### Option A: Run WITH LLM (Gemini) — Recommended

This gives you AI-generated executive narratives in the reports. The Gemini API free tier is sufficient.

**Linux/Mac:**
```bash
export GEMINI_API_KEY="your-gemini-api-key-here"

# Weekly reports
python -m src.main weekly data/input/

# Monthly synthesis + PowerPoint slides
python -m src.main monthly data/input/
```

**Windows (PowerShell):**
```powershell
$env:GEMINI_API_KEY="your-gemini-api-key-here"

# Weekly reports
python -m src.main weekly data/input/

# Monthly synthesis + PowerPoint slides
python -m src.main monthly data/input/
```

**Windows (CMD):**
```cmd
set GEMINI_API_KEY=your-gemini-api-key-here

python -m src.main weekly data/input/
python -m src.main monthly data/input/
```

**What happens:** The agent calls Gemini to generate VP-level narratives. If the API fails (quota, network), it automatically falls back to the rule-based narrative — no crash, no error.

---

### Option B: Run WITHOUT LLM (offline mode)

No API key needed. Uses rule-based templates for the narrative sections instead.

```bash
python -m src.main weekly data/input/ --no-llm
python -m src.main monthly data/input/ --no-llm
```

The scoring and all data analysis is identical in both modes — only the narrative text differs. With `--no-llm` you get structured bullet points instead of prose.

---

### Option C: Run on a weekly schedule (Bonus)

```bash
export GEMINI_API_KEY="your-gemini-api-key-here"
python -m src.main schedule data/input/
```

Runs weekly reports every Monday at 9:00 AM. Monthly synthesis runs automatically on the first Monday of each month. Runs once immediately on startup, then continues on schedule.

For production deployment, use a cron job or Windows Task Scheduler:
```cron
0 9 * * 1 cd /path/to/project-health-agent && python -m src.main weekly data/input/
0 9 1-7 * 1 cd /path/to/project-health-agent && python -m src.main monthly data/input/
```

## Expected Output

After running weekly + monthly, you'll find these in `data/output/`:

```
data/output/
├── Project_B_UniSan_20260710_weekly.md         # Weekly report (UniSan)
├── S2P_Project_Titan_20260710_weekly.md        # Weekly report (Titan)
├── monthly_synthesis_202607.md                 # Cross-project synthesis
└── monthly_executive_report_202607.pptx        # 7-slide PowerPoint deck
```

**Sample scoring output:**
```
UniSan S2P Implementation — RED
  🟢 Schedule Slippage: Schedule on track
  🔴 Milestone Health: 2 missed, 0 at risk
  🟡 Blocker Density: 3 tasks blocked
  🔴 Dependency Risk: 8 external tasks overdue (max 28d)

Titan S2P Implementation — RED
  🔴 Schedule Slippage: Critical path avg 48.3d behind (max: 81d)
  🟢 Milestone Health: All 2 upcoming milestones on track
  🟢 Blocker Density: No significant blockers
  🔴 Dependency Risk: 3 external tasks overdue (max 14d)
```

## How to use with your own project files

Drop any .xlsx project plans into `data/input/`. The parser handles:
- Multiple sheets (auto-detects task list vs. summary/dashboard)
- Varied column names (fuzzy matching — "Task Name", "Activity", "Description" all work)
- Missing baseline dates, NaN values, percentage formats (0.44, 44%, "44%")
- Predecessor encoding (264FS +5d, 267FF, "109, 122")
- WBS hierarchy levels
- #UNPARSEABLE values from broken formulas

## Design Decisions

1. **Deterministic scoring, LLM only for narrative** — The RAG rating is reproducible and auditable. You get the same score every run regardless of LLM availability. The AI just explains the result in business English.

2. **Any single Red = overall Red** — You can't average away a critical failure. If milestones are missed, the project is Red even if schedule looks fine.

3. **External dependency tracking** — We parse the Owner field to distinguish customer-owned vs internal tasks. This catches the "waiting on client" problem that kills most implementations.

4. **Cascade chain detection** — We walk the dependency graph to find sequences of 3+ stuck tasks. A single blocked task is annoying; a 6-task cascade chain means Phase II is dead until someone acts.

5. **Graceful degradation** — No API key? Falls back to templates. NaN in the data? Skipped safely. Missing baseline? Skip variance calc for that task. The agent never crashes on bad data.

## Scoring Model

See [RAG_METHODOLOGY.md](RAG_METHODOLOGY.md) for the full methodology.

| Dimension | Weight | Green | Amber | Red |
|-----------|--------|-------|-------|-----|
| Schedule Slippage | 35% | ≤5d avg, ≤10d max | 6-15d avg or 11-25d max | >15d avg or >25d max |
| Milestone Health | 25% | All on track | 1 at risk | 2+ at risk or any missed |
| Blocker Density | 25% | 0-2 blocked | 3-5 blocked or 1 cascade | 6+ blocked or 2+ cascades |
| Dependency Risk | 15% | None overdue | 1-2 overdue <10d | 3+ overdue or any >10d |

## Configuration

Edit `config/settings.yaml` to tune:
- Threshold values for each RAG dimension
- Keywords that identify external/customer teams (e.g., "UniSan", "Titan", "OTK")
- Milestone detection keywords
- LLM model selection

## Project Structure

```
project-health-agent/
├── src/
│   ├── parser/
│   │   ├── data_model.py        # Project/Task dataclasses
│   │   └── xlsx_parser.py       # Fuzzy column matching, handles messy data
│   ├── scoring/
│   │   ├── signals.py           # Signal extraction + cascade chain detection
│   │   └── rag_engine.py        # Deterministic RAG scoring engine
│   ├── reporting/
│   │   ├── narrative.py         # Gemini-powered plain-English narrative
│   │   ├── weekly_report.py     # Per-project weekly markdown report
│   │   └── monthly_synthesis.py # Cross-project trend analysis
│   ├── presentation/
│   │   └── slide_generator.py   # 7-slide executive PowerPoint deck
│   └── main.py                  # CLI entry point
├── config/
│   └── settings.yaml            # Configurable thresholds and keywords
├── data/
│   ├── input/                   # Drop .xlsx project plans here
│   └── output/                  # Generated reports land here
├── tests/
│   └── create_test_data.py      # Generates test xlsx from project data
├── RAG_METHODOLOGY.md           # One-page scoring methodology (Phase 1)
├── requirements.txt
└── README.md
```

## Tech Stack

- **Python 3.10+** — standard library + minimal dependencies
- **openpyxl + pandas** — xlsx parsing with fuzzy header matching
- **google-genai** — Gemini 2.5 Flash for narrative generation
- **python-pptx** — PowerPoint slide generation
- **PyYAML** — configuration
- **schedule** — weekly cron-like scheduling
