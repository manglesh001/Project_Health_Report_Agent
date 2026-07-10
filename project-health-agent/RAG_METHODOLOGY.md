# RAG Status Methodology

## How this works

We compute a Red/Amber/Green status for each project by looking at 4 things that actually matter. No fluff, no vanity metrics.

The scoring is deterministic — no AI involved in the rating itself. The AI only writes the narrative explanation after the math is done. This means the rating is reproducible and auditable.

## The 4 Dimensions

### 1. Schedule Slippage (Weight: 35%)

What we measure: How far behind are the tasks that actually matter?

We look at critical path tasks (tasks with zero float OR flagged as critical) and measure:
- Average days overdue across all critical tasks currently in progress or past due
- Maximum single-task slippage (one really late task is worse than five slightly late ones)

Scoring:
- GREEN: Average slippage ≤ 5 days, max slippage ≤ 10 days
- AMBER: Average 6-15 days OR max 11-25 days
- RED: Average > 15 days OR max > 25 days

We compute variance as: (Actual End or Today's Date) - Baseline End. Negative baseline variance in the source data means the task is behind.

### 2. Milestone Health (Weight: 25%)

What we measure: Will the next milestones actually land on time?

We identify milestones (zero-duration tasks, or tasks explicitly marked as milestones) due in the next 30 days and check:
- Is the predecessor chain on track to finish before the milestone date?
- Are the predecessor tasks progressing at a rate that makes the deadline realistic?

We flag a milestone as "at risk" if:
- Any of its direct predecessors are overdue
- The remaining work on predecessors, at current velocity, won't finish in time

Scoring:
- GREEN: All milestones in next 30 days are achievable
- AMBER: 1 milestone at risk
- RED: 2+ milestones at risk OR any milestone already missed

### 3. Blocker Density (Weight: 25%)

What we measure: How many tasks are stuck and blocking other work?

A "blocked task" is defined as:
- Status is Not Started or In Progress at < 10%
- Start date is in the past
- Has downstream dependents waiting on it

We also detect "cascade chains" — sequences of 3+ tasks where task 1 is stuck, and tasks 2/3/4 can't start until it finishes.

Scoring:
- GREEN: 0-2 blocked tasks, no cascade chains
- AMBER: 3-5 blocked tasks OR 1 cascade chain
- RED: 6+ blocked tasks OR 2+ cascade chains

### 4. Dependency Risk (Weight: 15%)

What we measure: Are external teams or customer deliverables holding things up?

We identify tasks owned by the customer/external team (parsed from Owner field) that are:
- Overdue (past end date, not 100% complete)
- Blocking Zycus-owned tasks downstream

This is the "someone else is late and it's going to hit us" signal.

Scoring:
- GREEN: No external dependencies overdue
- AMBER: 1-2 external tasks overdue by < 10 days
- RED: 3+ external tasks overdue OR any external task overdue by > 10 days

## How dimensions combine into a final RAG

**RED if:** ANY single dimension scores Red. One critical failure mode is enough — you can't average your way out of a blown milestone.

**AMBER if:** Any dimension scores Amber AND no dimension scores Red.

**GREEN if:** All dimensions score Green.

## What we can't measure (and don't pretend to)

- **Budget burn** — not in the data. If added later, it would get 20% weight and others would scale down.
- **Stakeholder sentiment** — we infer some from comments/blockers, but we don't have survey data.
- **Quality** — no defect data available.
- **Team morale/capacity** — not measurable from a project plan.

## Assumptions

1. Baseline dates represent the agreed-upon plan. If no baseline exists for a task, we skip it in variance calculations.
2. Tasks with 0 duration are milestones.
3. The "Owner" field distinguishes internal (Zycus) vs external (Customer) teams by keyword matching.
4. "Float" values near 0 (< 1 day) indicate critical path tasks.
5. When % complete data looks stale (hasn't changed but task is in progress), we trust dates over percentages.
6. Week-over-week trend requires at least 2 runs to compute. First run has no trend data.
