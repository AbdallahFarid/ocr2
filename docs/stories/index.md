# Stories Index

Tracks epics and stories for the Cheque Processing Platform.

## Epics
- [Epic 1 — Core Pipeline MVP](./epic-1-core-pipeline-mvp.md) — Status: Draft
- [Epic 2 — Validation & Routing](./epic-2-validation-routing.md) — Status: Draft
- [Epic 3 — Human-in-the-Loop (HITL) Reviewer UI](./epic-3-hitl-ui.md) — Status: Draft
- [Epic 4 — Export & ERP/AP Integration](./epic-4-export-integration.md) — Status: Draft
- [Epic 5 — Monitoring & Reporting](./epic-5-monitoring-reporting.md) — Status: Draft

## Stories (Epic 1)
- [1.1 — Preflight Processing](./1.1.story.md) — Status: Draft
- [1.2 — Bank & Template Classifier](./1.2.story.md) — Status: Draft
- [1.3 — Field Locator (Known + Unknown Templates)](./1.3.story.md) — Status: Draft
- [1.4 — OCR Extraction (PaddleOCR + MICR)](./1.4.story.md) — Status: Draft
- [1.5 — Parsing & Normalization](./1.5.story.md) — Status: Draft

## Stories (Epic 2)
- [2.1 — Validation Gates](./2.1.story.md) — Status: Draft
- [2.2 — Confidence Calculation and Thresholding](./2.2.story.md) — Status: Draft
- [2.3 — Auto-approve vs Human Review Routing + Logging](./2.3.story.md) — Status: Draft

## Stories (Epic 3)
- [3.1 — Reviewer Console Shell (Layout and Data Wiring)](./3.1.story.md) — Status: Draft
- [3.2 — Keyboard Shortcuts and Low-confidence Highlighting](./3.2.story.md) — Status: Draft
- [3.3 — Correction Workflow + Template/Dataset Update](./3.3.story.md) — Status: Draft

## Stories (Epic 4)
- [4.1 — CSV/XLSX Export with Schema Validation](./4.1.story.md) — Status: Draft
- [4.2 — Postgres Persistence and Audit JSON](./4.2.story.md) — Status: Draft
- [4.3 — ERP/AP API Push and Retry Logic](./4.3.story.md) — Status: Draft

## Stories (Epic 5)
- [5.1 — STP/Error Dashboards](./5.1.story.md) — Status: Draft
- [5.2 — Failure Reasons and Reviewer Throughput](./5.2.story.md) — Status: Draft
- [5.3 — Alerting and Log Aggregation](./5.3.story.md) — Status: Draft

## Notes
- Stories reference architecture shards under `docs/architecture/` and follow conventions in `coding-standards.md`, `unified-project-structure.md`, and `testing-strategy.md`.
- Use `create-next-story` workflow to sequence additional stories or start the next epic when ready.
