import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { Link } from 'react-router-dom'

export type ButtonTone = 'ink' | 'heat'

const base =
  'inline-flex min-h-12 cursor-pointer items-center justify-center px-6 py-3 text-sm font-semibold leading-none transition-colors disabled:cursor-not-allowed disabled:opacity-40'

const tones: Record<ButtonTone, string> = {
  ink: 'bg-ink text-heat hover:bg-field hover:text-ink',
  heat: 'bg-heat text-ink hover:bg-field hover:text-ink',
}

function classes(tone: ButtonTone, className: string) {
  return `${base} ${tones[tone]} ${className}`
}

export function Button({
  tone = 'ink',
  className = '',
  type = 'button',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { tone?: ButtonTone }) {
  return <button type={type} className={classes(tone, className)} {...props} />
}

export function ButtonLink({
  to,
  tone = 'ink',
  className = '',
  children,
}: {
  to: string
  tone?: ButtonTone
  className?: string
  children: ReactNode
}) {
  return (
    <Link to={to} className={classes(tone, className)}>
      {children}
    </Link>
  )
}

export function ButtonAnchor({
  href,
  tone = 'ink',
  className = '',
  children,
}: {
  href: string
  tone?: ButtonTone
  className?: string
  children: ReactNode
}) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className={classes(tone, className)}
    >
      {children}
    </a>
  )
}
