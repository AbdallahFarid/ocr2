import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import * as api from '../../../utils/api'
import ChequeReviewPage from '../[chequeId]'

describe('ChequeReviewPage', () => {
  it('renders two-pane layout and loads data', async () => {
    vi.spyOn(api, 'getReviewItem').mockResolvedValueOnce({
      bank: 'FABMISR',
      file: 'TEST-1',
      decision: {
        decision: 'review',
        stp: false,
        overall_conf: 0.9,
        low_conf_fields: [],
        reasons: [],
      },
      fields: {
        date: { field_conf: 0.9, parse_ok: true, parse_norm: '2025-01-01' },
      },
    } as any)

    render(
      <MemoryRouter initialEntries={[{ pathname: '/review/TEST-1' }] as any}>
        <Routes>
          <Route path="/review/:chequeId" element={<ChequeReviewPage />} />
        </Routes>
      </MemoryRouter>
    )

    await waitFor(() => expect(screen.getByLabelText('fields-pane')).toBeInTheDocument())
    expect(screen.getByText(/Cheque Reviewer/i)).toBeInTheDocument()
    expect(screen.getByText('FABMISR')).toBeInTheDocument()
    expect(screen.getByText('TEST-1')).toBeInTheDocument()
    expect(screen.getByText('2025-01-01')).toBeInTheDocument()
  })
})
