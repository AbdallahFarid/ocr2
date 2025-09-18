# Epic 3 — Human-in-the-Loop (HITL) Reviewer UI

Status: Done

## Epic Goal
Provide a fast, low-friction reviewer experience to correct low-confidence fields and feed improvements back into templates and training datasets.

## Description
Implements a reviewer console with side-by-side cheque image and extracted fields, keyboard shortcuts, and correction workflow with audit trail updates.

## Stories
1. 3.1 — Reviewer Console Shell (layout and data wiring)
2. 3.2 — Keyboard Shortcuts and Low-confidence Highlighting
3. 3.3 — Correction Workflow + Template/Dataset Update

## Acceptance Criteria
- Reviewer can view cheque and fields side-by-side and navigate efficiently.
- Low-confidence fields highlighted; keyboard-only operation supported.
- Corrections are persisted and reflected in audit trail; updates feed template/dataset.

## Dependencies
- Architecture Components (Human-in-the-Loop UI)
- PRD UI goals and non-functional requirements

## Definition of Done
- Stories 3.1–3.3 completed with usability validated by pilot reviewers.
- Corrections persisted to audit JSON and appended to CSV queue for template/dataset updates.
