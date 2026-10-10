# Dated statutory calculations and filing workpapers

OpenPeople 0.6.0 includes two partial calculation packs, an employer-scoped filing workpaper workflow and a separate restricted SSA annual-file adapter. Complete statutory payroll, online government submissions and payments remain unavailable. Country selection is not legal compliance.

## Embedded rules

`US-FEDERAL-PERIODIC-2026.1` handles ordinary US resident periodic wages in USD, a 2020-or-later W-4 and 2026 pay dates. Federal percentage-method withholding follows [IRS Publication 15-T worksheet 1A and automated schedules](https://www.irs.gov/publications/p15t); FICA uses [IRS Publication 15](https://www.irs.gov/publications/p15). Sources were checked on 9 October 2026. This implementation has not received independent payroll-specialist acceptance.

Reviewers explicitly supply gross pay, federal/Social Security/Medicare taxable bases, same-employer prior-year-to-date wages, regular frequency and W-4 fields. Decimal arithmetic rounds final deductions to cents. Unsupported countries/dates, unknown fields, nonordinary wages and ambiguous amounts are rejected. No tax status or accumulated wage base is inferred from salary.

For a $5,000 ordinary monthly payment using the template's single-person W-4 and zero adjustments/prior wages, federal withholding is $418.33, Social Security $310.00 and Medicare $72.50. Net **before other deductions** is $4,199.17; employer FICA is separate. Tests include independently worked examples for all filing-status/Step-2 combinations, a bracket crossing, wage caps and Additional Medicare crossings.

**US exclusions:** state/local taxes, unemployment tax, supplemental wages/tips, exemptions, nonresident/special-worker rules, legacy W-4, benefits, corrections, filing and payment. The pack is not complete US payroll.

`GB-CLASS1-NI-2026-27.1` handles ordinary non-director weekly/monthly Class 1 National Insurance in GBP for 6 April 2026 through 5 April 2027. The operator must review category eligibility; the pack supports the 16 published category letters and their employee/employer thresholds. It uses [HMRC's 2026/27 rates](https://www.gov.uk/guidance/rates-and-thresholds-for-employers-2026-to-2027) and the exact-percentage software rounding specified in [National Insurance technical guidance](https://www.gov.uk/government/publications/payroll-technical-specifications-national-insurance): inspect the third decimal pound digit only, rounding 5 or less down and 6 or greater up. Tests include independently worked boundaries, category examples and published rounding examples. PAYE income tax, directors, irregular periods, student loans, pensions, statutory pay, filing and payment are excluded. This pack also lacks independent payroll-specialist acceptance.

HR/payroll opens the statutory preview under **Pay runs** and chooses the US or UK template. `GET /api/statutory` supplies the catalog/templates; `POST /api/statutory/preview` calculates without saving or finalizing a payroll snapshot. Unsupported dates/applicability fail explicitly. Neither pack supplies complete automatic payroll; see [country guidance](PAYROLL_COUNTRIES.md).

## Employers and cost centers

HR creates employer/cost-center records under **Organization**, then assigns real workers. A center belongs to one employer; worker/employer country and currency must match. Assignments require and advance the current employee version, preventing stale employee edits. Remove mismatching assignments before changing a worker profile; existing financial-history currency safeguards still apply.

New pay runs capture each statement's employer and center. Later reassignment/removal does not rewrite those snapshots. Upgraded existing statements have no inferred employer. Definitions are create-only in this release. HR can now restrict payroll members to selected employers; historical statements follow their captured employer. This is [payroll access within one workspace](ENTERPRISE_CONTROLS.md), not separate tenant isolation. Employer-bound [dated pay groups](PAY_PERIODS.md) are now available; their period contract is retained in filing workpapers. Those groups do not calculate complete statutory payroll.

## Filing workpaper lifecycle

1. Import externally reviewed components for each included worker; an independent colleague finalizes the payroll run.
2. **Prepare workpaper** selects that finalized run and employer. The server verifies the current run version, employer/country/currency and reviewed results, then stores canonical JSON and SHA-256. Only one packet per run/employer is permitted.
3. Export and reconcile the immutable packet, including employer metadata, statement components/provenance, currency-specific totals and country review topics. `openpeople.filing-workpaper.v1` is a provider-neutral workpaper, **not** an agency submission schema. It includes only workers assigned to the employer in the source snapshot; verify roster completeness with your provider. Exports contain confidential payroll information.
4. A colleague who did not prepare the packet or create/edit its payroll source independently reviews with a note. Stale versions are rejected. Status changes cannot edit packet contents.
5. Submit separately through an authorized provider/official service. Record **Submitted externally**, then **Accepted externally** or **Rejected externally**, with a reference and retained receipt's SHA-256. These record operator evidence; `authority_verified` remains false. Arbitrary hashes do not authenticate government acceptance. No agency endpoint or bank is contacted.

Changes enter business/security audit and advance shared revision. Audit entries omit duplicate packet contents while retaining hashes/history. Only authorized HR/payroll accesses payloads, with payroll employer restrictions enforced. Session/MFA/CSRF/idempotency controls apply. Encrypted backups retain packets, assignments and snapshots. Corrections/replacement packets and live agency adapters remain future work.

## Restricted annual file export

The separate [2026 SSA EFW2 adapter](GOVERNMENT_SUBMISSION.md) writes original domestic regular-employment RA/RE/RW/RT/RF records from private, reviewed annual inputs with no optional W-2 amounts. It does not transform one monthly workpaper into annual totals or transmit to an authority. Official format positions/totals/private output are locally tested; authorized AccuWage validation and BSO acceptance remain pending. Other agency-specific schemas/transports remain unimplemented.

## Remaining implementation

Each jurisdiction needs independent review of dated rules, employer/state/province/worker applicability, all pay types, cumulative balances, agency formats, registration/certificates and official/provider sandbox acceptance. None of those services is configured here. Workday's native country engines and broader partner network cannot be copied as one universal law file; [the comparison](PAYROLL_COUNTRIES.md) distinguishes those capabilities.
