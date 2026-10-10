# SSA annual wage-file adapter — 0.5.0

`government_submission.py` generates a **restricted 2026 SSA EFW2 wage file**. It writes 512-byte RA/RE/RW/RT/RF records, required domestic identity/address/contact fields, annual monetary fields, reconciled employer/file totals, optional zero fields and the 2026 optional signature-PIN/Luhn format. It refuses unknown fields, unsupported scope, invalid/duplicate identifiers, amounts exceeding field widths and the 2026 Social Security cap, controls/non-ASCII text and truncation. Private file creation is exclusive: an existing export is never overwritten.

This is an original domestic regular-employment wage-file adapter with **no optional W-2 amounts**. It does not cover state/local returns, territories/foreign addresses, agents, corrections, tips, pension/benefit boxes or special employment. It consumes independently reviewed **annual** data; monthly pay-run workpapers must not be substituted for annual W-2 totals. Employer and submitter registrations, software/preparer classifications and email ownership must be reviewed separately.

Input must be a private 0600 JSON file. Use a new output inside a private 0700 folder:

```sh
.venv/bin/python government_submission.py \
  --input /private/reviewed-annual-2026.json \
  --output /private/filing-export/EFW2-2026.txt
```

See `tests/test_government_submission.py::fixture` for the exact input structure using fictional records. The root fields are `tax_year`, three explicit applicability/review confirmations, `submitter`, `employer` and `employees`. Replace every fictional identifier with authorized reviewed information. The test fixture is not a submission example to send to SSA. Outputs contain SSNs and may contain an employer signature PIN: keep them in private encrypted local storage, never in an ordinary cloud-synced folder, source release or public report. The CLI prints only counts/hash/status, not identifiers or PINs.

The adapter performs **no online submission** and keeps `authority_accepted: false`. Independently check the file against [SSA's 2026 specification](https://www.ssa.gov/employer/efw/26efw2.pdf), validate through [AccuWage Online](https://www.ssa.gov/employer/accuwage/index.html) with the employer's authorized BSO account, then use BSO's upload/status facilities and retain the receipt separately. Local unit checks do not constitute AccuWage acceptance, identity validation or government filing approval.

As checked on 9 October 2026, SSA states that new Electronic Wage Reporting Web Service users/consolidators are not currently accepted; BSO upload and W-2 Online remain available. [Official EWRWS status](https://www.ssa.gov/employer/EWRWS.htm). No government account or authority sandbox credentials were available, and no employer's legal submission or attestation was made during testing.

Other authorities require their own schemas, registrations, signing/transport mechanisms, conformance datasets and live/sandbox acceptance. They remain unimplemented; a provider-neutral workpaper or this US-specific adapter must not be labelled a universal government submission system.
