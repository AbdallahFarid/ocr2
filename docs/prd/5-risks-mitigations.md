# 5. Risks & Mitigations
- **OCR Accuracy in Arabic**: Mitigation via PaddleOCR fine-tuning + multi-crop voting.
- **Template Drift (new bank formats)**: Mitigation via fallback generic parsing + quick template onboarding.
- **Blurry/Low-quality Scans**: Mitigation via preflight checks and scan rejection.
- **Reviewer Fatigue**: Mitigation via hotkeys, minimal UI, dashboards for workload distribution.
- **Integration Failures**: Mitigation via retries, error logging, monitoring.
