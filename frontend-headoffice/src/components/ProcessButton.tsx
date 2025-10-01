import { colors, typography, borderRadius, shadows, transitions } from '../styles/tokens'

type Props = {
  fileCount: number
  disabled: boolean
  loading: boolean
  onClick: () => void
}

export default function ProcessButton({ fileCount, disabled, loading, onClick }: Props) {
  const isDisabled = disabled || loading

  return (
    <button
      onClick={onClick}
      disabled={isDisabled}
      style={{
        width: '500px',
        height: '64px',
        fontSize: typography.fontSize.lg,
        fontWeight: typography.fontWeight.semibold,
        color: '#FFFFFF',
        backgroundColor: isDisabled ? colors.gray400 : colors.primary,
        border: 'none',
        borderRadius: borderRadius.xl,
        cursor: isDisabled ? 'not-allowed' : 'pointer',
        transition: `all ${transitions.base}`,
        opacity: isDisabled ? 0.6 : 1,
        boxShadow: isDisabled ? shadows.sm : shadows.md,
        transform: 'translateY(0)',
        letterSpacing: '-0.01em',
      }}
      onMouseEnter={(e) => {
        if (!isDisabled) {
          e.currentTarget.style.backgroundColor = colors.primaryHover
          e.currentTarget.style.transform = 'translateY(-2px)'
          e.currentTarget.style.boxShadow = shadows.lg
        }
      }}
      onMouseLeave={(e) => {
        if (!isDisabled) {
          e.currentTarget.style.backgroundColor = colors.primary
          e.currentTarget.style.transform = 'translateY(0)'
          e.currentTarget.style.boxShadow = shadows.md
        }
      }}
    >
      {loading ? (
        <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
          <span>Processing</span>
          <span style={{ animation: 'pulse 1.5s ease-in-out infinite' }}>...</span>
        </span>
      ) : (
        <span>Process {fileCount} Cheque{fileCount !== 1 ? 's' : ''}</span>
      )}
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }
      `}</style>
    </button>
  )
}
