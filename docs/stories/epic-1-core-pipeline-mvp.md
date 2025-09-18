# Epic 1 — Core Pipeline MVP

Status: Done

## Epic Goal
Deliver an end-to-end cheque processing pipeline covering preflight, classification, field location, OCR, and parsing & normalization, ready for validation and routing. This establishes the backbone for human-in-the-loop review and downstream integrations.

## Description
Implements core pipeline components per architecture, prioritizing determinism and auditability.

- Preflight image processing (deskew, denoise, dewarp, contrast, orientation, blur rejection)
- Bank/template classification (MobileNetV3)
- Field locator (anchors for known templates; key-phrase/layout model fallback)
- OCR (PaddleOCR + MICR + multi-crop voting)
- Parsing & normalization (regex + finite-state grammar)

## Stories
1. 1.1 — Preflight processing
2. 1.2 — Bank & template classifier
3. 1.3 — Field locator (known + unknown templates)
4. 1.4 — OCR extraction (PaddleOCR + MICR)
5. 1.5 — Parsing & normalization

## Acceptance Criteria
- Core pipeline processes a cheque image to structured fields deterministically.
- Deterministic confidence computation per field.
- Unit/integration tests for each stage with golden samples.

## Dependencies
- Architecture shards in `docs/architecture/`
- PRD shards in `docs/prd/`

## Risks & Mitigations
- OCR variance → Multi-crop voting; controlled preflight.
- Template drift → Fallback to generic locator; quick template onboarding.

## Definition of Done
- Stories 1.1–1.5 completed with passing tests.
- Pipeline documented and demoed on golden samples.

## Change Log
| Date | Version | Description | Author |
|------|---------|-------------|--------|
| 2025-09-15 | 1.0.0 | Epic 1 MVP completed: Preflight, Classifier, Locator (FABMISR+QNB+fallback), OCR, Parsing. Amount-in-words deferred. Unknown-bank fallback available but not primary. | dev-agent |

