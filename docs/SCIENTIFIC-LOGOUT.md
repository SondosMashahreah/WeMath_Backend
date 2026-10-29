# Scientific student logout verification

Base commit: `1676aff1b25d5d0535d52f66d2cf4f48ced5ce97`.

The account/back-navigation failure is a frontend redirect bug. The existing backend
logout endpoint already revokes the token correctly. This patch adds regression tests
only; it does not alter production API behavior or require database migrations.

`tests/test_scientific_logout.py` checks both grades 11 and 12 with the scientific track:
registration, restored profile, 204 logout, rejection of the old token, and successful
fresh login without reviving the old token.

Validation: `python -m pytest -q` — 25 passed, using isolated SQLite test databases.
