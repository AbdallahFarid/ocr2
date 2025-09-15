# Components

## 1. Capture + Preflight
- **Input Sources**: Flatbed scanner, ADF scanner, or file ingestion (watch folder, SFTP, optional scanner SDK).
- **Requirements**: Minimum 300 dpi resolution.
- **Preprocessing (OpenCV)**:
  - Auto-deskew
  - Denoise
  - Dewarp
  - Contrast enhancement
  - Orientation correction
  - Blurry image rejection (Laplacian variance threshold)

## 2. Bank / Template Classifier
- **Model**: CNN (MobileNetV3) trained on bank logos and header features.
- **Routing**: Classifies cheque to specific bank template.
- **Fallback**: Unknown banks go to generic layout parsing.

## 3. Field Locator
- **Known Templates**:
  - Predefined anchor-based bounding boxes (x,y,w,h) per bank.
  - Perspective correction applied to anchors.
- **Unknown Templates**:
  - Key-phrase search in Arabic/English (e.g., "Date/التاريخ", "Amount/المبلغ").
  - Layout model using layoutparser + Detectron2 or YOLOv8 for label→value detection.

## 4. OCR
- **Engine**: PaddleOCR (Arabic, Latin, digits).
- **Specialized Models**:
  - MICR line with E-13B / Courier models if present.
- **Post-Processing**:
  - Multi-crop voting strategy to increase confidence.

## 5. Parsing + Normalization
- **Techniques**: Deterministic parsers only (regex + finite-state grammar).
- **Fields Extracted**:
  - Dates, amounts, cheque numbers, IBAN, payee names.
- **Special Parsing**:
  - Amount-in-words (Arabic + English) → numeric value.
  - Cross-match between words and numeric box.

## 6. Validation Gates
- Date: Must be within plausible range.
- Amount: >0 and within business thresholds.
- Cheque number: Valid length/pattern per bank.
- Payee: Must match vendor/payee master list or fuzzy-match above threshold (RapidFuzz).
- Currency: Must be in allowed set.

## 7. Confidence + Routing
- **Confidence Calculation**: Field confidence = OCR confidence × locator confidence × parse pass.
- **Routing Logic**:
  - If all required fields ≥ threshold (e.g., 0.995) and validations pass → auto-approve.
  - Else → route to human review.
- **Logging**: Record reasons for rejection.

## 8. Human-in-the-Loop UI
- **Frontend**: React + shadcn/ui.
- **UI Features**:
  - Side-by-side display of cheque image and extracted fields.
  - Hotkey-based correction.
  - Corrections update template library and active learning datasets.

## 9. Export + Integration
- **Formats**: CSV, XLSX.
- **Storage**: Postgres database.
- **Integration**: Push to ERP/AP system via API.
- **Audit Trail**: Store image, extracted JSON, confidences, and correction history.

## 10. Monitoring
- **Dashboards**:
  - STP rate tracking.
  - Per-bank error rate.
  - Top failure reasons.
  - Reviewer throughput.
- **Stack**: Grafana/Metabase dashboards.
