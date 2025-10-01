import { colors, typography, borderRadius, shadows, transitions, spacing } from '../styles/tokens'

type Props = {
  batchId: string
  onDownload: () => void
  onReset: () => void
  downloading: boolean
}

export default function DownloadSection({ batchId, onDownload, onReset, downloading }: Props) {
  return (
    <div style={{
      padding: spacing['2xl'],
      backgroundColor: colors.successLight,
      border: `2px solid ${colors.successBorder}`,
      borderRadius: borderRadius['2xl'],
      textAlign: 'center',
      boxShadow: shadows.lg,
      animation: 'fadeInScale 0.4s ease-out',
    }}>
      <div style={{
        fontSize: '64px',
        marginBottom: spacing.md,
        animation: 'checkmarkBounce 0.6s ease-out',
      }}>
        ✓
      </div>
      <div style={{
        fontSize: typography.fontSize['2xl'],
        fontWeight: typography.fontWeight.bold,
        color: colors.success,
        marginBottom: spacing.md,
        letterSpacing: '-0.02em',
      }}>
        Excel file ready
      </div>
      <div style={{
        fontSize: typography.fontSize.sm,
        color: colors.textSecondary,
        marginBottom: spacing.xl,
        fontFamily: typography.fontFamilyMono,
        backgroundColor: colors.gray100,
        padding: `${spacing.sm} ${spacing.lg}`,
        borderRadius: borderRadius.lg,
        display: 'inline-block',
        border: `1px solid ${colors.gray200}`,
      }}>
        Batch: {batchId}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: spacing.md, alignItems: 'center' }}>
        <button
          onClick={onDownload}
          disabled={downloading}
          style={{
            width: '500px',
            height: '64px',
            fontSize: typography.fontSize.lg,
            fontWeight: typography.fontWeight.semibold,
            color: '#FFFFFF',
            backgroundColor: downloading ? colors.gray400 : colors.success,
            border: 'none',
            borderRadius: borderRadius.xl,
            cursor: downloading ? 'wait' : 'pointer',
            transition: `all ${transitions.base}`,
            boxShadow: downloading ? shadows.sm : shadows.md,
            transform: 'translateY(0)',
            letterSpacing: '-0.01em',
          }}
          onMouseEnter={(e) => {
            if (!downloading) {
              e.currentTarget.style.backgroundColor = colors.successHover
              e.currentTarget.style.transform = 'translateY(-2px)'
              e.currentTarget.style.boxShadow = shadows.lg
            }
          }}
          onMouseLeave={(e) => {
            if (!downloading) {
              e.currentTarget.style.backgroundColor = colors.success
              e.currentTarget.style.transform = 'translateY(0)'
              e.currentTarget.style.boxShadow = shadows.md
            }
          }}
        >
          {downloading ? 'Downloading...' : 'Download Excel'}
        </button>

        <button
          onClick={onReset}
          disabled={downloading}
          style={{
            width: '500px',
            height: '54px',
            fontSize: typography.fontSize.base,
            fontWeight: typography.fontWeight.medium,
            color: colors.textSecondary,
            backgroundColor: colors.bgPrimary,
            border: `2px solid ${colors.gray300}`,
            borderRadius: borderRadius.xl,
            cursor: downloading ? 'not-allowed' : 'pointer',
            transition: `all ${transitions.base}`,
            boxShadow: shadows.sm,
          }}
          onMouseEnter={(e) => {
            if (!downloading) {
              e.currentTarget.style.backgroundColor = colors.bgSecondary
              e.currentTarget.style.borderColor = colors.gray400
            }
          }}
          onMouseLeave={(e) => {
            if (!downloading) {
              e.currentTarget.style.backgroundColor = colors.bgPrimary
              e.currentTarget.style.borderColor = colors.gray300
            }
          }}
        >
          Process Another Batch
        </button>
      </div>
      <style>{`
        @keyframes fadeInScale {
          from {
            opacity: 0;
            transform: scale(0.95);
          }
          to {
            opacity: 1;
            transform: scale(1);
          }
        }
        @keyframes checkmarkBounce {
          0% { transform: scale(0); }
          50% { transform: scale(1.1); }
          100% { transform: scale(1); }
        }
      `}</style>
    </div>
  )
}
