# Smoke report format

The real-Windows smoke report is a manually completed JSON artifact generated with:

```bat
python tools/smoke_report.py --init smoke-report.json
```

## Matrix identity

The report uses `schema_version: 3` and includes `matrix_fingerprint`.

`matrix_fingerprint` is a SHA-256 digest of the current smoke-case definitions:
case ID, area, title, application labels, priority, and destructive flag.
It deliberately excludes test notes, timestamps, environment details, and
results.

This prevents a report produced from an older smoke matrix from silently
passing validation after the matrix has changed. `python tools/smoke_report.py
--validate ...` must see the fingerprint for the current matrix.

## Result states

Each case records exactly one of:

- `PENDING` — not yet exercised on the real desktop.
- `PASS` — the expected behavior was observed.
- `FAIL` — the expected behavior was not observed.
- `BLOCKED` — the test could not be safely exercised in the environment.

`notes` may contain human test notes. Validation and summary code never reads
those notes to decide whether a case passed.

Every completed (`PASS`, `FAIL`, or `BLOCKED`) case must also contain a non-empty
`tested_at` execution timestamp. Pending cases leave `tested_at` empty.

## Release gate

A complete release report must also contain a Windows environment snapshot and
an exact 40-character Git commit SHA in `environment.source_commit`.
Every completed case must include its `tested_at` execution timestamp.
The release workflow separately checks that the smoke-report source commit is
present in the release workspace and is an ancestor of the tagged release.

The smoke report contains no window titles, conversation names, message text,
input values, clipboard contents, or credentials.
