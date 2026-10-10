# Employer groups and dated payroll — 0.6.0

HR creates pay groups under **Organization → Employer pay groups** for a legal employer and weekly, fortnightly, semimonthly or monthly frequency. Group definitions are create-only in this release. Assign each worker to that employer/currency first, then assign a payroll group. One worker belongs to one current group. Membership changes require both current employee/group versions, advance the worker and affected group versions, and record before/after history. Existing pay statements keep their original snapshots.

Under **Pay runs → Prepare dated payroll**, select the group, current roster version, period start/end, actual pay date, kind and reference. Regular weekly/fortnightly periods contain 7/14 days; semimonthly periods are days 1–15 or 16–month-end; monthly periods cover a complete calendar month. Date defaults are suggestions and must be reviewed. Bonus/adjustment periods support explicit dates and start with zero estimates. The product bounds periods to 366 days; this is an input limit, not a country's legal pay rule.

Preparation snapshots eligible group workers, employer/cost-center assignments, group name/version, period, pay date and kind. Sample workers are excluded. Employment start/end dates constrain the roster; inactive workers without an end date and stale employer/currency assignments require correction before preparation. Workers with valid separation dates can remain included in a period they worked. Existing monthly snapshots remain unchanged.

Regular draft gross amounts are estimates based on effective-dated annual salary divided by 12 and each calendar month's days, minus approved unpaid-leave fractions. This is not statutory weekly pay or an automatic country tax calculation. It can span month/year boundaries; joining/separation dates and effective salaries are read per day. Bonus/adjustment gross starts at zero to avoid silently paying ordinary salary twice.

Regular periods in the same group cannot overlap, and the same worker cannot appear in overlapping regular periods across groups after a membership transfer. A regular group run and a legacy organization-month run also cannot overlap for any included worker in either creation order. These checks do not identify every duplicate external earning or establish cumulative tax reconciliation; adjustments must be independently reviewed against the employer's payroll ledger.

## External results and review

Every worker in a dated run needs a reviewed external result before finalization, including zero-pay workers. Open the run and use **Import reviewed result**; its template is `openpeople.external-payroll.v2`. It binds the employee/country/currency and exact immutable `period` object: run/group IDs, group version, start/end, pay date, frequency, kind and reference. Preserve the supplied opaque `month` key; it is a compatibility identifier, not a date to parse. Legacy monthly templates remain version 1.

Imports require the current pay-run version, integer minor units, bounded components and balanced gross/deductions/net. No extra applicability or compliance flags are accepted. Changes preserve provider/reference/rules-date/review provenance and permanently record the importing editor. Your own statement requires a colleague to edit it. A colleague who neither created nor edited the run must review all included results and finalize using the current version. Finalized statements remain immutable; workers see only their own statement, including dates and pay-group label.

Restricted payroll operators can create/read/edit runs only within allowed employers. Historical reads use captured employers, not later transfers. A reviewer cannot finalize a run containing hidden statements. Filing workpapers carry the dated period contract alongside immutable employer/result data; they remain provider-neutral workpapers, not government submissions.

## Remaining payroll requirements

This capability supplies scheduling/snapshot/review controls, not complete statutory payroll. Country/state/province taxes, cumulative/retro/year-end rules, automatic calendar generation, retro links/reconciliation, corrections to finalized runs, payment execution, accounting/provider connectors and official submission acceptance require further implementation and jurisdiction review. See [country scope](PAYROLL_COUNTRIES.md), [statutory packs](STATUTORY_AND_FILINGS.md) and [government file adapter](GOVERNMENT_SUBMISSION.md).
