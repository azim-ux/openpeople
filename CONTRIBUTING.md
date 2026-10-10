# Contributing

Use Python 3.12+ and install the pinned dependencies in `requirements.txt` or `uv.lock`. Keep local operation available without an external service. New dependencies should have a clear purpose and maintained upstream.

1. Describe the user workflow and its authorization requirements.
2. Add regression tests for validation and access boundaries before changing the API.
3. Implement the smallest complete workflow, including visible errors and empty states.
4. Run `.venv/bin/python -m unittest discover -s tests -v`, `node tests/test_frontend.mjs`, and syntax checks for both JavaScript files. Use `.venv/bin/python tests/run_coverage.py` for backend coverage.
5. Check the affected desktop/mobile screen and update the README if scope changes.

Never commit databases, employee records, passwords, session tokens, or environment secrets. Keep sample data fictional. Changes to persisted schema need explicit migration handling; `CREATE TABLE IF NOT EXISTS` does not migrate existing tables.

Use the allowlisted `scripts/package_public.py` export to prepare a public source tree; it excludes local operational evidence and private logs. The GitHub workflow checks backend coverage, frontend regressions and both source packages. No personal email or application administrator is needed to contribute source. The macOS protected browser/service drills require the separately reviewed tools described in the testing guide; hosted CI does not imply those external acceptance checks passed.

## Code conventions

- Parameterize SQL values and keep table/column identifiers on server-controlled allowlists.
- Enforce authorization in the API, regardless of what navigation the UI displays.
- Escape text before including it in HTML. Keep scripts and styles in separate files for the content security policy.
- Store currency in integer minor units where transactions are involved.
- Use meaningful tests of real workflows and failure conditions.
