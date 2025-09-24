import React from 'react'
import { useNavigate } from 'react-router-dom'
import { uploadCheque, uploadZip } from '../../utils/api'

const banks = [
  { id: 'QNB', label: 'QNB' },
  { id: 'FABMISR', label: 'FABMISR' },
  { id: 'BANQUE_MISR', label: 'BANQUE MISR' },
  { id: 'CIB', label: 'CIB' },
  { id: 'AAIB', label: 'AAIB' },
  { id: 'NBE', label: 'NBE' },
] as const

type BankId = (typeof banks)[number]['id']

export default function UploadPage() {
  const navigate = useNavigate()
  const [bank, setBank] = React.useState<BankId>('FABMISR')
  const [files, setFiles] = React.useState<File[]>([])
  const [zipFile, setZipFile] = React.useState<File | null>(null)
  const [mode, setMode] = React.useState<'images' | 'zip'>('images')
  const [error, setError] = React.useState<string | null>(null)
  const [loading, setLoading] = React.useState(false)

  const onFileChange: React.ChangeEventHandler<HTMLInputElement> = (e) => {
    const list = e.target.files ? Array.from(e.target.files) : []
    setFiles(list)
  }

  const onZipChange: React.ChangeEventHandler<HTMLInputElement> = (e) => {
    const f = e.target.files && e.target.files[0] ? e.target.files[0] : null
    setZipFile(f)
  }

  const onSubmit: React.FormEventHandler<HTMLFormElement> = async (e) => {
    e.preventDefault()
    setError(null)
    if (mode === 'zip') {
      if (!zipFile) {
        setError('Please choose a .zip file')
        return
      }
      const name = zipFile.name.toLowerCase()
      const isZip =
        name.endsWith('.zip') ||
        zipFile.type === 'application/zip' ||
        zipFile.type === 'application/x-zip-compressed'
      if (!isZip) {
        setError('Unsupported file type. Please upload a .zip file')
        return
      }
    } else {
      if (!files || files.length === 0) {
        setError('Please choose at least one image file')
        return
      }
      const allowed = ['image/jpeg', 'image/jpg', 'image/png', 'image/tiff']
      for (const f of files) {
        if (f.type && !allowed.includes(f.type)) {
          setError(`Unsupported file type: ${f.name}`)
          return
        }
        if (f.size > 20 * 1024 * 1024) {
          setError(`File too large (max 20MB): ${f.name}`)
          return
        }
      }
    }
    setLoading(true)
    try {
      if (mode === 'zip' && zipFile) {
        const queueId = `${Date.now()}`
        const resp = await uploadZip(bank, zipFile, queueId)
        // Build queue URLs from items
        const urls = (resp.items || []).map((it) => it.reviewUrl)
        try {
          localStorage.setItem(`uploadQueue:${queueId}`, JSON.stringify(urls))
          localStorage.setItem(`uploadQueue:total:${queueId}`, String(resp.count ?? urls.length))
        } catch {}
        // Navigate to first review item
        const first = resp.firstReviewUrl
        const sep = first.includes('?') ? '&' : '?'
        navigate(`${first}${sep}queue=${encodeURIComponent(queueId)}&i=0`)
        setLoading(false)
      } else {
        const queueId = `${Date.now()}`
        // initialize empty queue in localStorage
        try {
          localStorage.setItem(`uploadQueue:${queueId}`, JSON.stringify([]))
          localStorage.setItem(`uploadQueue:total:${queueId}`, String(files.length))
        } catch {}
        let navigated = false
        // Kick off all uploads concurrently
        const tasks = files.map(async (f) => {
          try {
            const res = await uploadCheque(bank, f, queueId)
            if (!res?.reviewUrl) return
            // Cache the item for immediate display on the review page
            try {
              localStorage.setItem(
                `uploadItem:${res.bank}/${res.file}`,
                JSON.stringify(res.item ?? {})
              )
            } catch {}
            // Append to queue in localStorage atomically
            let arr: string[] = []
            try {
              const raw = localStorage.getItem(`uploadQueue:${queueId}`)
              arr = raw ? JSON.parse(raw) : []
            } catch {}
            const exists = arr.includes(res.reviewUrl)
            if (!exists) arr.push(res.reviewUrl)
            try {
              localStorage.setItem(`uploadQueue:${queueId}`, JSON.stringify(arr))
            } catch {}
            // Navigate to first finished item
            if (!navigated) {
              navigated = true
              const first = res.reviewUrl
              const sep = first.includes('?') ? '&' : '?'
              const idx = 0
              navigate(`${first}${sep}queue=${encodeURIComponent(queueId)}&i=${idx}`, {
                state: { item: res.item ?? null },
              })
            }
          } catch (err) {
            // Leave as best-effort; continue with others
            console.error('upload failed', err)
          }
        })
        // Do not await all; allow background completion
        Promise.allSettled(tasks).finally(() => setLoading(false))
      }
    } catch (err: any) {
      setError(String(err?.message || err))
      setLoading(false)
    }
  }

  return (
    <div
      style={{ display: 'flex', flexDirection: 'column', minHeight: '100%', background: '#f8fafc' }}
    >
      <header
        style={{
          padding: '14px 18px',
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
        <h1 style={{ fontSize: 18, margin: 0, color: '#111827' }}>Upload Cheques</h1>
      </header>
      <main style={{ padding: 20, display: 'flex', justifyContent: 'center' }}>
        <form
          onSubmit={onSubmit}
          style={{
            width: '100%',
            maxWidth: 640,
            display: 'grid',
            gap: 16,
            background: 'white',
            border: '1px solid #e5e7eb',
            borderRadius: 12,
            padding: 20,
            boxShadow: '0 4px 16px rgba(0,0,0,0.04)',
          }}
        >
          <div>
            <div style={{ fontWeight: 600, marginBottom: 8, color: '#111827' }}>Bank</div>
            <div style={{ display: 'flex', gap: 10 }}>
              {banks.map((b) => (
                <label
                  key={b.id}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 8,
                    border: '1px solid #e5e7eb',
                    padding: '6px 10px',
                    borderRadius: 999,
                    background: bank === b.id ? '#111827' : 'white',
                    color: bank === b.id ? 'white' : '#111827',
                    cursor: 'pointer',
                  }}
                >
                  <input
                    type="radio"
                    name="bank"
                    value={b.id}
                    checked={bank === b.id}
                    onChange={() => setBank(b.id)}
                    style={{ display: 'none' }}
                  />
                  {b.label}
                </label>
              ))}
            </div>
          </div>

          <div>
            <div style={{ fontWeight: 600, marginBottom: 8, color: '#111827' }}>Upload Mode</div>
            <div style={{ display: 'flex', gap: 10, marginBottom: 10 }}>
              <label
                style={{ display: 'inline-flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}
              >
                <input
                  type="radio"
                  name="mode"
                  value="images"
                  checked={mode === 'images'}
                  onChange={() => setMode('images')}
                />
                Images (multi-select)
              </label>
              <label
                style={{ display: 'inline-flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}
              >
                <input
                  type="radio"
                  name="mode"
                  value="zip"
                  checked={mode === 'zip'}
                  onChange={() => setMode('zip')}
                />
                ZIP (bulk upload)
              </label>
            </div>

            {mode === 'images' ? (
              <>
                <input
                  type="file"
                  accept=".jpg,.jpeg,.png,.tif,.tiff,image/*"
                  multiple
                  onChange={onFileChange}
                />
                <div style={{ fontSize: 12, color: '#6b7280', marginTop: 6 }}>
                  Max 20MB each. jpg, jpeg, png, tiff. You can select multiple files.
                </div>
                {files.length > 0 ? (
                  <div style={{ marginTop: 10, display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                    {files.map((f) => (
                      <span
                        key={f.name}
                        style={{
                          fontSize: 12,
                          color: '#111827',
                          border: '1px solid #e5e7eb',
                          background: '#f9fafb',
                          padding: '4px 8px',
                          borderRadius: 999,
                        }}
                      >
                        {f.name}
                      </span>
                    ))}
                  </div>
                ) : null}
              </>
            ) : (
              <>
                <input
                  type="file"
                  accept=".zip,application/zip,application/x-zip-compressed"
                  onChange={onZipChange}
                />
                <div style={{ fontSize: 12, color: '#6b7280', marginTop: 6 }}>
                  Upload a .zip containing only images (jpg, jpeg, png, tiff).
                </div>
                {zipFile ? (
                  <div style={{ marginTop: 10, fontSize: 12, color: '#111827' }}>
                    {zipFile.name}
                  </div>
                ) : null}
              </>
            )}
          </div>

          {error ? (
            <div
              role="alert"
              style={{ color: '#991b1b', background: '#fee2e2', padding: 8, borderRadius: 6 }}
            >
              {error}
            </div>
          ) : null}

          <div>
            <button
              type="submit"
              disabled={loading}
              style={{
                padding: '10px 14px',
                border: '1px solid #111827',
                borderRadius: 10,
                background: loading ? '#374151' : '#111827',
                color: 'white',
                boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
                minWidth: 140,
              }}
            >
              {loading
                ? 'Uploading…'
                : mode === 'zip'
                  ? zipFile
                    ? `Upload ${zipFile.name}`
                    : 'Upload ZIP'
                  : files.length > 1
                    ? `Upload ${files.length} files`
                    : 'Upload'}
            </button>
          </div>
        </form>
      </main>
    </div>
  )
}
