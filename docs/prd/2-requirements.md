# 2. Requirements

## Functional Requirements
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

## Non-Functional Requirements
- **Performance**: Handle 1,000+ cheques/day on CPU; GPU optional.
- **Reliability**: >99.9% system uptime.
- **Scalability**: Support multi-bank deployments.
- **Security**: On-prem deployment; encrypted storage & API communication.
- **Usability**: Reviewer console with intuitive, minimal UI.
