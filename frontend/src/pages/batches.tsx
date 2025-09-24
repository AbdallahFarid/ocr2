import React from 'react'
import { useNavigate } from 'react-router-dom'
import { listBatches, type BatchSummary } from '../utils/api'

const banks = ['QNB', 'FABMISR', 'BANQUE_MISR', 'CIB', 'AAIB', 'NBE'] as const

type Bank = (typeof banks)[number]

export default function BatchesPage() {
  const navigate = useNavigate()
  const [bank, setBank] = React.useState<Bank>('QNB')
  const [from, setFrom] = React.useState<string>('')
  const [to, setTo] = React.useState<string>('')
  const [flagged, setFlagged] = React.useState<'all' | 'true' | 'false'>('all')
  const [rows, setRows] = React.useState<BatchSummary[]>([])
  const [loading, setLoading] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  const load = React.useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params: { from?: string; to?: string; flagged?: boolean } = {}
      if (from) params.from = from
      if (to) params.to = to
      if (flagged !== 'all') params.flagged = flagged === 'true'
      const data = await listBatches(bank, params)
      setRows(data)
    } catch (e: any) {
      setError(String(e?.message || e))
    } finally {
      setLoading(false)
    }
  }, [bank, from, to, flagged])

  React.useEffect(() => {
    load()
  }, [load])

  return (
    <div style={{ padding: 16 }}>
      <h1 style={{ marginBottom: 12 }}>Batches</h1>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 12 }}>
        <select value={bank} onChange={(e) => setBank(e.target.value as Bank)}>
          {banks.map((b) => (
            <option key={b} value={b}>
              {b}
            </option>
          ))}
        </select>
        <label>
          From
          <input
            type="date"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
            style={{ marginLeft: 4 }}
          />
        </label>
        <label>
          To
          <input
            type="date"
            value={to}
            onChange={(e) => setTo(e.target.value)}
            style={{ marginLeft: 4 }}
          />
        </label>
        <label>
          Flagged
          <select
            value={flagged}
            onChange={(e) => setFlagged(e.target.value as any)}
            style={{ marginLeft: 4 }}
          >
            <option value="all">All</option>
            <option value="true">Flagged</option>
            <option value="false">Not flagged</option>
          </select>
        </label>
        <button onClick={load} disabled={loading}>
          {loading ? 'Loading…' : 'Reload'}
        </button>
      </div>
      {error && <div style={{ color: 'red', marginBottom: 8 }}>Error: {error}</div>}
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr>
              <th style={th}>Name</th>
              <th style={th}>Date</th>
              <th style={th}>Seq</th>
              <th style={th}>Total</th>
              <th style={th}>With Errors</th>
              <th style={th}>Cheque Err%</th>
              <th style={th}>Flagged</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const errRate =
                r.error_rate_cheques ??
                (r.total_cheques ? (r.cheques_with_errors ?? 0) / (r.total_cheques || 1) : 0)
              return (
                <tr
                  key={r.name}
                  style={{ cursor: 'pointer' }}
                  onClick={() => navigate(`/batches/${r.bank}/${encodeURIComponent(r.name)}`)}
                >
                  <td style={td}>{r.name}</td>
                  <td style={td}>{r.batch_date}</td>
                  <td style={td}>{r.seq}</td>
                  <td style={td}>{r.total_cheques ?? '-'}</td>
                  <td style={td}>{r.cheques_with_errors ?? '-'}</td>
                  <td style={td}>
                    {typeof errRate === 'number' ? `${(errRate * 100).toFixed(1)}%` : '-'}
                  </td>
                  <td style={{ ...td, color: r.flagged ? '#b91c1c' : '#065f46' }}>
                    {r.flagged ? 'Yes' : 'No'}
                  </td>
                </tr>
              )
            })}
            {!loading && rows.length === 0 && (
              <tr>
                <td colSpan={7} style={td}>
                  No batches
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

const th: React.CSSProperties = { textAlign: 'left', borderBottom: '1px solid #e5e7eb', padding: 8 }
const td: React.CSSProperties = { borderBottom: '1px solid #f1f5f9', padding: 8 }
