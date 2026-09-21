# Scheduled refresh — 20 September 2026, evening

**No new Ready or Caution jobs.** The existing Ready queue remains Indeed Software Engineer I. No previously recommended role closed or materially changed during this pass.

The tracker now contains 2,224 collected leads, 39 reviewed roles, and 56 discovered employer boards. One role is Ready and none are Caution. Unverified leads do not count toward the target of 50 qualified jobs.

## Work completed

- Collected public feeds and the next discovery/backfill pages, reusing cached responses where available. The collector initially added 129 entries; subsequent duplicate reconciliation and original-posting imports changed the final total.
- Executed and audited 16 rotating integration-engineer discovery queries plus four targeted searches for newly observed employers.
- Reviewed four additional original postings. Reused the earlier same-day evidence review for unchanged Ready/Caution records.
- [Bubblehouse Integration Engineer](https://jobs.bubblehouse.com/integration-engineer/): $70–110k annual cash compensation, but requires around 5–10 years. Excluded.
- [DualEntry Hardcore Engineer](https://jobs.ashbyhq.com/dualentry/f43f3646-8342-497c-b364-b14b3d6f382f): old India-remote role absent from the current employer board; matching LinkedIn listing is expired. Marked Closed, not an active high-salary opportunity.
- [WebEngage Data Engineer](https://webengage.hire.trakstar.com/jobs/fk0zs8y/): 1–3 years, but employer specifies Mumbai with partial remote work and publishes no salary. Excluded by location.
- [Sanctuary Computer Senior Shopify Developer](https://wellfound.com/jobs/4735188-senior-shopify-developer): employer publishes $80–160k and an 18 September date, but requires 8+ years and offers a contract without a verified 12-month term. Visible worldwide geography conflicts with US-only structured metadata. Excluded. The higher RemoteOK range was not used as employer evidence.

## Reliability and coverage

RemoteOK, Anthropic and Stream recovered. Caseware and SugarCRM were not selected in this pass's rotating board batch; their earlier failures remain unresolved and are shown in both user-facing reports. Sixteen of twenty employer-link discovery fetches failed. Search also reported a Built In robots restriction. Public feed and search coverage remains incomplete.

Fixed a collector defect that recreated feed entries after they had been merged into an employer original. Nine existing duplicates were reconciled, and future repeat feed entries now preserve the employer facts, review and application status. Also fixed the reports so earlier board failures do not disappear merely because a board was not scanned in the latest batch.

All 25 checks passed, including regressions for returning aliases, duplicate-history preservation and visibility of unresolved board failures. Refreshed Latest Results.txt and the detailed tracker. No applications, accounts or outreach were created.

The earlier same-day report contains the still-held CentralApp and AnswerThis leads and the detailed Indeed evidence: [earlier review](RUN-2026-09-20.md).
