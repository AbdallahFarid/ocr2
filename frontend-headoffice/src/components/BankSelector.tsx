import type { Bank } from '../utils/api'
import { colors, typography, borderRadius, shadows, transitions } from '../styles/tokens'

const BANKS: Bank[] = ['QNB', 'FABMISR', 'BANQUE_MISR', 'CIB', 'AAIB', 'NBE']

type Props = {
  selected: Bank | null
  onSelect: (bank: Bank) => void
  disabled?: boolean
}

export default function BankSelector({ selected, onSelect, disabled }: Props) {
  return (
    <div>
      <label style={{
        display: 'block',
        fontSize: typography.fontSize.base,
        fontWeight: typography.fontWeight.semibold,
        color: colors.textSecondary,
        marginBottom: '12px',
        letterSpacing: '-0.01em',
      }}>
        Select Bank
      </label>
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(3, 1fr)',
        gap: '12px',
      }}>
        {BANKS.map((bank) => {
          const isSelected = selected === bank
          return (
            <button
              key={bank}
              onClick={() => !disabled && onSelect(bank)}
              disabled={disabled}
              style={{
                width: '180px',
                height: '54px',
                fontSize: typography.fontSize.base,
                fontWeight: typography.fontWeight.semibold,
                border: '2px solid',
                borderColor: isSelected ? colors.primary : colors.gray300,
                borderRadius: borderRadius.lg,
                backgroundColor: isSelected ? colors.primaryLight : colors.bgPrimary,
                color: isSelected ? colors.primary : colors.textSecondary,
                cursor: disabled ? 'not-allowed' : 'pointer',
                transition: `all ${transitions.base}`,
                opacity: disabled ? 0.5 : 1,
                boxShadow: isSelected ? shadows.md : shadows.sm,
                transform: 'scale(1)',
              }}
              onMouseEnter={(e) => {
                if (!disabled) {
                  e.currentTarget.style.borderColor = colors.primary
                  e.currentTarget.style.transform = 'scale(1.02)'
                  e.currentTarget.style.boxShadow = shadows.md
                }
              }}
              onMouseLeave={(e) => {
                if (!disabled) {
                  e.currentTarget.style.borderColor = isSelected ? colors.primary : colors.gray300
                  e.currentTarget.style.transform = 'scale(1)'
                  e.currentTarget.style.boxShadow = isSelected ? shadows.md : shadows.sm
                }
              }}
            >
              {bank}
            </button>
          )
        })}
      </div>
    </div>
  )
}
