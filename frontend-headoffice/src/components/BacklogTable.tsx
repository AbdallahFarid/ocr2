import { useState, useEffect } from 'react'
import { getRecentBatches, type BatchItem } from '../utils/api'
import { colors, typography, spacing, borderRadius, shadows } from '../styles/tokens'

export default function BacklogTable() {
  const [batches, setBatches] = useState<BatchItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadBatches()
  }, [])

  const loadBatches = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getRecentBatches(5)
      setBatches(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load batches')
    } finally {
      setLoading(false)
    }
  }

  const formatDate = (isoDate: string) => {
    const date = new Date(isoDate)
    return date.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })
  }

  const getStatusBadge = (status: string) => {
    const statusColors: Record<string, { bg: string; text: string }> = {
      pending_review: { bg: colors.warningLight, text: colors.warning },
      reviewed: { bg: colors.successLight, text: colors.success },
    }

    const style = statusColors[status] || { bg: colors.gray100, text: colors.textSecondary }

    return (
      <span
        style={{
          padding: `${spacing.xs} ${spacing.sm}`,
          backgroundColor: style.bg,
          color: style.text,
          borderRadius: borderRadius.md,
          fontSize: typography.fontSize.xs,
          fontWeight: typography.fontWeight.semibold,
          textTransform: 'uppercase',
        }}
      >
        {status.replace('_', ' ')}
      </span>
    )
  }

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: spacing['2xl'] }}>
        <p style={{ color: colors.textSecondary }}>Loading batches...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div
        style={{
          padding: spacing.lg,
          backgroundColor: colors.errorLight,
          border: `2px solid ${colors.errorBorder}`,
          borderRadius: borderRadius.xl,
          color: colors.error,
        }}
      >
        {error}
      </div>
    )
  }

  if (batches.length === 0) {
    return (
      <div
        style={{
          textAlign: 'center',
          padding: spacing['3xl'],
          backgroundColor: colors.bgPrimary,
          borderRadius: borderRadius.xl,
          border: `2px dashed ${colors.gray200}`,
        }}
      >
        <p style={{ color: colors.textTertiary, fontSize: typography.fontSize.lg }}>
          No batches processed yet
        </p>
      </div>
    )
  }

  return (
    <div
      style={{
        backgroundColor: colors.bgPrimary,
        borderRadius: borderRadius.xl,
        border: `1px solid ${colors.gray200}`,
        boxShadow: shadows.md,
        overflow: 'hidden',
      }}
    >
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ backgroundColor: colors.gray50, borderBottom: `2px solid ${colors.gray200}` }}>
            <th
              style={{
                padding: spacing.lg,
                textAlign: 'left',
                fontSize: typography.fontSize.sm,
                fontWeight: typography.fontWeight.bold,
                color: colors.textPrimary,
              }}
            >
              Batch Name
            </th>
            <th
              style={{
                padding: spacing.lg,
                textAlign: 'left',
                fontSize: typography.fontSize.sm,
                fontWeight: typography.fontWeight.bold,
                color: colors.textPrimary,
              }}
            >
              Bank
            </th>
            <th
              style={{
                padding: spacing.lg,
                textAlign: 'left',
                fontSize: typography.fontSize.sm,
                fontWeight: typography.fontWeight.bold,
                color: colors.textPrimary,
              }}
            >
              Date
            </th>
            <th
              style={{
                padding: spacing.lg,
                textAlign: 'center',
                fontSize: typography.fontSize.sm,
                fontWeight: typography.fontWeight.bold,
                color: colors.textPrimary,
              }}
            >
              Cheques
            </th>
            <th
              style={{
                padding: spacing.lg,
                textAlign: 'center',
                fontSize: typography.fontSize.sm,
                fontWeight: typography.fontWeight.bold,
                color: colors.textPrimary,
              }}
            >
              Accuracy
            </th>
            <th
              style={{
                padding: spacing.lg,
                textAlign: 'center',
                fontSize: typography.fontSize.sm,
                fontWeight: typography.fontWeight.bold,
                color: colors.textPrimary,
              }}
            >
              Status
            </th>
          </tr>
        </thead>
        <tbody>
          {batches.map((batch, index) => (
            <tr
              key={`${batch.bank}-${batch.name}`}
              style={{
                borderBottom: index < batches.length - 1 ? `1px solid ${colors.gray100}` : 'none',
                transition: 'background-color 0.2s',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.backgroundColor = colors.gray50
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.backgroundColor = 'transparent'
              }}
            >
              <td
                style={{
                  padding: spacing.lg,
                  fontSize: typography.fontSize.sm,
                  fontWeight: typography.fontWeight.medium,
                  color: colors.textPrimary,
                }}
              >
                {batch.name}
              </td>
              <td
                style={{
                  padding: spacing.lg,
                  fontSize: typography.fontSize.sm,
                  color: colors.textSecondary,
                }}
              >
                <span
                  style={{
                    padding: `${spacing.xs} ${spacing.sm}`,
                    backgroundColor: colors.primaryLight,
                    color: colors.primary,
                    borderRadius: borderRadius.md,
                    fontSize: typography.fontSize.xs,
                    fontWeight: typography.fontWeight.semibold,
                  }}
                >
                  {batch.bank}
                </span>
              </td>
              <td
                style={{
                  padding: spacing.lg,
                  fontSize: typography.fontSize.sm,
                  color: colors.textSecondary,
                }}
              >
                {formatDate(batch.batch_date)}
              </td>
              <td
                style={{
                  padding: spacing.lg,
                  fontSize: typography.fontSize.sm,
                  fontWeight: typography.fontWeight.medium,
                  color: colors.textPrimary,
                  textAlign: 'center',
                }}
              >
                {batch.total_cheques ?? 0}
              </td>
              <td
                style={{
                  padding: spacing.lg,
                  fontSize: typography.fontSize.sm,
                  fontWeight: typography.fontWeight.bold,
                  textAlign: 'center',
                  color:
                    batch.accuracy_rate !== null && batch.accuracy_rate >= 99
                      ? colors.success
                      : batch.accuracy_rate !== null && batch.accuracy_rate >= 95
                      ? colors.warning
                      : colors.error,
                }}
              >
                {batch.accuracy_rate !== null ? `${batch.accuracy_rate}%` : 'N/A'}
              </td>
              <td style={{ padding: spacing.lg, textAlign: 'center' }}>
                {getStatusBadge(batch.status)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
