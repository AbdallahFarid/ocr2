// LocalStorage helpers for batch queue management

export type QueueItem = {
  bank: string
  file: string
  reviewUrl: string
}

/**
 * Save uploaded items to localStorage queue
 */
export function saveQueue(correlationId: string, items: QueueItem[]) {
  const key = `uploadQueue:${correlationId}`
  localStorage.setItem(key, JSON.stringify(items))
  localStorage.setItem(`${key}:total`, String(items.length))
}

/**
 * Get queue items from localStorage
 */
export function getQueue(correlationId: string): QueueItem[] {
  const key = `uploadQueue:${correlationId}`
  const data = localStorage.getItem(key)
  return data ? JSON.parse(data) : []
}

/**
 * Clear queue from localStorage
 */
export function clearQueue(correlationId: string) {
  const key = `uploadQueue:${correlationId}`
  localStorage.removeItem(key)
  localStorage.removeItem(`${key}:total`)
}

/**
 * Generate correlation ID (timestamp-based)
 */
export function generateCorrelationId(): string {
  return Date.now().toString()
}
