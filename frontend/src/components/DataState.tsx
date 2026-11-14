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
    <div role="status" aria-live="polite" className="py-3">
      <span className="sr-only">{label}</span>
      <div aria-hidden="true" className="space-y-1">
        {Array.from({ length: rows }, (_, index) => (
          <div key={index} className="flex items-center gap-6 px-4 py-5">
            <span className="h-6 w-2/3 bg-ink/10 motion-safe:animate-pulse" />
            <span className="ml-auto h-4 w-16 bg-ink/10 motion-safe:animate-pulse" />
          </div>
        ))}
      </div>
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
    <div className="bg-heat px-6 py-10 md:px-10">
      <p className="font-display text-head">{title}</p>
      <p className="mt-3 max-w-xl text-body text-ink/80">{children}</p>
    </div>
  )
}
