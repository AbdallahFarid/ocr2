# Product Requirements Document (PRD)

## 1. Goals & Background Context
The goal of this project is to build an automated cheque processing platform that digitizes, extracts, validates, and integrates cheque data into enterprise financial systems. Current manual cheque processing is error-prone, time-consuming, and costly. This system aims to reduce manual effort, improve accuracy, increase straight-through-processing (STP) rates, and provide a robust human-in-the-loop fallback for exceptional cases.

Key drivers:
- Reduce cheque processing time from days to minutes.
- Improve accuracy to >99.5% on key fields.
- Minimize operational costs by automating repetitive tasks.
- Ensure compliance with banking and business rules.

## 2. Requirements

### Functional Requirements
1. **Image Capture & Preprocessing**
   - Support flatbed and ADF scanners (≥300 dpi).
   - Auto-deskew, denoise, dewarp, contrast adjust, orientation fix.
   - Reject blurry scans (Laplacian variance threshold).

2. **Bank & Template Classification**
   - CNN (MobileNetV3) classifier for bank logos and headers.
   - Route to template-based parsing; fallback to generic layout parsing.

3. **Field Detection**
   - Known templates: anchor-based bounding boxes with perspective correction.
   - Unknown templates: key-phrase detection (Arabic/English) and layout model (Detectron2/YOLOv8).

4. **OCR Extraction**
   - Use PaddleOCR (Arabic + Latin + digits).
   - Specialized MICR recognition with E-13B/Courier.
   - Multi-crop voting for high confidence.

5. **Parsing & Normalization**
   - Deterministic regex and finite-state grammars.
   - Parse dates, amounts, cheque numbers, IBAN, names.
   - Amount-in-words (Arabic + English) cross-matched to numeric.

6. **Validation Rules**
   - Date plausibility checks.
   - Amount thresholds (non-zero, within limits).
   - Cheque number formats per bank.
   - Payee validation against vendor master list with fuzzy matching.
   - Allowed currency checks.

7. **Confidence & Routing**
   - Calculate field-level confidence (OCR × locator × parse).
   - Auto-approve if all required fields exceed threshold (≥0.995).
   - Route to human review otherwise.

8. **Human-in-the-Loop Review**
   - Reviewer console with side-by-side cheque + extracted fields.
   - Hotkey corrections.
   - Corrections update templates and training datasets.

9. **Integration & Export**
   - Export to CSV/XLSX.
   - Store structured results in Postgres.
   - Push validated records to ERP/AP system via API.
   - Maintain audit trail with images, JSON, and corrections.

10. **Monitoring & Reporting**
    - Dashboards for STP rate, error rates per bank, top failure reasons, reviewer throughput.
    - Grafana/Metabase integration.

### Non-Functional Requirements
- **Performance**: Handle 1,000+ cheques/day on CPU; GPU optional.
- **Reliability**: >99.9% system uptime.
- **Scalability**: Support multi-bank deployments.
- **Security**: On-prem deployment; encrypted storage & API communication.
- **Usability**: Reviewer console with intuitive, minimal UI.

## 3. User Interface Design Goals
- **Simplicity**: Side-by-side comparison with minimal clicks.
- **Speed**: Keyboard shortcuts for corrections.
- **Clarity**: Highlight low-confidence fields for quick identification.
- **Adaptability**: Reviewer corrections feed into active learning.
- **Accessibility**: Support Arabic + English reviewers.

## 4. Success Metrics
- **STP Rate**: ≥80% cheques auto-approved without human intervention.
- **Accuracy**: ≥99.5% field-level accuracy on validated cheques.
- **Reviewer Efficiency**: <30 seconds average correction time per cheque.
- **Integration Reliability**: 100% of approved cheques exported to ERP/AP without errors.
- **Error Reduction**: ≥50% decrease in cheque-related processing errors compared to manual entry.

## 5. Risks & Mitigations
- **OCR Accuracy in Arabic**: Mitigation via PaddleOCR fine-tuning + multi-crop voting.
- **Template Drift (new bank formats)**: Mitigation via fallback generic parsing + quick template onboarding.
- **Blurry/Low-quality Scans**: Mitigation via preflight checks and scan rejection.
- **Reviewer Fatigue**: Mitigation via hotkeys, minimal UI, dashboards for workload distribution.
- **Integration Failures**: Mitigation via retries, error logging, monitoring.

## 6. Dependencies
- Hardware: Flatbed/ADF scanners.
- Software Libraries: OpenCV, PaddleOCR, layoutparser, Detectron2/YOLOv8, RapidFuzz, python-bidi, arabic-reshaper.
- Backend: FastAPI, Celery, Redis, Postgres.
- Frontend: React + shadcn/ui.
- Infrastructure: Docker (CPU baseline, GPU optional).

## 7. Out of Scope
- Cheque fraud detection (future phase).
- Cross-bank settlement systems.
- Mobile cheque deposit app.
- Multi-currency FX reconciliation.

## 8. Timeline (High-Level)
1. **Month 1–2**: Core pipeline (capture, preflight, OCR, parsing).
2. **Month 3**: Validation rules + human-in-the-loop console.
3. **Month 4**: ERP/AP integration + dashboards.
4. **Month 5**: Bank-specific template expansion.
5. **Month 6**: Pilot with selected banks/vendors.

## 9. Acceptance Criteria
- Process ≥1,000 cheques/day on CPU-only deployment.
- ≥80% STP cheques auto-approved.
- Reviewer console enables correction in <30s.
- All exports validated against ERP/AP API with zero data loss.
- System audit trail complete and queryable.

