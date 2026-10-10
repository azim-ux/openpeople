# Country payroll options and integration contract

Research date: 9 October 2026. OpenPeople uses original code and UI. It is not a Workday product or a certified Workday integration.

Workday's current public country guides list Australia, Canada, France, Ireland, the United Kingdom and the United States. Its global product page advertises partner integrations for more than 180 countries. Native calculation and partner coverage are different capabilities; neither is a universal table of tax rates. [Country payroll guides](https://doc.workday.com/admin-guide/en-us/payroll/payroll.html), [global integrations](https://www.workday.com/en-us/products/payroll/global-payroll.html).

OpenPeople already offers 251 country/region profiles for HR, currency and timezone. This release adds planning guidance for all six documented native Workday payroll countries and a provider-neutral external-results workflow for the existing country profiles. It does not embed, license, reverse engineer or certify Workday's tax engines. A list of Workday partner countries is not evidence that OpenPeople has a tested connector for each country.

## Implemented options

| Option | OpenPeople behavior |
| --- | --- |
| Manual reviewed payroll | Monthly gross estimate from effective salary, joining/exit dates and approved unpaid leave; peer-entered deductions; independent finalization |
| Externally calculated payroll | Employer groups with weekly/fortnightly/semimonthly/monthly dated periods and bonuses/adjustments; record reviewed gross components, employee deductions, separate employer contributions, net pay, provider/reference/jurisdiction and rules effective date |
| Dated partial calculation | US 2026 federal periodic withholding/FICA and UK 2026/27 ordinary Class 1 NI previews; other obligations excluded and independent review required |
| Complete automatic statutory payroll | Unavailable; complete country capability remains explicitly false |
| Filing workpapers | Employer-scoped immutable review packet, peer approval and external receipt tracking; not agency submission |
| Agency-format file export | Restricted 2026 SSA EFW2 annual wage file from reviewed domestic ordinary data; no optional amounts; AccuWage/BSO acceptance pending |
| Online government filing and payments | Unavailable; performed by the employer's reviewed provider or official service |

The external-results option follows the general integration pattern described in Workday's [global deployment guidance](https://doc.workday.com/admin-guide/en-us/payroll/payroll-considerations/dwn1595352231356.html.html): externally computed results are brought into the HR workspace for review. OpenPeople's format is its own; no vendor adapter, certification or live provider connection is claimed.

## Country implementation checklist

The following are areas to validate with a qualified payroll provider. They are not complete legal requirements, executable calculations or a promise of compliance. Employer registration, worker classification, tax year, regional rules, benefits, accumulated balances and statutory reporting vary by deployment. This checklist itself has no numeric rates. The separately scoped [US federal and UK NI partial packs](STATUTORY_AND_FILINGS.md) contain dated calculation rules; the [SSA file adapter](GOVERNMENT_SUBMISSION.md) has its own restricted input and acceptance requirements.

| Country | Review areas | Primary guidance |
| --- | --- | --- |
| Australia | PAYG withholding, superannuation, STP reporting | [ATO developer guidance](https://softwaredevelopers.ato.gov.au/STP) |
| Canada | Income tax, CPP/QPP, EI, province-specific rules, year-end reporting | [CRA employer guide](https://www.canada.ca/en/revenue-agency/services/forms-publications/publications/t4001/employers-guide-payroll-deductions-remittances.html) |
| France | Employee/employer contributions, DSN and withholding configuration | [Urssaf DSN guidance](https://www.urssaf.fr/accueil/employeur/gerer-entreprise/declaration-sociale-nominative.html) |
| Ireland | Revenue notifications and payroll submissions, PAYE/USC/PRSI and pension configuration | [Revenue employer obligations](https://www.revenue.ie/en/employing-people/becoming-an-employer-and-ongoing-obligations/employer-obligations-from-01-01-2019/index.aspx) |
| United Kingdom | PAYE, National Insurance, statutory pay, FPS/EPS and pension configuration | [HMRC payroll guide](https://www.gov.uk/running-payroll) |
| United States | Federal withholding, Social Security/Medicare, state/local rules and year-end forms | [IRS employer tax guide](https://www.irs.gov/publications/p15) |

Workday's country guides additionally describe statutory payments, country reporting and pension features; these remain implementation targets here. The public overview is not an exhaustive specification of a licensed customer's tenant or layout.

## Record an external result

1. Create and open a draft under **Pay runs**. A colleague must handle your own statement.
2. Select **Import reviewed result** for the employee. Download the JSON template if your provider needs the contract, then paste the completed result. Treat exports as confidential payroll records; the download goes to the user's browser download location.
3. Fill in the provider, result reference, rules effective date and review note. Use integer minor units: USD/INR use cents/paise, JPY uses whole yen, and three-decimal currencies use thousandths. Negative and fractional component amounts are not supported by this version.
4. The server checks the employee/month/country/currency, component shapes and bounds, and gross minus employee deductions equals net. Employer contributions remain separate. These are structural/arithmetic checks, not verification of a tax calculation.
5. Another HR/payroll colleague who neither created nor edited the run reopens it, checks the latest components and finalizes. Finalized results are locked. Employees see only their own finalized statements and recorded components.

The request is a PATCH to `/api/pay_results/<id>` with exactly `expected_version` and `external_result`. Legacy monthly results use `openpeople.external-payroll.v1`; dated group results use version 2 and bind the exact immutable period object. Every dated worker requires a reviewed result before finalization; use the template returned by `GET /api/pay_runs/<id>` rather than inventing IDs. A changed run returns 409; missing version returns 428. Browser saves use an idempotency key, preserving successful submissions if refresh fails. Existing externally calculated statements must be revised with another reviewed result, keeping the component breakdown consistent.

Every successful import increments the run version, permanently records the importing editor for that draft, and audits before/after values. A finalizer cannot be the creator or any editor. Import provenance, component amounts and editor exclusions survive encrypted backup restoration. No external service is contacted during an import.

## Work remaining for statutory payroll

Each jurisdiction needs an effective-dated rule implementation, legally reviewed test cases and ongoing updates. Required capabilities include registration, regional tax fields, pay groups/calendars, cumulative and retrospective calculations, year-end corrections, filing schemas/certificates, bank/accounting reconciliation, failure handling and provider acceptance. [Dated pay groups](PAY_PERIODS.md) now support employer-scoped regular periods and reviewed bonus/adjustment runs alongside legacy monthly snapshots. Automatic calendars, cumulative/retro reconciliation and consolidated currency conversion remain unavailable. Calendar-prorated draft salary is an estimate; complete externally reviewed results are required for every dated worker.

An enterprise payroll claim requires evidence for each supported jurisdiction and provider. A country selector, imported calculation or passing security tests does not establish that evidence.
