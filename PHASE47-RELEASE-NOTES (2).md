# ACE Canteen — Phase 47 release notes

## Delivered
- Admin-only `POST /api/admin/users` creates active staff or administrator accounts.
- Validates full name, email, role and a temporary password (12–128 characters).
- Rejects duplicate email addresses and rejects `student` role on this managed-account endpoint.
- Adds a Staff & permissions creation form to the existing admin management UI.
- Role/activation changes increment `token_version` to invalidate previously issued sessions.
- Account creation, role changes and activation changes are audited.
- Existing last-active-admin protections are preserved.
- No refund functionality was added.

## Run locally (Windows PowerShell)
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\start_local.ps1
```
Open `http://127.0.0.1:8000/` and sign in as an administrator. In Staff & permissions, enter the staff member's name, email, role, and a unique temporary password of at least 12 characters.

## Tests
Run `.\scripts\run_tests.ps1` from the `clg` root. Phase 47 verification in this build: **94 tests passed** using an isolated SQLite database.

## Operational notes
- Share temporary passwords out-of-band; never send them in a public channel.
- Staff should change the temporary password after first sign-in.
- This release does not implement forced first-login password rotation. If the deployment requires enforced rotation, that should be a dedicated follow-up with a database migration and authentication-flow enforcement.
