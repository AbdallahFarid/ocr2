// API client for Head Office frontend
// Minimal subset of backend API calls needed for batch processing

const backendBase = import.meta.env.VITE_BACKEND_BASE || 'http://localhost:8000'

export type Bank = 'QNB' | 'FABMISR' | 'BANQUE_MISR' | 'CIB' | 'AAIB' | 'NBE'

export type UploadResponse = {
  ok: boolean
  bank: string
  file: string
  reviewUrl: string
  imageUrl?: string
}

export type UploadZipResponse = {
  ok: boolean
  count: number
  firstReviewUrl: string
  items: Array<{
    bank: string
    file: string
    reviewUrl: string
    imageUrl?: string
  }>
}

export type FinalizeResponse = {
  ok: boolean
  bank: string
  batch: string
  metrics?: Record<string, unknown>
}

export type BatchItem = {
  bank: string
  name: string
  batch_date: string
  seq: number
  status: string
  total_cheques: number
  accuracy_rate: number | null
  error_rate_cheques: number | null
  error_rate_fields: number | null
  flagged: boolean
  created_at: string
}

/**
 * Upload a single cheque image
 */
export async function uploadCheque(
  bank: Bank,
  file: File,
  correlationId: string
): Promise<UploadResponse> {
  const fd = new FormData()
  fd.append('bank', bank)
  fd.append('correlation_id', correlationId)
  fd.append('file', file)

  const res = await fetch(`${backendBase}/review/upload`, {
    method: 'POST',
    body: fd,
  })

  if (!res.ok) {
    throw new Error(`Upload failed: ${res.status} ${res.statusText}`)
  }

  return res.json()
}

/**
 * Upload a ZIP file containing multiple cheques
 */
export async function uploadZip(
  bank: Bank,
  zipFile: File,
  correlationId: string
): Promise<UploadZipResponse> {
  const fd = new FormData()
  fd.append('bank', bank)
  fd.append('correlation_id', correlationId)
  fd.append('zip_file', zipFile)

  const res = await fetch(`${backendBase}/review/upload`, {
    method: 'POST',
    body: fd,
  })

  if (!res.ok) {
    throw new Error(`ZIP upload failed: ${res.status} ${res.statusText}`)
  }

  return res.json()
}

/**
 * Finalize batch (mark as complete)
 */
export async function finalizeBatch(
  bank: Bank,
  correlationId: string
): Promise<FinalizeResponse> {
  const fd = new FormData()
  fd.append('bank', bank)
  fd.append('correlation_id', correlationId)

  const res = await fetch(`${backendBase}/review/batches/finalize`, {
    method: 'POST',
    body: fd,
  })

  if (!res.ok) {
    throw new Error(`Finalize failed: ${res.status} ${res.statusText}`)
  }

  return res.json()
}

/**
 * Export items to Excel (CSV format)
 */
export async function exportItems(
  items: Array<{ bank: string; file: string }>
): Promise<Blob> {
  const res = await fetch(`${backendBase}/review/export`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      items,
      overrides: {}, // No corrections for Head Office (no review)
      format: 'csv',
    }),
  })

  if (!res.ok) {
    throw new Error(`Export failed: ${res.status} ${res.statusText}`)
  }

  return res.blob()
}

/**
 * Download blob as file
 */
export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

/**
 * Fetch recent batches (last 5 by default)
 */
export async function getRecentBatches(limit: number = 5): Promise<BatchItem[]> {
  const res = await fetch(`${backendBase}/batches/recent?limit=${limit}`, {
    method: 'GET',
  })

  if (!res.ok) {
    throw new Error(`Failed to fetch recent batches: ${res.status} ${res.statusText}`)
  }

  return res.json()
}
