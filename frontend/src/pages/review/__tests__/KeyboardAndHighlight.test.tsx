import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import * as api from '../../../utils/api'
import ChequeReviewPage from '../[chequeId]'

const mockItem = {
  bank: 'FABMISR',
  file: 'TEST-1',
  decision: {
    decision: 'review',
    stp: false,
    overall_conf: 0.9,
    low_conf_fields: ['date'],
    reasons: [],
  },
  // Set confidences so date is low (< 0.995) and amount is high (=1.0)
  fields: {
    date: { field_conf: 0.99, parse_ok: true, parse_norm: '2025-01-01' },
    amount_numeric: { field_conf: 1.0, parse_ok: true, parse_norm: '100.00' },
  },
} as any

describe('Keyboard & Highlighting', () => {
  it('supports navigation, filter, and edit hotkeys; highlights low-confidence', async () => {
    vi.spyOn(api, 'getReviewItem').mockResolvedValueOnce(mockItem)

    render(
      <MemoryRouter initialEntries={[{ pathname: '/review/TEST-1' }] as any}>
        <Routes>
          <Route path="/review/:chequeId" element={<ChequeReviewPage />} />
        </Routes>
      </MemoryRouter>
    )

    // Wait for fields pane
    await waitFor(() => expect(screen.getByLabelText('fields-pane')).toBeInTheDocument())

    // Initially select first field (date)
    await waitFor(() => expect(document.getElementById('field-date')).toBeTruthy())
    const dateEl = document.getElementById('field-date') as HTMLElement
    expect(dateEl).toBeTruthy()
    expect(dateEl.getAttribute('data-selected')).toBe('true')
    expect(dateEl.getAttribute('data-low')).toBe('true')

    // j -> next (amount)
    fireEvent.keyDown(window, { key: 'j' })
    const amountEl = document.getElementById('field-amount_numeric') as HTMLElement
    expect(amountEl.getAttribute('data-selected')).toBe('true')

    // k -> prev (date)
    fireEvent.keyDown(window, { key: 'k' })
    expect(dateEl.getAttribute('data-selected')).toBe('true')

    // f -> filter low only (amount should disappear)
    fireEvent.keyDown(window, { key: 'f' })
    expect(document.getElementById('field-amount_numeric')).toBeNull()

    // e -> enter edit mode (input appears)
    fireEvent.keyDown(window, { key: 'e' })
    const input = await screen.findByLabelText(/Edit date:/i)
    expect((input as HTMLInputElement).value).toBe('2025-01-01')

    // Esc -> exit edit mode
    fireEvent.keyDown(window, { key: 'Escape' })
  })
})
