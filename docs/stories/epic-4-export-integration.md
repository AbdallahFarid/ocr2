# Epic 4 — Export & ERP/AP Integration

Status: Draft

## Epic Goal
Export validated cheque data to CSV/XLSX and integrate with ERP/AP systems via API with full auditability and reliability.

## Description
Covers file exports, database persistence, and API push with retries and error handling.

## Stories
1. 4.1 — CSV/XLSX Export with Schema Validation
2. 4.2 — Postgres Persistence and Audit JSON
3. 4.3 — ERP/AP API Push and Retry Logic

## Acceptance Criteria
- Exports match schema; ERP/AP endpoints receive correct data.
- Database persistence and audit trail complete and queryable.
- Retries and error logging implemented for integration.

## Dependencies
- Architecture: Export + Integration, Data Model
- PRD export and integration requirements

## Definition of Done
- Stories 4.1–4.3 complete; integration tested in staging with sample data.
