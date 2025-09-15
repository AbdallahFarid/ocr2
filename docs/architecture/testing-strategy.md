# Testing Strategy

This strategy defines the testing approach for achieving high confidence and auditability, aligned with the 100% accuracy requirement via validation/human-in-the-loop.

## Levels of Testing
- Unit tests (pytest): Core parsing, validation, and confidence logic.
- Property-based tests: Parsers and validators (e.g., amounts, dates) to explore edge cases.
- Integration tests: OCR pipeline and classifier integration with golden samples.
- API tests: FastAPI endpoint contract tests using TestClient.
- UI tests: Critical reviewer flows (keyboard shortcuts, low-confidence highlighting).

## Golden Datasets
- Maintain a small, redacted set of cheque images for regression.
- Store expected JSON outputs and field confidences for comparison.

## Test Requirements by Area
- Preflight: Deterministic image transforms given seed; blur rejection threshold behavior.
- Classifier: Stable top-1 accuracy on labeled bank samples.
- Locator: Correct bbox extraction for known templates; fallback path verified.
- OCR: Reproducible outputs for crops; MICR model verified where present.
- Parsing: Deterministic regex/grammar; amount-in-words vs numeric cross-checks.
- Validation: All business rules enforced with machine-readable error codes.
- Routing: Threshold logic directs cases to auto-approve vs review paths.

## Coverage Targets
- ≥ 85% for parsing and validation modules.
- Critical path modules must have tests before merging.

## References
- [Source: architecture/components.md]
- [Source: architecture/coding-standards.md]
- [Source: architecture/tech-stack.md]
