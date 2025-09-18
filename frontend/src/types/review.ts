export type ValidationInfo = {
  ok: boolean
  code?: string
}

export type FieldRecord = {
  field_conf: number
  loc_conf?: number
  ocr_conf?: number
  parse_ok?: boolean
  parse_norm?: string
  ocr_text?: string
  ocr_lang?: string
  meets_threshold?: boolean
  validation?: ValidationInfo
}

export type Decision = {
  decision: 'auto_approve' | 'review'
  stp: boolean
  overall_conf: number
  low_conf_fields: string[]
  reasons: string[]
}

export type ReviewItem = {
  bank: string
  file: string
  decision: Decision
  fields: Record<string, FieldRecord>
  imageUrl?: string
}
