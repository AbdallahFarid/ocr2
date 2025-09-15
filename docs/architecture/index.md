# System Architecture: Cheque Processing Platform

## Table of Contents

- [System Architecture: Cheque Processing Platform](#table-of-contents)
  - [Overview](./overview.md)
  - [Components](./components.md)
    - [1. Capture + Preflight](./components.md#1-capture-preflight)
    - [2. Bank / Template Classifier](./components.md#2-bank-template-classifier)
    - [3. Field Locator](./components.md#3-field-locator)
    - [4. OCR](./components.md#4-ocr)
    - [5. Parsing + Normalization](./components.md#5-parsing-normalization)
    - [6. Validation Gates](./components.md#6-validation-gates)
    - [7. Confidence + Routing](./components.md#7-confidence-routing)
    - [8. Human-in-the-Loop UI](./components.md#8-human-in-the-loop-ui)
    - [9. Export + Integration](./components.md#9-export-integration)
    - [10. Monitoring](./components.md#10-monitoring)
  - [Tech Stack](./tech-stack.md)
  - [Data Model (Core Tables)](./data-model-core-tables.md)
    - [cheque](./data-model-core-tables.md#cheque)
    - [cheque_fields](./data-model-core-tables.md#cheque_fields)
    - [banks](./data-model-core-tables.md#banks)
    - [payees](./data-model-core-tables.md#payees)
    - [errors](./data-model-core-tables.md#errors)
