import React from 'react'
import type { FieldRecord } from '../types/review'

type Props = {
  fields: Record<string, FieldRecord>
  order?: string[]
  selected?: string
  threshold?: number
}

function ConfBar({ conf }: { conf: number }) {
  const pct = Math.round(conf * 100)
  return (
    <div
      style={{ background: '#eee', borderRadius: 4, height: 8, width: '100%' }}
      aria-label={`confidence-${pct}`}
    >
      <div
        style={{
          width: `${pct}%`,
          height: '100%',
          background: conf >= 0.995 ? '#16a34a' : '#f59e0b',
          borderRadius: 4,
          transition: 'width 200ms',
        }}
      />
    </div>
  )
}

export default function ReviewFields({ fields, order, selected, threshold = 0.995 }: Props) {
  const keys = React.useMemo(() => order ?? Object.keys(fields), [order, fields])
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {keys.map((name) => {
        const rec = fields[name]
        if (!rec) return null
        const isArabicLang = rec.ocr_lang === 'ar'
        const tentative = rec.parse_norm ?? rec.ocr_text ?? ''
        const isArabic = isArabicLang || /[\u0600-\u06FF]/.test(String(tentative))
        // Normalize helper (NFKC + strip bidi controls)
        const norm = (s: any) => {
          let v = String(s ?? '')
          try {
            v = v.normalize('NFKC')
          } catch {}
          return v.replace(/[\u200B\u200C\u200E\u200F\u202A-\u202E\u2066-\u2069]/g, '')
        }
        // For Arabic: strictly use OCR logical text (fallback to parse_norm only if OCR empty)
        const value = isArabic ? norm(rec.ocr_text ?? rec.parse_norm ?? '') : norm(tentative)
        const valid = rec.validation?.ok ?? true
        const code = rec.validation?.code ?? 'UNKNOWN'
        const low =
          typeof rec.meets_threshold === 'boolean'
            ? !rec.meets_threshold
            : (rec.field_conf ?? 0) < threshold
        const isSelected = selected === name
        return (
          <div
            key={name}
            id={`field-${name}`}
            tabIndex={isSelected ? 0 : -1}
            role="region"
            data-field={name}
            data-low={low ? 'true' : 'false'}
            data-selected={isSelected ? 'true' : 'false'}
            style={{
              border: `2px solid ${isSelected ? '#3b82f6' : low ? '#f59e0b' : '#e5e7eb'}`,
              borderRadius: 8,
              padding: 12,
              outline: 'none',
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: 8,
              }}
            >
              <strong style={{ textTransform: 'capitalize' }}>{name.replace(/_/g, ' ')}</strong>
              <span style={{ fontSize: 12, color: valid ? '#16a34a' : '#dc2626' }}>
                {valid ? code : `ERR: ${code}`}
              </span>
            </div>
            <div
              style={{
                marginBottom: 8,
                color: '#111827',
                direction: isArabic ? 'rtl' : 'ltr',
                unicodeBidi: 'isolate' as any,
                textAlign: isArabic ? 'right' : 'left',
                fontFamily: isArabic
                  ? "'Noto Naskh Arabic','Noto Sans Arabic','Segoe UI','Arial',sans-serif"
                  : undefined,
              }}
              dir={isArabic ? 'rtl' : 'ltr'}
              lang={isArabic ? 'ar' : undefined}
            >
              <bdi>{value}</bdi>
            </div>
            <ConfBar conf={rec.field_conf} />
            <div style={{ marginTop: 6, fontSize: 12, color: '#6b7280' }}>
              ocr: {rec.ocr_conf?.toFixed(3) ?? '-'} | loc: {rec.loc_conf?.toFixed(3) ?? '-'} |
              parse: {rec.parse_ok ? 'ok' : 'fail'}
            </div>
          </div>
        )
      })}
    </div>
  )
}
