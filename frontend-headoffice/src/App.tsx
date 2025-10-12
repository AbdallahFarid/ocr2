import { useState, useEffect } from 'react'
import BankSelector from './components/BankSelector'
import FileUploader from './components/FileUploader'
import ProcessButton from './components/ProcessButton'
import DownloadSection from './components/DownloadSection'
import ProgressIndicator from './components/ProgressIndicator'
import BacklogTable from './components/BacklogTable'
import {
  type Bank,
  uploadCheque,
  uploadZip,
  finalizeBatch,
  exportItems,
  downloadBlob,
} from './utils/api'
import { generateCorrelationId, saveQueue } from './utils/storage'
import { getErrorMessage, retryWithBackoff } from './utils/errorMessages'
import { colors, typography, spacing, borderRadius, shadows } from './styles/tokens'

type Stage = 'upload' | 'uploading' | 'processing' | 'complete'
type View = 'upload' | 'backlog'

function App() {
  const [view, setView] = useState<View>('upload')
  const [stage, setStage] = useState<Stage>('upload')
  const [selectedBank, setSelectedBank] = useState<Bank | null>(null)
  const [files, setFiles] = useState<File[]>([])
  const [processing, setProcessing] = useState(false)
  const [batchId, setBatchId] = useState<string>('')
  const [uploadedItems, setUploadedItems] = useState<Array<{ bank: string; file: string }>>([])
  const [downloading, setDownloading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  
  // Progress tracking
  const [uploadProgress, setUploadProgress] = useState({ current: 0, total: 0, percentage: 0 })
  const [uploadStartTime, setUploadStartTime] = useState<number>(0)
  const [estimatedTime, setEstimatedTime] = useState<number>(0)

  // Calculate estimated time remaining
  useEffect(() => {
    if (stage === 'uploading' && uploadProgress.current > 0) {
      const elapsed = Date.now() - uploadStartTime
      const avgTimePerFile = elapsed / uploadProgress.current
      const remaining = (uploadProgress.total - uploadProgress.current) * avgTimePerFile
      setEstimatedTime(Math.ceil(remaining / 1000))
    }
  }, [uploadProgress, uploadStartTime, stage])

  const handleProcess = async () => {
    if (!selectedBank || files.length === 0) return

    setProcessing(true)
    setError(null)
    setUploadStartTime(Date.now())

    try {
      const correlationId = generateCorrelationId()
      const items: Array<{ bank: string; file: string }> = []

      // Check if we have a ZIP file
      const zipFile = files.find((f) => f.name.toLowerCase().endsWith('.zip'))

      if (zipFile) {
        // Upload ZIP
        setStage('uploading')
        setUploadProgress({ current: 0, total: 1, percentage: 0 })

        const result = await retryWithBackoff(() =>
          uploadZip(selectedBank, zipFile, correlationId)
        )
        
        setUploadProgress({ current: 1, total: 1, percentage: 100 })
        items.push(...result.items)
      } else {
        // Upload individual files
        setStage('uploading')
        setUploadProgress({ current: 0, total: files.length, percentage: 0 })

        for (let i = 0; i < files.length; i++) {
          const file = files[i]
          
          const result = await retryWithBackoff(() =>
            uploadCheque(selectedBank, file, correlationId)
          )
          
          items.push({ bank: result.bank, file: result.file })
          
          const current = i + 1
          setUploadProgress({
            current,
            total: files.length,
            percentage: (current / files.length) * 100,
          })
        }
      }

      // Move to processing stage
      setStage('processing')

      // Save queue to localStorage
      saveQueue(correlationId, items.map((item) => ({
        ...item,
        reviewUrl: `/review/${item.bank}/${item.file}`,
      })))

      // Finalize batch
      const finalizeResult = await retryWithBackoff(() =>
        finalizeBatch(selectedBank, correlationId)
      )
      
      setBatchId(finalizeResult.batch)
      setUploadedItems(items)

      // Move to complete stage
      setStage('complete')
    } catch (err) {
      setError(getErrorMessage(err))
      console.error('Upload error:', err)
      setStage('upload')
    } finally {
      setProcessing(false)
    }
  }

  const handleDownload = async () => {
    if (uploadedItems.length === 0) return

    setDownloading(true)
    setError(null)

    try {
      const blob = await retryWithBackoff(() => exportItems(uploadedItems))
      const filename = `${batchId}.csv`
      downloadBlob(blob, filename)
    } catch (err) {
      setError(getErrorMessage(err))
      console.error('Download error:', err)
    } finally {
      setDownloading(false)
    }
  }

  const handleReset = () => {
    setStage('upload')
    setSelectedBank(null)
    setFiles([])
    setBatchId('')
    setUploadedItems([])
    setError(null)
    setView('upload')
  }

  const canProcess = selectedBank !== null && files.length > 0 && !processing

  return (
    <div style={{
      minHeight: '100vh',
      width: '100%',
      backgroundColor: colors.gray50,
      paddingTop: spacing['3xl'],
      paddingBottom: spacing['3xl'],
      display: 'flex',
      justifyContent: 'center',
      alignItems: 'flex-start',
    }}>
      <div style={{
        width: '100%',
        maxWidth: view === 'backlog' ? '1200px' : '600px',
        padding: spacing.xl,
        fontFamily: typography.fontFamily,
        transition: 'max-width 0.3s ease',
      }}>
        <div style={{
          textAlign: 'center',
          marginBottom: spacing['2xl'],
        }}>
          <h1 style={{
            fontSize: typography.fontSize['3xl'],
            fontWeight: typography.fontWeight.bold,
            color: colors.primary,
            marginBottom: spacing.md,
            letterSpacing: '-0.02em',
            lineHeight: typography.lineHeight.tight,
          }}>
            Cheque Verification Tool
          </h1>
          <p style={{
            fontSize: typography.fontSize.base,
            color: colors.textTertiary,
            marginTop: 0,
            marginBottom: 0,
            maxWidth: '400px',
            margin: '0 auto',
          }}>
            Upload cheques and download Excel for verification
          </p>
        </div>

        {/* View Toggle */}
        {stage === 'upload' && (
          <div style={{
            display: 'flex',
            justifyContent: 'center',
            gap: spacing.md,
            marginBottom: spacing.xl,
          }}>
            <button
              onClick={() => setView('upload')}
              style={{
                padding: `${spacing.md} ${spacing.xl}`,
                fontSize: typography.fontSize.base,
                fontWeight: typography.fontWeight.semibold,
                color: view === 'upload' ? colors.bgPrimary : colors.textSecondary,
                backgroundColor: view === 'upload' ? colors.primary : colors.bgPrimary,
                border: `2px solid ${view === 'upload' ? colors.primary : colors.gray200}`,
                borderRadius: borderRadius.lg,
                cursor: 'pointer',
                transition: 'all 0.2s',
              }}
            >
              New Upload
            </button>
            <button
              onClick={() => setView('backlog')}
              style={{
                padding: `${spacing.md} ${spacing.xl}`,
                fontSize: typography.fontSize.base,
                fontWeight: typography.fontWeight.semibold,
                color: view === 'backlog' ? colors.bgPrimary : colors.textSecondary,
                backgroundColor: view === 'backlog' ? colors.primary : colors.bgPrimary,
                border: `2px solid ${view === 'backlog' ? colors.primary : colors.gray200}`,
                borderRadius: borderRadius.lg,
                cursor: 'pointer',
                transition: 'all 0.2s',
              }}
            >
              Recent Batches
            </button>
          </div>
        )}

        {error && (
          <div style={{
            padding: spacing.lg,
            marginBottom: spacing.xl,
            backgroundColor: colors.errorLight,
            border: `2px solid ${colors.errorBorder}`,
            borderRadius: borderRadius.xl,
            animation: 'shake 0.5s',
            boxShadow: shadows.md,
          }}>
            <div style={{
              color: colors.error,
              fontSize: typography.fontSize.base,
              marginBottom: spacing.md,
              fontWeight: typography.fontWeight.medium,
            }}>
              {error}
            </div>
            <button
              onClick={() => {
                setError(null)
                if (stage === 'upload' && selectedBank && files.length > 0) {
                  handleProcess()
                }
              }}
              style={{
                fontSize: typography.fontSize.sm,
                fontWeight: typography.fontWeight.semibold,
                color: colors.error,
                backgroundColor: colors.bgPrimary,
                border: `2px solid ${colors.error}`,
                borderRadius: borderRadius.lg,
                padding: `${spacing.sm} ${spacing.lg}`,
                cursor: 'pointer',
                transition: 'all 0.2s',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.backgroundColor = colors.errorLight
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.backgroundColor = colors.bgPrimary
              }}
            >
              ↻ Retry
            </button>
            <style>{`
              @keyframes shake {
                0%, 100% { transform: translateX(0); }
                25% { transform: translateX(-10px); }
                75% { transform: translateX(10px); }
              }
            `}</style>
          </div>
        )}

        {/* Backlog View */}
        {stage === 'upload' && view === 'backlog' && (
          <BacklogTable />
        )}

        {/* Upload View */}
        {stage === 'upload' && view === 'upload' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: spacing.xl }}>
            <BankSelector
              selected={selectedBank}
              onSelect={setSelectedBank}
              disabled={processing}
            />

            <FileUploader
              files={files}
              onFilesChange={setFiles}
              disabled={processing}
            />

            <ProcessButton
              fileCount={files.length}
              disabled={!canProcess}
              loading={processing}
              onClick={handleProcess}
            />
          </div>
        )}

        {(stage === 'uploading' || stage === 'processing') && (
          <ProgressIndicator
            current={uploadProgress.current}
            total={uploadProgress.total}
            percentage={uploadProgress.percentage}
            stage={stage}
            estimatedTimeRemaining={estimatedTime}
          />
        )}

        {stage === 'complete' && (
          <DownloadSection
            batchId={batchId}
            onDownload={handleDownload}
            onReset={handleReset}
            downloading={downloading}
          />
        )}
      </div>
    </div>
  )
}

export default App
