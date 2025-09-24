import React from 'react'
import ReactDOM from 'react-dom/client'
import { createBrowserRouter, RouterProvider, Navigate } from 'react-router-dom'
import ChequeReviewPage from './pages/review/[chequeId]'
import UploadPage from './pages/upload'
import BatchesPage from './pages/batches/index'
import BatchDetailPage from './pages/batches/[bank]/[name]'

const router = createBrowserRouter([
  { path: '/', element: <Navigate to="/upload" replace /> },
  { path: '/upload', element: <UploadPage /> },
  { path: '/batches', element: <BatchesPage /> },
  { path: '/batches/:bank/:name', element: <BatchDetailPage /> },
  // Backend mode (bank + fileId)
  { path: '/review/:bank/:fileId', element: <ChequeReviewPage /> },
  // Stub mode (only chequeId)
  { path: '/review/:chequeId', element: <ChequeReviewPage /> },
])

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <RouterProvider router={router} />
  </React.StrictMode>
)
