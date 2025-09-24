import React from 'react'
import { useParams, useSearchParams, useNavigate, useLocation } from 'react-router-dom'
import { getReviewItem, getItem, submitCorrections, exportItems } from '../../utils/api'
import type { ReviewItem } from '../../types/review'
import ReviewFields from '../../components/ReviewFields'

export default function ChequeReviewPage() {
  const { chequeId = '', bank, fileId } = useParams()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const location = useLocation()
  const navItem = (location.state as any)?.item as ReviewItem | undefined
  const [item, setItem] = React.useState<ReviewItem | null>(navItem ?? null)
  const [loading, setLoading] = React.useState<boolean>(!navItem)
  const [error, setError] = React.useState<string | null>(null)
  const [selected, setSelected] = React.useState<string | null>(null)
  const [filterLowOnly, setFilterLowOnly] = React.useState(false)
  const [sortByConfidence, setSortByConfidence] = React.useState(false)
  const [showHelp, setShowHelp] = React.useState(false)
  const [editMode, setEditMode] = React.useState(false)
  // Scope edits to current item (avoid applying edits across images)
  const itemKey = React.useMemo(
    () => (bank && fileId ? `${bank}/${fileId}` : chequeId),
    [bank, fileId, chequeId]
  )
  const [editsMap, setEditsMap] = React.useState<Record<string, Record<string, string>>>({})
  const edits = React.useMemo(() => editsMap[itemKey] ?? {}, [editsMap, itemKey])
  const [saved, setSaved] = React.useState<null | 'ok' | 'err'>(null)
  const [queueUrls, setQueueUrls] = React.useState<string[] | null>(null)
  const [queueId, setQueueId] = React.useState<string | null>(null)
  const [queueIndex, setQueueIndex] = React.useState<number>(-1)
  const [queueTotal, setQueueTotal] = React.useState<number | null>(null)
  const [imgRetry, setImgRetry] = React.useState<number>(0)

  React.useEffect(() => {
    let ignore = false
    // Try to hydrate immediately from navigation state or cache (set by Upload page)
    let hydratedFromCache = !!navItem
    if (navItem && !ignore) {
      setItem(navItem)
      setLoading(false)
      hydratedFromCache = true
    }
    if (bank && fileId) {
      try {
        const raw = localStorage.getItem(`uploadItem:${bank}/${fileId}`)
        if (raw) {
          const cached = JSON.parse(raw)
          if (!ignore && cached && typeof cached === 'object') {
            setItem(cached)
            setLoading(false)
            hydratedFromCache = true
          }
        }
      } catch {}
    }

    const load = async () => {
      try {
        let data: ReviewItem
        if (bank && fileId && (import.meta as any).env?.VITE_BACKEND_BASE) {
          data = await getItem(bank, fileId)
        } else {
          data = await getReviewItem(chequeId)
        }
        if (!ignore) setItem(data)
      } catch (e: any) {
        // Only surface error if we didn't hydrate from cache
        if (!hydratedFromCache) setError(String(e))
      } finally {
        if (!hydratedFromCache) setLoading(false)
      }
    }
    // If we didn't hydrate from cache, show loading until fetch resolves
    if (!hydratedFromCache) setLoading(true)
    load()
    return () => {
      ignore = true
    }
  }, [chequeId, bank, fileId, navItem])

  // Read queue from URL/localStorage (created by Upload page) e.g. ?queue=<id>&i=<index>
  React.useEffect(() => {
    const q = searchParams.get('queue')
    const i = searchParams.get('i')
    if (!q) {
      setQueueId(null)
      setQueueUrls(null)
      setQueueIndex(-1)
      setQueueTotal(null)
      return
    }
    setQueueId(q)
    let idx = -1
    try {
      idx = i ? parseInt(i, 10) : 0
    } catch {
      idx = 0
    }
    let urls: string[] | null = null
    try {
      const raw = localStorage.getItem(`uploadQueue:${q}`)
      if (raw) urls = JSON.parse(raw)
      const t = localStorage.getItem(`uploadQueue:total:${q}`)
      setQueueTotal(t ? parseInt(t, 10) : null)
    } catch {}
    setQueueUrls(Array.isArray(urls) ? urls : null)
    setQueueIndex(Array.isArray(urls) ? Math.max(0, Math.min(idx, urls.length - 1)) : -1)
  }, [searchParams])

  // Poll localStorage for queue updates so newly finished items appear automatically
  React.useEffect(() => {
    if (!queueId) return
    let stopped = false
    const tick = () => {
      if (stopped) return
      try {
        const raw = localStorage.getItem(`uploadQueue:${queueId}`)
        if (!raw) return
        const arr = JSON.parse(raw)
        if (!Array.isArray(arr)) return
        // Only update if changed in length or content
        const cur = queueUrls ?? []
        const changed =
          arr.length !== cur.length || arr.some((v: string, idx: number) => v !== cur[idx])
        if (changed) {
          setQueueUrls(arr)
          // Clamp index to new bounds
          setQueueIndex((prev) =>
            prev < 0 ? (arr.length ? 0 : -1) : Math.min(prev, arr.length - 1)
          )
        }
        const t = localStorage.getItem(`uploadQueue:total:${queueId}`)
        if (t) setQueueTotal(parseInt(t, 10))
      } catch {}
    }
    const h = setInterval(tick, 1000)
    return () => {
      stopped = true
      clearInterval(h)
    }
  }, [queueId, queueUrls])

  const hasDirtyEdits = React.useCallback(() => {
    return !!itemKey && edits && Object.keys(edits).length > 0
  }, [edits, itemKey])

  const autoSaveIfNeeded = React.useCallback(async () => {
    if (!item || !hasDirtyEdits()) return
    const updates: Record<string, string> = {}
    for (const [k, v] of Object.entries(edits)) {
      if (typeof v === 'string') updates[k] = v
    }
    if (Object.keys(updates).length === 0) return
    try {
      await submitCorrections(chequeId, updates, {
        bank: item.bank,
        file: item.file,
        reviewer_id: 'dev',
      })
    } catch (e) {
      // Best-effort auto-save; do not block navigation on error
      console.warn('Auto-save failed before Next', e)
    }
  }, [item, edits, chequeId, hasDirtyEdits])

  const goToIndex = React.useCallback(
    async (nextIdx: number) => {
      if (!queueUrls || !queueId) return
      if (nextIdx < 0 || nextIdx >= queueUrls.length) return
      // Auto-save only when moving forward
      if (queueIndex >= 0 && nextIdx > queueIndex) {
        await autoSaveIfNeeded()
      }
      const target = queueUrls[nextIdx]
      const sep = target.includes('?') ? '&' : '?'
      navigate(`${target}${sep}queue=${encodeURIComponent(queueId)}&i=${nextIdx}`)
    },
    [queueUrls, queueId, queueIndex, navigate, autoSaveIfNeeded]
  )

  const hasPrev = queueUrls && queueIndex > 0
  const hasNext =
    queueUrls && queueUrls.length > 0 && queueIndex >= 0 && queueIndex < queueUrls.length - 1

  const batchComplete = React.useMemo(() => {
    if (!queueId || !queueUrls) return true
    if (queueTotal == null) return false
    return queueUrls.length >= queueTotal
  }, [queueId, queueUrls, queueTotal])

  const backendBase = (import.meta as any).env?.VITE_BACKEND_BASE as string | undefined
  const displayImageUrl = React.useMemo(() => {
    if (!item) return undefined
    if (item.imageUrl) return item.imageUrl
    if (backendBase && bank && fileId) {
      return `${backendBase.replace(/\/$/, '')}/files/${encodeURIComponent(bank)}/${encodeURIComponent(fileId)}`
    }
    return undefined
  }, [item, backendBase, bank, fileId])

  const parseQueueItem = (url: string): { bank: string; file: string } | null => {
    try {
      const u = url.split('?')[0]
      const parts = u.split('/')
      const bank = parts[2]
      const file = parts[3]
      if (bank && file) return { bank, file }
      return null
    } catch {
      return null
    }
  }

  const buildOverrides = (): Record<string, Record<string, string>> => {
    const out: Record<string, Record<string, string>> = {}
    for (const [k, map] of Object.entries(editsMap)) {
      if (!map) continue
      // k is either "BANK/FILE" or chequeId (stub)
      if (k.includes('/')) {
        out[k] = { ...map }
      } else if (item?.bank && item?.file) {
        out[`${item.bank}/${item.file}`] = { ...(out[`${item.bank}/${item.file}`] ?? {}), ...map }
      }
    }
    return out
  }

  const onExportClick = async () => {
    if (!queueUrls || queueUrls.length === 0) return
    const items = queueUrls
      .map(parseQueueItem)
      .filter((x): x is { bank: string; file: string } => !!x)
    try {
      const blob = await exportItems(items, buildOverrides())
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'cheques.csv'
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } catch (e) {
      console.error('export failed', e)
    }
  }

  const onSubmit = async () => {
    if (!item) return
    // Build updates from edits state
    const updates: Record<string, string> = {}
    for (const [k, v] of Object.entries(edits)) {
      if (typeof v === 'string') updates[k] = v
    }
    try {
      await submitCorrections(chequeId, updates, {
        bank: item.bank,
        file: item.file,
        reviewer_id: 'dev',
      })
      setSaved('ok')
      setTimeout(() => setSaved(null), 1500)
    } catch (e) {
      setSaved('err')
      setTimeout(() => setSaved(null), 2000)
    }
  }

  const threshold = 0.995

  const orderedKeys = React.useMemo(() => {
    if (!item) return [] as string[]
    const entries = Object.entries(item.fields)
    const withLowFlag = entries.map(([name, rec]) => ({
      name,
      conf: rec.field_conf ?? 0,
      meets:
        typeof rec.meets_threshold === 'boolean'
          ? rec.meets_threshold
          : (rec.field_conf ?? 0) >= threshold,
    }))
    // Mute 'name' field from UI (temporarily hidden but preserved in payload)
    let keys = withLowFlag
      .filter((e) => (filterLowOnly ? !e.meets : true))
      .map((e) => e.name)
      .filter((k) => k !== 'name')
    if (sortByConfidence) {
      keys = keys.sort(
        (a, b) => (item.fields[a].field_conf ?? 0) - (item.fields[b].field_conf ?? 0)
      )
    }
    return keys
  }, [item, filterLowOnly, sortByConfidence])

  // Select first item when list changes
  React.useEffect(() => {
    if (!selected && orderedKeys.length > 0) {
      setSelected(orderedKeys[0])
    } else if (selected && orderedKeys.length > 0 && !orderedKeys.includes(selected)) {
      setSelected(orderedKeys[0])
    }
  }, [orderedKeys, selected])

  // Ensure selected field is brought into view
  React.useEffect(() => {
    if (!selected) return
    const el = document.getElementById(`field-${selected}`)
    // In test environment (jsdom), scrollIntoView may be undefined
    el?.scrollIntoView?.({ block: 'nearest' })
  }, [selected])

  // Keyboard shortcuts
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!item) return
      if (e.key === '?' || (e.shiftKey && e.key.toLowerCase() === '/')) {
        e.preventDefault()
        setShowHelp((v) => !v)
        return
      }
      if (e.key === 'f') {
        e.preventDefault()
        setFilterLowOnly((v) => !v)
        return
      }
      if (e.key === 's') {
        e.preventDefault()
        setSortByConfidence((v) => !v)
        return
      }
      if (!selected) return
      const idx = orderedKeys.indexOf(selected)
      if (e.key === 'j' || e.key === 'ArrowDown') {
        e.preventDefault()
        const next = orderedKeys[Math.min(idx + 1, orderedKeys.length - 1)]
        if (next) setSelected(next)
      } else if (e.key === 'k' || e.key === 'ArrowUp') {
        e.preventDefault()
        const prev = orderedKeys[Math.max(idx - 1, 0)]
        if (prev) setSelected(prev)
      } else if (e.key === 'e' || e.key === 'Enter') {
        e.preventDefault()
        setEditMode(true)
      } else if (e.key === 'Escape') {
        if (editMode) {
          e.preventDefault()
          setEditMode(false)
        }
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [item, orderedKeys, selected, editMode])

  const selectedValue = React.useMemo(() => {
    if (!item || !selected) return ''
    const rec = item.fields[selected]
    const tentative = rec.parse_norm ?? rec.ocr_text ?? ''
    const isArabic = rec.ocr_lang === 'ar' || /[\u0600-\u06FF]/.test(String(tentative))
    // Prefer OCR logical text for Arabic to avoid any pre-shaped reversal
    const baseValue = isArabic ? (rec.ocr_text ?? rec.parse_norm ?? '') : tentative
    const display = edits[selected] ?? baseValue
    return display
  }, [item, selected, edits])

  const normalizedSelectedValue = React.useMemo(() => {
    let v = String(selectedValue)
    try {
      v = v.normalize('NFKC')
    } catch {}
    // strip zero-width and bidi controls
    v = v.replace(/[\u200B\u200C\u200E\u200F\u202A-\u202E\u2066-\u2069]/g, '')
    return v
  }, [selectedValue])

  const selectedIsArabic = React.useMemo(
    () => /[\u0600-\u06FF]/.test(normalizedSelectedValue),
    [normalizedSelectedValue]
  )

  const onEditChange: React.ChangeEventHandler<HTMLInputElement> = (e) => {
    if (!selected) return
    setEditsMap((cur) => ({
      ...cur,
      [itemKey]: {
        ...(cur[itemKey] ?? {}),
        [selected]: e.target.value,
      },
    }))
  }

  const fieldsWithEdits = React.useMemo(() => {
    if (!item) return {}
    const cloned: ReviewItem['fields'] = JSON.parse(JSON.stringify(item.fields))
    for (const [k, v] of Object.entries(edits)) {
      if (cloned[k]) {
        ;(cloned[k] as any).parse_norm = String(v)
        // For Arabic, also mirror into ocr_text so ReviewFields (which prefers OCR for Arabic) reflects the edit immediately
        if ((cloned[k] as any).ocr_lang === 'ar') {
          ;(cloned[k] as any).ocr_text = String(v)
        }
      }
    }
    return cloned
  }, [item, edits])

  if (loading) return <div style={{ padding: 24 }}>Loading…</div>
  if (error) return <div style={{ padding: 24, color: '#dc2626' }}>Error: {error}</div>
  if (!item) return <div style={{ padding: 24 }}>Not found</div>

  return (
    <div
      style={{ display: 'flex', flexDirection: 'column', minHeight: '100%', background: '#f8fafc' }}
    >
      <header
        style={{
          padding: '12px 16px',
          borderBottom: '1px solid #e5e7eb',
          display: 'flex',
          gap: 12,
          alignItems: 'center',
          background: 'white',
          position: 'sticky',
          top: 0,
          zIndex: 10,
        }}
      >
        <h1 style={{ fontSize: 18, margin: 0, color: '#111827' }}>Cheque Reviewer</h1>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <span
            style={{
              fontSize: 12,
              color: '#111827',
              border: '1px solid #e5e7eb',
              background: '#f9fafb',
              padding: '4px 8px',
              borderRadius: 999,
            }}
          >
            Bank: <strong>{item.bank}</strong>
          </span>
          <span
            style={{
              fontSize: 12,
              color: '#111827',
              border: '1px solid #e5e7eb',
              background: '#f9fafb',
              padding: '4px 8px',
              borderRadius: 999,
            }}
          >
            File: <strong>{item.file}</strong>
          </span>
          <span
            style={{
              fontSize: 12,
              color: '#047857',
              border: '1px solid #bbf7d0',
              background: '#ecfdf5',
              padding: '4px 8px',
              borderRadius: 999,
            }}
          >
            {item.decision.decision}
          </span>
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <a
            href="/upload"
            style={{
              display: 'inline-block',
              padding: '8px 12px',
              border: '1px solid #e5e7eb',
              borderRadius: 8,
              background: 'white',
              color: '#111827',
              textDecoration: 'none',
              boxShadow: '0 2px 8px rgba(0,0,0,0.04)',
            }}
          >
            Upload
          </a>
          <button
            onClick={onSubmit}
            style={{
              padding: '8px 12px',
              border: '1px solid #111827',
              borderRadius: 8,
              background: '#111827',
              color: 'white',
              boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
            }}
          >
            Save (stub)
          </button>
        </div>
      </header>
      {saved && (
        <div
          role="status"
          style={{
            padding: '6px 12px',
            background: saved === 'ok' ? '#dcfce7' : '#fee2e2',
            color: saved === 'ok' ? '#166534' : '#991b1b',
            borderBottom: '1px solid #e5e7eb',
          }}
        >
          {saved === 'ok' ? 'Saved' : 'Failed to save'}
        </div>
      )}
      <main
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: 16,
          padding: 16,
          height: '100%',
          boxSizing: 'border-box',
        }}
      >
        <section
          aria-label="image-pane"
          style={{
            border: '1px solid #e5e7eb',
            borderRadius: 8,
            minHeight: 300,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'white',
            boxShadow: '0 2px 8px rgba(0,0,0,0.04)',
          }}
        >
          {displayImageUrl ? (
            <img
              src={displayImageUrl}
              alt="Cheque"
              style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }}
            />
          ) : (
            <div style={{ textAlign: 'center', color: '#6b7280' }}>
              <div style={{ fontSize: 13, marginBottom: 8 }}>Image not available</div>
              <div style={{ fontSize: 12 }}>Backend will provide image URL in later story</div>
            </div>
          )}
        </section>
        <section
          aria-label="fields-pane"
          style={{ overflow: 'auto', display: 'flex', flexDirection: 'column', gap: 8 }}
        >
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <button
              onClick={() => setFilterLowOnly((v) => !v)}
              style={{
                padding: '6px 10px',
                border: '1px solid #e5e7eb',
                borderRadius: 8,
                background: filterLowOnly ? '#f59e0b' : 'white',
              }}
            >
              Low only (f)
            </button>
            <button
              onClick={() => setSortByConfidence((v) => !v)}
              style={{
                padding: '6px 10px',
                border: '1px solid #e5e7eb',
                borderRadius: 8,
                background: sortByConfidence ? '#e5e7eb' : 'white',
              }}
            >
              Sort by confidence (s)
            </button>
            <button
              onClick={() => setShowHelp((v) => !v)}
              style={{
                padding: '6px 10px',
                border: '1px solid #e5e7eb',
                borderRadius: 8,
                background: 'white',
              }}
            >
              Hotkeys (?)
            </button>
          </div>
          {editMode && selected ? (
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <label htmlFor="edit-field" style={{ fontSize: 12, color: '#6b7280' }}>
                Edit {selected}:
              </label>
              <input
                id="edit-field"
                value={normalizedSelectedValue}
                onChange={onEditChange}
                style={{
                  flex: 1,
                  padding: '6px 8px',
                  border: '1px solid #e5e7eb',
                  borderRadius: 6,
                  direction: selectedIsArabic ? 'rtl' : 'ltr',
                  textAlign: selectedIsArabic ? 'right' : 'left',
                }}
                dir={selectedIsArabic ? 'rtl' : 'ltr'}
              />
              <span style={{ fontSize: 12, color: '#6b7280' }}>
                (Enter to apply, Esc to cancel)
              </span>
            </div>
          ) : null}
          <ReviewFields
            fields={fieldsWithEdits as any}
            order={orderedKeys}
            selected={selected ?? undefined}
            threshold={threshold}
          />
        </section>
      </main>
      {showHelp ? (
        <div
          role="dialog"
          aria-label="hotkeys"
          style={{
            position: 'fixed',
            right: 16,
            bottom: 16,
            background: 'white',
            border: '1px solid #e5e7eb',
            borderRadius: 8,
            padding: 12,
            boxShadow: '0 4px 10px rgba(0,0,0,0.1)',
          }}
        >
          <div style={{ fontWeight: 600, marginBottom: 6 }}>Hotkeys</div>
          <ul style={{ margin: 0, paddingLeft: 16, fontSize: 13, color: '#374151' }}>
            <li>j / ArrowDown — Next field</li>
            <li>k / ArrowUp — Previous field</li>
            <li>e / Enter — Edit selected</li>
            <li>Esc — Exit edit</li>
            <li>f — Toggle Low only filter</li>
            <li>s — Toggle Sort by confidence</li>
            <li>? — Toggle this help</li>
          </ul>
        </div>
      ) : null}
      {queueUrls && queueIndex >= 0 ? (
        <div
          aria-label="queue-controls"
          style={{
            position: 'fixed',
            right: 16,
            bottom: 16,
            display: 'flex',
            gap: 8,
            alignItems: 'center',
          }}
        >
          {queueId ? (
            <span
              style={{
                fontSize: 12,
                color: '#111827',
                border: '1px solid #e5e7eb',
                background: '#f9fafb',
                padding: '4px 8px',
                borderRadius: 999,
              }}
              title="Batch progress"
            >
              {queueUrls?.length ?? 0}
              {queueTotal ? ` / ${queueTotal}` : ''}
            </span>
          ) : null}
          <button
            onClick={() => goToIndex(queueIndex - 1)}
            disabled={!hasPrev}
            style={{
              padding: '8px 12px',
              border: '1px solid #e5e7eb',
              borderRadius: 8,
              background: 'white',
            }}
          >
            ◀ Prev
          </button>
          <button
            onClick={() => goToIndex(queueIndex + 1)}
            disabled={!hasNext}
            style={{
              padding: '8px 12px',
              border: '1px solid #111827',
              borderRadius: 8,
              background: '#111827',
              color: 'white',
            }}
          >
            Next ▶
          </button>
          <button
            onClick={onExportClick}
            disabled={!batchComplete || !queueUrls || queueIndex !== queueUrls.length - 1}
            style={{
              padding: '8px 12px',
              border: '1px solid',
              borderColor: batchComplete ? '#059669' : '#9ca3af',
              borderRadius: 8,
              background: batchComplete ? '#059669' : '#9ca3af',
              color: 'white',
            }}
            title={
              batchComplete
                ? 'Export reviewed items (CSV)'
                : 'Export available when batch completes'
            }
          >
            ⬇ Export CSV
          </button>
        </div>
      ) : null}
    </div>
  )
}
