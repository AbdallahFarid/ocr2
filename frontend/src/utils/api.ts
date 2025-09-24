import type { ReviewItem } from '../types/review'

// Stubbed API per Story 3.1 acceptance criteria
export async function getReviewItem(chequeId: string): Promise<ReviewItem> {
  // Simulate latency
  await new Promise((r) => setTimeout(r, 50))
  // Minimal mock consistent with backend audit JSON example
  return {
    bank: 'FABMISR',
    file: chequeId,
    decision: {
      decision: 'review',
      stp: false,
      overall_conf: 0.93,
      low_conf_fields: ['date', 'cheque_number', 'name'],
      reasons: [
        'low_confidence:date:0.986<thr0.995',
        'low_confidence:cheque_number:0.946<thr0.995',
        'low_confidence:name:0.930<thr0.995',
      ],
    },
    fields: {
      date: {
        field_conf: 0.986,
        loc_conf: 0.999,
        ocr_conf: 0.986,
        validation: { ok: true, code: 'OK' },
        parse_ok: true,
        parse_norm: '2025-12-31',
        ocr_text: '31/Dec/2025',
        ocr_lang: 'en',
        meets_threshold: false,
      },
      cheque_number: {
        field_conf: 0.946,
        loc_conf: 0.957,
        ocr_conf: 0.989,
        validation: { ok: true, code: 'OK' },
        parse_ok: true,
        parse_norm: '11637506',
        ocr_text: '11637506',
        ocr_lang: 'en',
        meets_threshold: false,
      },
      amount_numeric: {
        field_conf: 1.0,
        loc_conf: 1.0,
        ocr_conf: 1.0,
        validation: { ok: true, code: 'OK' },
        parse_ok: true,
        parse_norm: '817410.00',
        ocr_text: '817,410.00',
        ocr_lang: 'en',
        meets_threshold: true,
      },
      name: {
        field_conf: 0.93,
        loc_conf: 0.989,
        ocr_conf: 0.94,
        validation: { ok: true, code: 'OK' },
        parse_ok: true,
        parse_norm: 'شركة بالم هيلز للتعمير',
        ocr_text: 'شركة بالم هيلز للتعمير',
        ocr_lang: 'ar',
        meets_threshold: false,
      },
    },
    imageUrl: undefined, // Backend will supply later; placeholder box is shown if missing
  }
}

export type BatchSummary = {
  bank: string
  name: string
  batch_date: string
  seq: number
  flagged: boolean
  status: string
  processing_started_at?: string | null
  processing_ended_at?: string | null
  processing_ms?: number | null
  total_cheques?: number | null
  cheques_with_errors?: number | null
  total_fields?: number | null
  incorrect_fields?: number | null
  error_rate_cheques?: number | null
  error_rate_fields?: number | null
}

export async function listBatches(
  bank: 'QNB' | 'FABMISR' | 'BANQUE_MISR' | 'CIB' | 'AAIB' | 'NBE',
  params?: { from?: string; to?: string; flagged?: boolean }
): Promise<BatchSummary[]> {
  if (!backendBase) return []
  const q = new URLSearchParams({ bank })
  if (params?.from) q.set('from', params.from)
  if (params?.to) q.set('to', params.to)
  if (typeof params?.flagged === 'boolean') q.set('flagged', String(params.flagged))
  const res = await fetch(`${backendBase.replace(/\/$/, '')}/batches?${q.toString()}`)
  if (!res.ok) throw new Error(`listBatches failed: ${res.status}`)
  return res.json()
}

export type BatchDetail = {
  bank: string
  name: string
  batch_date: string
  seq: number
  flagged: boolean
  status: string
  kpis: {
    total_cheques: number | null
    cheques_with_errors: number | null
    total_fields: number | null
    incorrect_fields: number | null
    error_rate_cheques: number | null
    error_rate_fields: number | null
  }
  cheques: Array<{
    file: string
    incorrect_fields_count?: number | null
    decision?: string | null
    stp?: boolean | null
    overall_conf?: number | null
    index_in_batch?: number | null
    created_at?: string | null
  }>
}

export async function getBatchDetail(
  bank: 'QNB' | 'FABMISR' | 'BANQUE_MISR' | 'CIB' | 'AAIB' | 'NBE',
  batchName: string
): Promise<BatchDetail> {
  if (!backendBase) throw new Error('No backend configured')
  const res = await fetch(
    `${backendBase.replace(/\/$/, '')}/batches/${bank}/${encodeURIComponent(batchName)}`
  )
  if (!res.ok) throw new Error(`getBatchDetail failed: ${res.status}`)
  return res.json()
}

