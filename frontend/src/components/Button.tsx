import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { Link } from 'react-router-dom'

export type ButtonTone = 'ink' | 'heat'

const base =
  'inline-flex min-h-12 cursor-pointer items-center justify-center px-6 py-3 text-small font-semibold leading-none transition-[background-color,color,box-shadow] duration-150 disabled:cursor-not-allowed disabled:opacity-40'

const tones: Record<ButtonTone, string> = {
  // Keeps its edge on every surface: the inset ring stops the fill vanishing on white.
  ink: 'bg-ink text-heat hover:bg-field hover:text-ink hover:shadow-[inset_0_0_0_2px_var(--color-ink)]',
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
