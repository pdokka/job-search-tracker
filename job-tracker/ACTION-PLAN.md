# Dheeraj’s daily job tracker

## What you receive

Open [the tracker](TRACKER.md) for application-ready roles and a separate ₹17–20L caution queue. Each qualifying row has the direct posting, employer-stated pay, experience evidence, location and original posting date or recent hiring signal. New qualifying roles trigger a message in this task. Applications remain your decision.

## Every day at 9:00 a.m. India time

1. Collect new listings from six public job feeds and the current Hacker News hiring thread. Search India remote, worldwide remote and Hyderabad. Capture employers and application destinations discovered in those feeds, even when the employer was not in the previous company list.
2. Refresh discovered employer boards directly. Keep the employer registry growing as new links emerge. Use rotating open-web searches for platforms and company sites that the feeds miss.
3. Verify the original job: India eligibility, 1–2-year suitability, guaranteed pay, employment type, original date, active application route and any recent hiring announcement. A salary estimate or foreign-only salary cannot qualify.
4. Add only evidence-backed roles to Ready (>₹20L) or Caution (₹17–20L). Keep promising but incomplete leads in Needs verification. Remote contracts need a stated minimum 12-month term. Unknown salary/duration is not quietly passed.
5. Recheck previous qualifying roles, detect changes and closures, and preserve history. On Mondays, summarise the preceding week without replacing the daily queue.

## How this avoids the previous mistakes

- No hardcoded company allowlist. Public feeds and full hiring threads provide discovery independently of search rankings; employer boards expand from observed links.
- Original posting dates are separate from first seen, feed publication and page modification. An old listing needs a dated recent hiring signal; an open page alone is insufficient.
- Wellfound/YC are discovery routes when useful. The review follows the employer's actual application destination and records it; it does not assume any platform will generate a response.
- Posted salary must apply to the Indian candidate. Uniform global pay, regional pay and unspecified policies remain distinct. A USD hourly rate is not a guaranteed annual salary.
- Requisition URLs/IDs and verified aliases are used for deduplication. Reposts do not reset the first-seen date.
- Coverage reports show page limits, blocked sources and fetch failures. Unverified leads are never counted as 50 qualifying jobs.

## What is built and what depends on the daily run

The local Python collector, persistent records, evidence filters, candidate review queue, date checks, employer-board discovery, source-failure reporting and regression tests are implemented. The scheduled Codex run executes the open-web queries and reviews descriptions that require judgment or a browser; Python alone does not perform that part.

The schedule runs in this task using local files, so keep this computer on and the app running at the scheduled time. [Official scheduled-task documentation](https://learn.chatgpt.com/docs/automations?surface=app).

No source covers every employer. The operating goal is to expand measurable coverage and deliver fresh verified matches daily. It is not to inflate a list to 50 or to promise an offer.

Technical operation and evidence schema: [runbook](RUNBOOK.md). The current source and query audit is included in [the tracker](TRACKER.md).