export async function exportItems(
  items: Array<{ bank: string; file: string }>,
  overrides?: Record<string, Record<string, string>>
): Promise<Blob> {
  if (!backendBase) throw new Error('No backend configured')
  const res = await fetch(`${backendBase.replace(/\/$/, '')}/review/export`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ items, overrides: overrides ?? {}, format: 'csv' }),
  })
  if (!res.ok) throw new Error(`export failed: ${res.status}`)
  return res.blob()
}

let backendBase: string | undefined =
  (import.meta as any).env?.VITE_BACKEND_BASE || 'http://127.0.0.1:8000'

export function setBackendBase(url?: string) {
  backendBase = url
}

type SubmitCtx = { bank: string; file: string; reviewer_id?: string }

export async function listItems(): Promise<Array<{ bank: string; file: string }>> {
  if (!backendBase) return []
  const res = await fetch(`${backendBase.replace(/\/$/, '')}/review/items`)
  if (!res.ok) throw new Error(`listItems failed: ${res.status}`)
  return res.json()
}

export async function finalizeBatch(
  bank: 'QNB' | 'FABMISR' | 'BANQUE_MISR' | 'CIB' | 'AAIB' | 'NBE',
  correlationId: string
): Promise<{ ok: boolean; bank: string; batch: string; metrics?: any }> {
  if (!backendBase) throw new Error('No backend configured')
  const fd = new FormData()
  fd.append('bank', bank)
  fd.append('correlation_id', correlationId)
  const res = await fetch(`${backendBase.replace(/\/$/, '')}/review/batches/finalize`, {
    method: 'POST',
    body: fd,
  })
  if (!res.ok) throw new Error(`finalize failed: ${res.status}`)
  return res.json()
}

export async function uploadZip(
  bank: 'QNB' | 'FABMISR' | 'BANQUE_MISR' | 'CIB' | 'AAIB' | 'NBE',
  zipFile: File,
  correlationId?: string
): Promise<{
  ok: boolean
  count: number
  firstReviewUrl: string
  items: Array<{ bank: string; file: string; reviewUrl: string; imageUrl?: string }>
}> {
  if (!backendBase) throw new Error('No backend configured')
  const fd = new FormData()
  fd.append('bank', bank)
  if (correlationId) fd.append('correlation_id', correlationId)
  fd.append('zip_file', zipFile)
  const res = await fetch(`${backendBase.replace(/\/$/, '')}/review/upload`, {
    method: 'POST',
    body: fd,
  })
  if (!res.ok) throw new Error(`upload zip failed: ${res.status}`)
  return res.json()
}

export async function getItem(bank: string, fileId: string): Promise<ReviewItem> {
  if (!backendBase) throw new Error('No backend configured')
  const res = await fetch(
    `${backendBase.replace(/\/$/, '')}/review/items/${encodeURIComponent(bank)}/${encodeURIComponent(fileId)}`
  )
  if (!res.ok) throw new Error(`getItem failed: ${res.status}`)
  return res.json()
}

export async function submitCorrections(
  chequeId: string,
  updates: Record<string, string>,
  ctx?: SubmitCtx
): Promise<{ ok: true }> {
  // If a backend base is configured and context is provided, call the backend; otherwise stub
  if (backendBase && ctx) {
    const reviewer = ctx.reviewer_id ?? 'demo'
    const body = {
      reviewer_id: reviewer,
      updates: Object.fromEntries(
        Object.entries(updates).map(([k, v]) => [k, { value: v, reason: null }])
      ),
    }
    const res = await fetch(
      `${backendBase.replace(/\/$/, '')}/review/items/${encodeURIComponent(ctx.bank)}/${encodeURIComponent(ctx.file)}/corrections`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }
    )
    if (!res.ok) {
      throw new Error(`submitCorrections failed: ${res.status}`)
    }
    return { ok: true }
  }
  // Stub: pretend success
  await new Promise((r) => setTimeout(r, 50))
  return { ok: true }
}

export async function uploadCheque(
  bank: 'QNB' | 'FABMISR' | 'BANQUE_MISR' | 'CIB' | 'AAIB' | 'NBE',
  file: File,
  correlationId?: string
): Promise<{
  ok: boolean
  bank: string
  file: string
  imageUrl?: string
  reviewUrl: string
  item: ReviewItem
}> {
  if (!backendBase) throw new Error('No backend configured')
  const fd = new FormData()
  fd.append('bank', bank)
  if (correlationId) fd.append('correlation_id', correlationId)
  fd.append('file', file)
  const res = await fetch(`${backendBase.replace(/\/$/, '')}/review/upload`, {
    method: 'POST',
    body: fd,
  })
  if (!res.ok) throw new Error(`upload failed: ${res.status}`)
  return res.json()
}
