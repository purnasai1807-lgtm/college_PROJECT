# Phase 19 — Campus pilot validation

This phase adds repeatable smoke checks for the public student entry point, API health/readiness, catalogue data, direct-order protections, and staff-only feedback summaries. It also documents a staged pilot checklist. These checks are not a substitute for a browser-driven end-to-end test or a live payment test.

## Student-friendly pilot checklist

1. Use a staging environment and Razorpay test credentials; never test with student payment details.
2. Create separate student and staff accounts and verify role boundaries.
3. Check the app on a narrow mobile viewport and desktop; verify keyboard focus, labels, readable errors, and empty states.
4. Complete a test order, follow it through kitchen status transitions, and verify the pickup token.
5. Test payment pending, failed, duplicate webhook, delayed webhook, and browser refresh scenarios.
6. Verify stock cannot be oversold with simultaneous orders and that staff stock adjustments appear in the inventory ledger.
7. Confirm the no-refunds policy is displayed before payment and that no refund workflow is exposed. Payment errors/duplicate charges still require support investigation.
8. Test database backup restoration in staging before any real launch.
9. Obtain canteen staff and a small group of student testers' sign-off before expanding access.

## Run checks

From the project root in PowerShell:

```powershell
$env:PYTHONPATH = "backend"
python -m pytest backend/tests -q
node --check frontend/js/app.js
```

## Launch gate

Do not call the app production-ready until browser end-to-end tests, real staging payment verification, load/concurrency tests, restore drills, accessibility review, and deployment security review have been completed. Refund functionality remains intentionally out of scope per the project's no-refunds requirement.
