# Phase 6 Release Decision Report

**Date:** 2026-10-27
**Branch:** master
**Baseline commit:** 12928ab
**Test suite:** 253/253 pass (195s)

---

## 1. Baseline Verification

| Metric | Result |
|--------|--------|
| Test suite at start | 239/239 pass |
| Working tree | Clean |
| Commit | 12928ab on master |

## 2. Risk-Based Audit Findings

Four areas audited; three confirmed defects, one noted (no code change needed):

| # | Area | Severity | Status |
|---|------|----------|--------|
| 1 | Import partial-failure atomicity | High | Fixed |
| 2 | Email validation weakness | Medium | Fixed |
| 3 | Silent negative-amount handling | Low | Fixed |
| 4 | SECRET_KEY not used cryptographically | Info | Documented (Streamlit limitation) |

## 3. Fixes Applied

### Fix 1: Import savepoint atomicity (`src/importer.py`)
**Problem:** `run_import` re-raised exceptions after the outer `except` block, causing
`get_db()` to commit partial transactions alongside a "failed" import record.
**Fix:** Wrapped transaction insertion in `db.begin_nested()` savepoint. On failure, the
savepoint rolls back all inserted rows while the import record survives with `status="failed"`.
The outer except no longer re-raises.
**Tests:** `test_import_failure_does_not_leave_partial_transactions`,
`test_import_success_commits_all_transactions`

### Fix 2: Email validation (`src/auth.py`)
**Problem:** `"@" not in email` accepted emails like `user@domain` (no TLD).
**Fix:** Replaced with `re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email)`.
**Tests:** `test_register_rejects_email_without_domain`,
`test_register_rejects_email_without_tld`, `test_register_accepts_valid_email`,
`test_register_rejects_empty_email`, `test_register_rejects_email_with_spaces`

### Fix 3: Negative amount warning (`src/importer.py`)
**Problem:** Negative amounts in imports were skipped with a generic "invalid date or amount"
warning, giving users no guidance.
**Fix:** Added a `negative_count` tracker with a specific warning message explaining that
amounts must be positive and the type column indicates direction.
**Tests:** `test_negative_amounts_skipped_with_specific_warning`, `test_parse_amount_negative`

## 4. Regression Tests Added

14 new tests in `tests/test_phase6.py`:
- Import savepoint rollback (failure + success paths)
- Negative amount handling
- Email validation (5 cases: no domain, no TLD, valid, empty, spaces)
- Empty user experience (new user has zero transactions)
- Analytics on empty DataFrame
- Anomaly detection on empty DataFrame
- Period comparison edge cases (no prior data, zero income)

**Total suite: 253/253 pass.**

## 5. Browser E2E Verification

| Workflow | Result |
|----------|--------|
| Register new user | PASS |
| Email validation rejects invalid email | PASS |
| Login and access protected pages | PASS |
| Import CSV (93 rows via service layer) | PASS |
| Overview dashboard (KPIs, charts, INR formatting) | PASS |
| Transaction filters, sort, pagination | PASS |
| Anomalies page (11 flagged, 3 detection methods) | PASS |
| Insights page (6 data-backed insights) | PASS |
| AI Assistant (query, deterministic summary, charts) | PASS |
| Logout clears protected content | PASS |
| Cross-user isolation (user2 sees zero transactions) | PASS |
| Invalid file upload | NOT TESTED (Streamlit file widget limitation in automated browser) |
| Follow-up questions / clear history | PARTIALLY TESTED (conversation history tracked, 2 queries) |
| Restart persistence | NOT TESTED (would require server restart mid-session) |

**Note:** File upload was tested via the service layer (`run_import`) rather than the
Streamlit file upload widget, which does not accept programmatic file injection reliably.
The import pipeline itself is thoroughly unit-tested (14 tests in `test_importer.py` +
regression tests in `test_phase6.py`).

## 6. Database & Migration Readiness

| Check | Result |
|-------|--------|
| Schema matches models | PASS |
| Alembic version current (d1b0c82c90a1) | PASS |
| Fresh DB init from models | PASS |
| Foreign keys defined | PASS |
| WAL mode enabled | PASS |
| Composite indexes present | PASS |
| Unique constraints (username, email) | PASS |

## 7. Deployment & Operational Review

| Check | Result |
|-------|--------|
| `.env` not committed | PASS |
| `.gitignore` covers .env, *.db, __pycache__, .claude/ | PASS |
| SECRET_KEY validated (refuses default in production) | PASS |
| XSRF protection enabled | PASS |
| Structured logging with configurable level | PASS |
| Dependencies pinned with minimum versions | PASS |
| No paid APIs required (deterministic fallback) | PASS |

## 8. Documentation

- README updated: test count (253), Phase 6 test file listed, import atomicity and email
  validation descriptions updated.

## 9. Changed Files

```
 README.md            | 18 +++++++++++-------  (documentation updates)
 src/auth.py          |  2 ++-                  (email validation regex)
 src/importer.py      | 50 ++++++++++++++++++++  (savepoint + negative warning)
 tests/test_phase6.py | NEW (246 lines)         (14 regression tests)
```

## 10. Security Checklist

- [x] No secrets in diff
- [x] No database files in diff
- [x] No `.env` files committed
- [x] XSS protection maintained (html.escape on user data)
- [x] User isolation enforced at service layer
- [x] Rate limiting functional
- [x] Session expiry functional
- [x] No real bank credentials requested or collected

## 11. Known Limitations (Unchanged)

- Streamlit session management (no HTTP-only cookies)
- Rate limiting is in-memory (resets on restart)
- SECRET_KEY is not used cryptographically (Streamlit limitation)
- Single-currency (INR) demo scope
- PostgreSQL production path not verified locally

## 12. Items NOT Changed

Per the operating rules, no existing behavior was modified beyond the three targeted fixes.
No tests were weakened or removed. No features were added beyond what the audit identified.

## 13. Release Recommendation

**CONDITIONAL GO** — The application is ready for review and commit.

All confirmed defects are fixed with regression tests. The test suite passes completely
(253/253). Browser verification covers the critical paths. Three browser workflows could
not be fully automated (file upload widget, restart persistence, and exhaustive follow-up
testing) but are covered by unit tests.

**Awaiting user approval to commit.**
