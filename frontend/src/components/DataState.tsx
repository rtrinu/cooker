import type { ReactNode } from 'react'
import { Button } from './Button'

export function LoadingRows({
  label = 'Loading',
  rows = 5,
}: {
  label?: string
  rows?: number
}) {
  return (
    <div
      role="status"
      aria-label={`${label} (${rows} rows)`}
      className="flex items-center gap-4 py-16"
    >
      <span
        aria-hidden="true"
        className="h-4 w-4 animate-pulse bg-ink motion-reduce:animate-none"
      />
      <p className="font-display text-head">{label}</p>
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
    <div role="alert" className="on-ink bg-ink px-6 py-10 text-field md:px-10">
      <p className="font-display text-head text-heat">That request failed.</p>
      <p className="mt-3 max-w-xl text-body text-field/70">{message}</p>
      {onRetry && (
        <Button tone="heat" className="mt-6" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  )
}

export function EmptyState({
  children,
  title = 'Nothing here yet.',
}: {
  children: ReactNode
  title?: string
}) {
  return (
    <div className="bg-ember px-6 py-10 md:px-10">
      <p className="font-display text-head">{title}</p>
      <p className="mt-3 max-w-xl text-body text-ink/80">{children}</p>
    </div>
  )
}
