# Data Model (Core Tables)

## `cheque`
- id
- bank_id
- received_at
- image_path
- status
- stp (boolean)
- reviewer_id
- audit_json

## `cheque_fields`
- cheque_id (FK)
- name (field name)
- value (extracted)
- confidence (float)
- source_bbox (JSON)
- valid (boolean)

## `banks`
- id
- name
- template_meta (JSON)
- patterns

## `payees`
- id
- name_norm
- aliases

## `errors`
- cheque_id (FK)
- code
- details

