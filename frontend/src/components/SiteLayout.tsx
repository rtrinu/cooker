import type { ReactNode } from 'react'
import { Link, NavLink, Outlet } from 'react-router-dom'
import { ButtonLink } from './Button'

const navItems = [
  { to: '/finder', label: 'Finder' },
  { to: '/recipes', label: 'Recipes' },
  { to: '/ingredients', label: 'Ingredients' },
]

function SiteHeader() {
  return (
    <header className="bg-heat">
      <div className="mx-auto flex max-w-[1440px] flex-wrap items-center justify-between gap-x-8 gap-y-3 px-5 py-5 md:px-10">
        <Link
          to="/"
          className="font-display text-3xl leading-none tracking-tight sm:text-4xl"
        >
          Cooker
        </Link>
        <nav
          aria-label="Main"
          className="flex flex-wrap items-center gap-x-5 gap-y-1 text-sm font-semibold sm:gap-x-7"
        >
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                isActive
                  ? 'underline decoration-2 underline-offset-4'
                  : 'hover:underline hover:decoration-2 hover:underline-offset-4'
              }
            >
              {item.label}
            </NavLink>
          ))}
          <a
            href="/api/docs"
            target="_blank"
            rel="noreferrer"
            className="hover:underline hover:decoration-2 hover:underline-offset-4"
          >
            API
          </a>
        </nav>
      </div>
    </header>
  )
}

function SiteFooter() {
  return (
    <footer className="on-ink bg-ink text-field">
      <div className="mx-auto max-w-[1440px] px-5 pt-20 md:px-10 md:pt-28">
        <div className="grid gap-14 lg:grid-cols-12 lg:gap-8">
          <div className="lg:col-span-8">
            <h2 className="font-display text-[clamp(3.25rem,8vw,7rem)] leading-[0.86] text-heat">
              Still hungry?
            </h2>
            <p className="mt-6 max-w-md text-lead leading-snug text-field/80">
              Tell Cooker what is in your kitchen and cook the closest
              match.
            </p>
            <ButtonLink to="/finder" tone="heat" className="mt-8">
              Open the finder
            </ButtonLink>
          </div>

          <div className="grid grid-cols-2 gap-8 text-sm lg:col-span-4">
            <div>
              <p className="font-semibold text-heat">Browse</p>
              <ul className="mt-3 space-y-2 text-field/80">
                <li>
                  <Link
                    to="/recipes"
                    className="hover:underline hover:decoration-2 hover:underline-offset-4"
                  >
                    All recipes
                  </Link>
                </li>
                <li>
                  <Link
                    to="/ingredients"
                    className="hover:underline hover:decoration-2 hover:underline-offset-4"
                  >
                    The pantry
                  </Link>
                </li>
                <li>
                  <Link
                    to="/finder"
                    className="hover:underline hover:decoration-2 hover:underline-offset-4"
                  >
                    Finder
                  </Link>
                </li>
              </ul>
            </div>
            <div className="lg:text-right">
              <p className="font-semibold text-heat">Elsewhere</p>
              <ul className="mt-3 space-y-2 text-field/80">
                <li>
                  <a
                    href="/api/docs"
                    target="_blank"
                    rel="noreferrer"
                    className="hover:underline hover:decoration-2 hover:underline-offset-4"
                  >
                    API reference
                  </a>
                </li>
                <li>
                  <a
                    href="/api/openapi.json"
                    target="_blank"
                    rel="noreferrer"
                    className="hover:underline hover:decoration-2 hover:underline-offset-4"
                  >
                    OpenAPI schema
                  </a>
                </li>
              </ul>
            </div>
          </div>
        </div>

        <div className="mt-20 flex flex-wrap items-end justify-between gap-4 text-sm text-field/60">
          <p>Cook from what you have. No accounts, no tracking.</p>
          <a
            href="#main"
            className="hover:underline hover:decoration-2 hover:underline-offset-4"
          >
            Back to top
          </a>
        </div>

        <div className="mt-6 overflow-hidden" aria-hidden="true">
          <p className="translate-y-[16%] whitespace-nowrap text-center font-display text-[30vw] leading-[0.74] tracking-[-0.02em] text-heat md:text-[26vw]">
            Cooker
          </p>
        </div>
      </div>
    </footer>
  )
}

export default function SiteLayout({ children }: { children?: ReactNode }) {
  return (
    <div className="flex min-h-svh flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:bg-ink focus:px-4 focus:py-3 focus:text-sm focus:font-semibold focus:text-heat"
      >
        Skip to content
      </a>
      <SiteHeader />
      <main id="main" className="flex-1">
        {children ?? <Outlet />}
      </main>
      <SiteFooter />
    </div>
  )
}
