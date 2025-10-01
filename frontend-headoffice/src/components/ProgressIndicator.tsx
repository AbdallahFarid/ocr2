import { colors, typography, borderRadius, shadows, transitions, spacing } from '../styles/tokens'

type Props = {
  current: number
  total: number
  percentage: number
  stage: 'uploading' | 'processing'
  estimatedTimeRemaining?: number
}

export default function ProgressIndicator({
  current,
  total,
  percentage,
  stage,
  estimatedTimeRemaining,
}: Props) {
  const statusText = stage === 'uploading' ? 'Uploading' : 'Processing'
  
  return (
    <div style={{
      width: '500px',
      padding: spacing.xl,
      backgroundColor: colors.bgSecondary,
      borderRadius: borderRadius.xl,
      border: `1px solid ${colors.gray200}`,
      boxShadow: shadows.md,
      animation: 'fadeIn 0.3s ease-in-out',
    }}>
      {/* Progress Bar */}
      <div style={{
        width: '100%',
        height: '24px',
        backgroundColor: colors.gray200,
        borderRadius: borderRadius.full,
        overflow: 'hidden',
        marginBottom: spacing.md,
        boxShadow: shadows.inner,
      }}>
        <div
          style={{
            width: `${percentage}%`,
            height: '100%',
            backgroundColor: colors.primary,
            transition: `width ${transitions.slow}`,
            backgroundImage: 'linear-gradient(90deg, rgba(255,255,255,0.2) 0%, rgba(255,255,255,0) 100%)',
          }}
        />
      </div>

      {/* Status Text */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: spacing.sm,
      }}>
        <span style={{
          fontSize: typography.fontSize.base,
          color: colors.textSecondary,
          fontWeight: typography.fontWeight.medium,
        }}>
          {statusText} {current} of {total}
        </span>
        <span style={{
          fontSize: typography.fontSize.lg,
          color: colors.primary,
          fontWeight: typography.fontWeight.bold,
        }}>
          {Math.round(percentage)}%
        </span>
      </div>

      {/* Estimated Time */}
      {estimatedTimeRemaining !== undefined && estimatedTimeRemaining > 0 && (
        <div style={{
          fontSize: typography.fontSize.sm,
          color: colors.textTertiary,
          fontStyle: 'italic',
        }}>
          ~{estimatedTimeRemaining} seconds remaining
        </div>
      )}

      {/* Processing Spinner */}
      {stage === 'processing' && (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: spacing.sm,
          marginTop: spacing.md,
          fontSize: typography.fontSize.base,
          color: colors.primary,
          fontWeight: typography.fontWeight.medium,
        }}>
          <div
            style={{
              width: '18px',
              height: '18px',
              border: `2px solid ${colors.gray200}`,
              borderTopColor: colors.primary,
              borderRadius: borderRadius.full,
              animation: 'spin 1s linear infinite',
            }}
          />
          <span>Processing cheques...</span>
          <style>{`
            @keyframes spin {
              to { transform: rotate(360deg); }
            }
            @keyframes fadeIn {
              from { opacity: 0; transform: translateY(-10px); }
              to { opacity: 1; transform: translateY(0); }
            }
          `}</style>
        </div>
      )}
    </div>
  )
}
