# Epic 2 — Validation & Routing

Status: Draft

## Epic Goal
Enforce deterministic validation gates and confidence-based routing to achieve high straight-through-processing (STP) while guaranteeing correctness via human-in-the-loop when needed.

## Description
Implements validation rules, confidence calculation, and routing with full auditability:
- Validation gates for dates, amounts, cheque numbers, payee, currency.
- Field-level confidence calculation and thresholds.
- Auto-approve vs human-review routing and structured logging of decisions.

## Stories
1. 2.1 — Validation Gates (dates, amounts, cheque numbers, payee, currency)
2. 2.2 — Confidence Calculation and Thresholding
3. 2.3 — Auto-approve vs Human Review Routing + Logging

## Acceptance Criteria
- All listed validation gates implemented with machine-readable error codes.
- Confidence calculation and global thresholding implemented.
- Routing decisions recorded with reason codes; deterministic and test-covered.

## Dependencies
- Architecture shards in `docs/architecture/` (Components, Data Model)
- PRD shards in `docs/prd/`

## Risks & Mitigations
- Over-rejection due to strict thresholds → Calibrate thresholds and use review routing.

## Definition of Done
- Stories 2.1–2.3 completed with passing tests and end-to-end demo on golden samples.
