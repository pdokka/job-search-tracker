# Job search tracker

A shared tracker for Dheeraj's software-engineering job search: Hyderabad or verified India-eligible remote, suitable for 1–2 years of experience, with employer-backed salary evidence.

The repository includes the collector, eligibility checks, saved job records, evidence reviews, search audit and reports. It does not submit applications.

## Read the results

- [Current tracker](job-tracker/TRACKER.md)
- [Latest reviewed run: 21 September 2026](job-tracker/RUN-2026-09-21.md)
- [Weekly summary](job-tracker/WEEKLY.md)
- [Review process and evidence rules](job-tracker/RUNBOOK.md)

Reports are dated snapshots, not a guarantee that a job remains open. Re-rendering recalculates freshness; it does not replace reading current employer evidence. Collected leads do not count as verified matches.

## Set up a copy

Requires Python 3.9+ and Git on macOS or Linux. On Windows, use WSL because the tracker uses POSIX file locking. No third-party Python packages, IDE, API keys or paid services are required.

```sh
git clone https://github.com/DheerajDV/job-search-tracker.git
cd job-search-tracker
python3 -m venv .venv
.venv/bin/python3 run.py check --no-open
.venv/bin/python3 run.py open --no-open
```

Private repository access is required before cloning. The last command produces `Latest Results.txt` in your checkout.

On macOS, after creating the environment, the included launchers work by double-click:

- `Open Results.command`: update and open saved results in TextEdit.
- `Run Tracker.command`: collect listings and open the results.
- `Check Setup.command`: run the existing regression checks.

On Linux/WSL, use the commands below with `--no-open`.

## Collect and review

```sh
# Collect public sources; this may take several minutes.
.venv/bin/python3 run.py refresh --no-open

# Print today's discovery queries for a human or connected agent to execute.
.venv/bin/python3 job-tracker/tracker.py queries

# After reviewing employer evidence, import dated discoveries and reviews.
.venv/bin/python3 job-tracker/tracker.py import path/to/discoveries.json
.venv/bin/python3 job-tracker/tracker.py review path/to/reviews.json

# Rebuild readable results after evidence changes.
.venv/bin/python3 run.py open --no-open
```

The Python collector gathers leads from public feeds, hiring announcements and discovered employer boards. Open-web searches and evidence verification are performed separately by a human or connected agent, following the runbook. A collection run is not a full verification run.

## Qualification rules

- **Ready:** annual guaranteed base above ₹20 lakh.
- **Caution:** ₹17–20 lakh; the lower bound of the advertised range decides.
- Hyderabad employment or remote work explicitly available from India.
- Experience requirements compatible with 1–2 years; a two-year minimum requires two completed years.
- Employer salary evidence, not estimates, company averages, CTC or equity.
- Employer posting within 30 days, or a recent dated hiring signal.
- Remote contracts require a documented guaranteed term of at least 12 months. Hourly/task rates are not annualized into guaranteed income.

Unknown facts remain in Needs verification. There is no promise of exhaustive internet coverage or application acceptance.

## Collaborate

See [CONTRIBUTING.md](CONTRIBUTING.md). Use branches and pull requests for changes. Add discoveries and evidence as dated JSON files; coordinate before changing the shared state snapshot.

`job-tracker/data/state.json` contains the saved jobs, provenance, reviews and history. It is included so a collaborator can continue from the current project. Local response caches, recovery backups, logs, credentials and machine setup are excluded.

The existing daily 9am India-time Codex review belongs to Dheeraj's local installation. Cloning this repository does not install that schedule or connect another machine to his task. Local refreshes also do not automatically commit or push to GitHub; repository results update when the owner pushes a new snapshot.
