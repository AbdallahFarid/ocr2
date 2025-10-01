import { useState } from 'react'
import { colors, typography, borderRadius, shadows, transitions, spacing } from '../styles/tokens'

type Props = {
  files: File[]
  onFilesChange: (files: File[]) => void
  disabled?: boolean
}

export default function FileUploader({ files, onFilesChange, disabled }: Props) {
  const [isDragOver, setIsDragOver] = useState(false)

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setIsDragOver(false)

    if (disabled) return

    const droppedFiles = Array.from(e.dataTransfer.files)
    onFilesChange([...files, ...droppedFiles])
  }

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    if (!disabled) {
      setIsDragOver(true)
    }
  }

  const handleDragLeave = () => {
    setIsDragOver(false)
  }

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const selectedFiles = Array.from(e.target.files)
      onFilesChange([...files, ...selectedFiles])
    }
  }

  const handleClear = () => {
    onFilesChange([])
  }

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return bytes + ' B'
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
  }

  const totalSize = files.reduce((sum, f) => sum + f.size, 0)

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
        Upload Cheques
      </label>

      <div
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={() => !disabled && document.getElementById('file-input')?.click()}
        style={{
          width: '500px',
          height: '200px',
          border: '2px dashed',
          borderColor: isDragOver ? colors.primary : colors.gray300,
          borderRadius: borderRadius.xl,
          backgroundColor: isDragOver ? colors.primaryLight : colors.bgSecondary,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          cursor: disabled ? 'not-allowed' : 'pointer',
          opacity: disabled ? 0.5 : 1,
          transition: `all ${transitions.base}`,
          boxShadow: isDragOver ? shadows.lg : shadows.sm,
        }}
      >
        <div style={{ textAlign: 'center', padding: spacing.xl }}>
          <div style={{
            fontSize: '48px',
            marginBottom: spacing.md,
            opacity: isDragOver ? 1 : 0.5,
            transition: `opacity ${transitions.base}`,
          }}>
            📁
          </div>
          <div style={{
            fontSize: typography.fontSize.lg,
            color: colors.textSecondary,
            marginBottom: spacing.sm,
            fontWeight: typography.fontWeight.medium,
          }}>
            Drag files or ZIP here, or click to browse
          </div>
          <div style={{
            fontSize: typography.fontSize.sm,
            color: colors.textMuted,
          }}>
            Supports JPG, PNG, TIFF, ZIP
          </div>
        </div>
      </div>

      <input
        id="file-input"
        type="file"
        multiple
        accept=".jpg,.jpeg,.png,.tiff,.tif,.zip"
        onChange={handleFileInput}
        disabled={disabled}
        style={{ display: 'none' }}
      />

      {files.length > 0 && (
        <div style={{ marginTop: spacing.lg }}>
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: spacing.md,
          }}>
            <span style={{
              fontSize: typography.fontSize.base,
              color: colors.textSecondary,
              fontWeight: typography.fontWeight.semibold,
            }}>
              {files.length} file{files.length !== 1 ? 's' : ''} selected ({formatFileSize(totalSize)})
            </span>
            <button
              onClick={handleClear}
              disabled={disabled}
              style={{
                fontSize: typography.fontSize.sm,
                color: colors.error,
                background: 'none',
                border: 'none',
                cursor: disabled ? 'not-allowed' : 'pointer',
                textDecoration: 'underline',
                fontWeight: typography.fontWeight.medium,
                transition: `color ${transitions.fast}`,
              }}
              onMouseEnter={(e) => !disabled && (e.currentTarget.style.color = colors.errorHover)}
              onMouseLeave={(e) => !disabled && (e.currentTarget.style.color = colors.error)}
            >
              Clear All
            </button>
          </div>

          <div style={{
            maxHeight: '150px',
            overflowY: 'auto',
            border: `1px solid ${colors.gray200}`,
            borderRadius: borderRadius.lg,
            padding: spacing.md,
            backgroundColor: colors.bgPrimary,
            boxShadow: shadows.sm,
          }}>
            {files.map((file, index) => (
              <div
                key={index}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  padding: `${spacing.sm} ${spacing.md}`,
                  fontSize: typography.fontSize.sm,
                  color: colors.textSecondary,
                  borderRadius: borderRadius.md,
                  transition: `background-color ${transitions.fast}`,
                  marginBottom: index < files.length - 1 ? spacing.xs : 0,
                }}
                onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = colors.bgSecondary)}
                onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
              >
                <span style={{
                  flex: 1,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                  fontWeight: typography.fontWeight.medium,
                }}>
                  {file.name}
                </span>
                <span style={{
                  marginLeft: spacing.lg,
                  color: colors.textTertiary,
                  fontFamily: typography.fontFamilyMono,
                  fontSize: typography.fontSize.xs,
                }}>
                  {formatFileSize(file.size)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
