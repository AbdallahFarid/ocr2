import React from 'react'
import { useParams, Link } from 'react-router-dom'
import { getBatchDetail, type BatchDetail } from '../../../utils/api'

export default function BatchDetailPage() {
  const { bank = 'QNB', name = '' } = useParams()
  const [data, setData] = React.useState<BatchDetail | null>(null)
  const [loading, setLoading] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  React.useEffect(() => {
    async function run() {
      setLoading(true)
      setError(null)
      try {
        const res = await getBatchDetail(bank as any, decodeURIComponent(name))
        setData(res)
      } catch (e: any) {
        setError(String(e?.message || e))
      } finally {
        setLoading(false)
      }
    }
    run()
  }, [bank, name])

  if (loading) return <div style={{ padding: 16 }}>Loading…</div>
  if (error) return <div style={{ padding: 16, color: 'red' }}>Error: {error}</div>
  if (!data) return <div style={{ padding: 16 }}>No batch</div>

  return (
    <div style={{ padding: 16 }}>
      <div style={{ marginBottom: 8 }}>
        <Link to="/batches">← Back</Link>
      </div>
      <h1 style={{ marginBottom: 12 }}>{data.name}</h1>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, minmax(0, 1fr))',
          gap: 8,
          marginBottom: 16,
        }}
      >
        <Stat label="Date" value={data.batch_date} />
        <Stat label="Seq" value={String(data.seq)} />
        <Stat label="Total cheques" value={String(data.kpis.total_cheques ?? '-')} />
        <Stat label="With errors" value={String(data.kpis.cheques_with_errors ?? '-')} />
      </div>
      <h2 style={{ margin: '12px 0' }}>Cheques</h2>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr>
              <th style={th}>File</th>
              <th style={th}>Incorrect</th>
              <th style={th}>STP</th>
              <th style={th}>Conf</th>
              <th style={th}>Index</th>
            </tr>
          </thead>
          <tbody>
            {data.cheques.map((c) => (
              <tr key={c.file}>
                <td style={td}>{c.file}</td>
                <td style={td}>{c.incorrect_fields_count ?? '-'}</td>
                <td style={td}>{c.stp ? 'Yes' : 'No'}</td>
                <td style={td}>{c.overall_conf ?? '-'}</td>
                <td style={td}>{c.index_in_batch ?? '-'}</td>
              </tr>
            ))}
            {data.cheques.length === 0 && (
              <tr>
                <td colSpan={5} style={td}>
                  No cheques
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ border: '1px solid #e5e7eb', borderRadius: 8, padding: 8 }}>
      <div style={{ fontSize: 12, color: '#475569' }}>{label}</div>
      <div style={{ fontSize: 16, fontWeight: 600 }}>{value}</div>
    </div>
  )
}

const th: React.CSSProperties = { textAlign: 'left', borderBottom: '1px solid #e5e7eb', padding: 8 }
const td: React.CSSProperties = { borderBottom: '1px solid #f1f5f9', padding: 8 }
