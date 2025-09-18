import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import ReviewFields from '../ReviewFields'

describe('ReviewFields', () => {
  it('shows field values and confidence bars', () => {
    render(
      <ReviewFields
        fields={{
          amount_numeric: {
            field_conf: 1.0,
            parse_ok: true,
            parse_norm: '123.45',
            ocr_conf: 1.0,
            loc_conf: 1.0,
          },
          date: {
            field_conf: 0.9,
            parse_ok: true,
            parse_norm: '2025-01-01',
            ocr_conf: 0.9,
            loc_conf: 0.95,
          },
        }}
      />
    )
    expect(screen.getByText('amount numeric')).toBeInTheDocument()
    expect(screen.getByText('123.45')).toBeInTheDocument()
    expect(screen.getByText('2025-01-01')).toBeInTheDocument()
  })
})
