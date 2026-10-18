# Phase 46 — Admin governance and audit investigation

## Included

- Prevents demoting or disabling the last active administrator. Promote/activate another admin first to avoid locking the installation out of administrative control.
- Adds audit-history filters for actor user ID and entity ID, alongside action and entity type filters.
- Adds regression tests and keeps changes backward-compatible with the existing admin UI and API.

## API

`GET /api/admin/audit-events?action=user.role_changed&entity_type=user&actor_user_id=12&entity_id=45&limit=100&offset=0`

All audit-history access remains admin-only. No password hashes, payment signatures, or gateway secrets are returned by the audit endpoint. No refund workflow is included.

## Validation

Run `.scripts\run_tests.ps1` on Windows or `PYTHONPATH=backend python -m pytest backend/tests -q` from the project root.
