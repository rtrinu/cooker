import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

type PageHeroProps = {
  crumb: string
  title: string
  intro: ReactNode
  children?: ReactNode
}

export default function PageHero({
  crumb,
  title,
  intro,
  children,
}: PageHeroProps) {
  return (
    <>
      <nav aria-label="Breadcrumb" className="text-small text-ink/80">
        <Link
          to="/"
          className="inline-flex min-h-11 items-center font-semibold underline decoration-2 underline-offset-4 hover:decoration-4"
        >
          Home
        </Link>
        <span aria-hidden="true"> / </span>
        <span>{crumb}</span>
      </nav>

      <header className="mt-6 max-w-4xl">
        <h1 className="hero-rise font-display text-poster">{title}</h1>
        <p className="mt-6 max-w-2xl text-lead text-ink/80">{intro}</p>
        {children}
      </header>
    </>
  )
}
