// Map technical errors to user-friendly messages

export function getErrorMessage(error: unknown): string {
  if (!(error instanceof Error)) {
    return 'An unexpected error occurred. Please try again.'
  }

  const message = error.message.toLowerCase()

  // Network errors
  if (message.includes('failed to fetch') || message.includes('network')) {
    return 'Connection lost. Please check your internet connection and try again.'
  }

  // Timeout errors
  if (message.includes('timeout')) {
    return 'Request timed out. The server is taking too long to respond.'
  }

  // Upload errors
  if (message.includes('upload failed')) {
    if (message.includes('413') || message.includes('too large')) {
      return 'File is too large. Maximum size is 20MB per file.'
    }
    if (message.includes('415') || message.includes('unsupported')) {
      return 'Unsupported file type. Please upload JPG, PNG, TIFF, or ZIP files.'
    }
    if (message.includes('400')) {
      return 'Invalid file format. Please check your files and try again.'
    }
    return 'Upload failed. Please try again.'
  }

  // Processing errors
  if (message.includes('finalize failed')) {
    return 'Failed to complete batch processing. Please try again.'
  }

  // Export errors
  if (message.includes('export failed')) {
    return 'Failed to generate Excel file. Please try again.'
  }

  // Server errors
  if (message.includes('500') || message.includes('502') || message.includes('503')) {
    return 'Server error. Please try again in a few moments.'
  }

  if (message.includes('404')) {
    return 'Resource not found. Please refresh the page.'
  }

  // Default fallback
  return `Error: ${error.message}`
}

export function shouldRetry(error: unknown): boolean {
  if (!(error instanceof Error)) return false

  const message = error.message.toLowerCase()

  // Retry on network errors
  if (message.includes('failed to fetch') || message.includes('network')) {
    return true
  }

  // Retry on timeout
  if (message.includes('timeout')) {
    return true
  }

  // Retry on server errors (5xx)
  if (message.includes('500') || message.includes('502') || message.includes('503')) {
    return true
  }

  // Don't retry on client errors (4xx)
  return false
}

export async function retryWithBackoff<T>(
  fn: () => Promise<T>,
  maxRetries: number = 3,
  initialDelay: number = 1000
): Promise<T> {
  let lastError: unknown

  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      return await fn()
    } catch (error) {
      lastError = error

      if (!shouldRetry(error)) {
        throw error
      }

      if (attempt < maxRetries - 1) {
        const delay = initialDelay * Math.pow(2, attempt) // Exponential backoff
        await new Promise((resolve) => setTimeout(resolve, delay))
      }
    }
  }

  throw lastError
}
