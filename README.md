# Job search tracker

A private tracker for these US roles: Business Analyst, Data Analyst, Systems Analyst, Business Systems Analyst, Product Owner, Product Analyst, Associate Product Manager, Product Manager, Financial Analyst, and Business Intelligence Analyst.

A qualifying role must be explicitly US-eligible, require 2–5 years of experience, be a full-time employee position, have a current employer JD posted within 30 days, and disclose a USD annual **base** salary range whose maximum reaches at least $100,000. A range such as $90k–$130k qualifies with a lower-end caution. Senior/lead roles are excluded; “manager” is not penalized when the requested title is Product Manager.

## Reports

- [`job-tracker/MASTER-QUALIFYING.md`](job-tracker/MASTER-QUALIFYING.md): every currently qualifying reviewed role.
- `job-tracker/data/reports/BASELINE.md`: the explicitly published initial baseline.
- `job-tracker/data/reports/YYYY-MM-DD.md`: subsequent new-only daily publications.
- [`job-tracker/TRACKER.md`](job-tracker/TRACKER.md): complete queues, failures, and reviewed exclusions.
- `Latest Results.txt`: easy-to-read local rendering.

Daily reports use a durable identity/alias ledger. Re-rendering does not consume jobs; publication advances the ledger only after the report is written. Reports show an honest shortfall from the 15-new-match target and never repeat or pad unsuitable roles.

## Setup and checks

Requires Python 3.9+ and Git on macOS or Linux (use WSL on Windows). No third-party Python packages or credentials are required.

```sh
git clone https://github.com/pdokka/job-search-tracker.git
cd job-search-tracker
python3 -m venv .venv
.venv/bin/python3 run.py check --no-open
.venv/bin/python3 run.py open --no-open
```

## Collection, review, and publication

```sh
# Collection only: leads are not qualified by this command.
.venv/bin/python3 run.py refresh --no-open

# Show today's rotating searches for the separate evidence-review task.
.venv/bin/python3 job-tracker/tracker.py queries

# Persist dated discoveries and current-employer-JD reviews.
.venv/bin/python3 job-tracker/tracker.py import job-tracker/data/imports/YYYY-MM-DD-topic.json
.venv/bin/python3 job-tracker/tracker.py review job-tracker/data/reviews/YYYY-MM-DD-topic.json

# Re-render without affecting the publication ledger.
.venv/bin/python3 run.py open --no-open

# Run exactly once after the new policy has enough reviewed matches.
.venv/bin/python3 run.py baseline --no-open

# On later review days, publish every newly qualifying identity (no limit of 15).
.venv/bin/python3 run.py publish --no-open
```

The separate ChatGPT Work task performs open-web discovery and current-JD evidence review, then commits its dated import/review file, dated report, and updated durable state to this fork. The GitHub Actions collector remains collection-only and preserves `cloud-run.json`; it cannot invent evidence or qualify jobs.

## Sponsorship handling

Current JD language controls. An explicit offer is labeled **Offered**; conditional language is **Conditional** with its conditions; silence is **Not stated / needs confirmation** and may remain in the qualifying report. Language denying current/future sponsorship or requiring citizenship, permanent residence, or unrestricted authorization excludes the role. Historical sponsor searches and generic EEO/immigration boilerplate are not used as proof.

See [`job-tracker/RUNBOOK.md`](job-tracker/RUNBOOK.md) for the exact evidence contract. The tracker never applies, contacts anyone, creates accounts, or buys services.
