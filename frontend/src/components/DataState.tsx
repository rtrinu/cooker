import type { ReactNode } from 'react'

export function LoadingRows({ label = 'Loading', rows = 5 }: { label?: string; rows?: number }) {
  return (
    <div role="status" aria-label={label} className="space-y-2">
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className="bg-surface px-5 py-6">
          <div className="h-5 w-2/3 bg-surface-deep" />
          <div className="mt-3 h-3 w-1/3 bg-surface-deep" />
        </div>
      ))}
      <span className="sr-only">{label}</span>
    </div>
  )
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string
  onRetry?: () => void
}) {
  return (
    <div role="alert" className="bg-surface px-5 py-8">
      <p className="font-display text-2xl">The archive did not answer.</p>
      <p className="mt-2 text-sm text-muted">{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-5 bg-accent px-4 py-2 text-sm text-paper transition-colors hover:bg-ink"
        >
          Try again
        </button>
      )}
    </div>
  )
}

export function EmptyState({ children }: { children: ReactNode }) {
  return (
    <div className="bg-surface px-5 py-10">
      <p className="font-display text-2xl">Nothing here yet.</p>
      <p className="mt-2 max-w-lg text-sm text-muted">{children}</p>
    </div>
  )
}
