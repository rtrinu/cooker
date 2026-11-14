import {
  useEffect,
  useRef,
  type ReactNode,
} from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { ButtonLink } from './Button'

const navItems = [
  { to: '/finder', label: 'Finder' },
  { to: '/recipes', label: 'Recipes' },
]

const linkClass =
  'inline-flex min-h-11 items-center hover:underline hover:decoration-2 hover:underline-offset-4'

function SiteHeader() {
  return (
    <header className="bg-heat">
      <div className="shell flex flex-wrap items-center justify-between gap-x-8 gap-y-2 py-4">
        <Link
          to="/"
          className="font-display text-title leading-none"
        >
          Cooker
        </Link>
        <nav
          aria-label="Main"
          className="-mx-1 flex flex-wrap items-center gap-x-4 text-small font-semibold sm:gap-x-6"
        >
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `inline-flex min-h-11 items-center px-1 ${
                  isActive
                    ? 'underline decoration-2 underline-offset-4'
                    : 'hover:underline hover:decoration-2 hover:underline-offset-4'
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
          <a
            href="/api/docs"
            target="_blank"
            rel="noreferrer"
            className="inline-flex min-h-11 items-center px-1 hover:underline hover:decoration-2 hover:underline-offset-4"
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
      <div className="shell pt-16 md:pt-24">
        <div className="grid gap-12 lg:grid-cols-12 lg:gap-8">
          <div className="lg:col-span-8">
            <h2 className="font-display text-head text-heat">
              Still hungry?
            </h2>
            <p className="mt-5 max-w-md text-lead text-field/80">
              Tell Cooker what is in your kitchen and cook the closest match.
            </p>
            <ButtonLink to="/finder" tone="heat" className="mt-7">
              Open the finder
            </ButtonLink>
          </div>

          <div className="grid grid-cols-2 gap-8 text-small lg:col-span-4">
            <div>
              <p className="font-semibold text-heat">Browse</p>
              <ul className="mt-2 text-field/80">
                <li>
                  <Link to="/recipes" className={linkClass}>
                    All recipes
                  </Link>
                </li>
                <li>
                  <Link to="/finder" className={linkClass}>
                    Finder
                  </Link>
                </li>
              </ul>
            </div>
            <div className="lg:text-right">
              <p className="font-semibold text-heat">Elsewhere</p>
              <ul className="mt-2 text-field/80">
                <li>
                  <Link to="/data" className={`${linkClass} lg:justify-end`}>
                    Data &amp; licences
                  </Link>
                </li>
                <li>
                  <a
                    href="/api/docs"
                    target="_blank"
                    rel="noreferrer"
                    className={`${linkClass} lg:justify-end`}
                  >
                    API reference
                  </a>
                </li>
                <li>
                  <a
                    href="/api/openapi.json"
                    target="_blank"
                    rel="noreferrer"
                    className={`${linkClass} lg:justify-end`}
                  >
                    OpenAPI schema
                  </a>
                </li>
              </ul>
            </div>
          </div>
        </div>

        <div className="mt-16 flex flex-wrap items-end justify-between gap-4 text-small text-field/60">
          <p>Cook from what you have. No accounts, no tracking.</p>
          <a href="#main" className={linkClass}>
            Back to top
          </a>
        </div>

        <div className="mt-6 overflow-hidden" aria-hidden="true">
          <p className="wordmark translate-y-[16%] whitespace-nowrap text-center font-display text-heat">
            Cooker
          </p>
        </div>
      </div>
    </footer>
  )
}

function RouteMain({ children }: { children?: ReactNode }) {
  const { pathname } = useLocation()
  const mainRef = useRef<HTMLElement>(null)
  const firstRender = useRef(true)

  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: 'auto' })
    if (firstRender.current) {
      firstRender.current = false
      return
    }
    // Move focus with the page so keyboard and screen-reader users land on the new content.
    mainRef.current?.focus({ preventScroll: true })
  }, [pathname])

  return (
    <main
      key={pathname}
      id="main"
      ref={mainRef}
      tabIndex={-1}
      className="page-in flex-1 outline-none"
    >
      {children ?? <Outlet />}
    </main>
  )
}

export default function SiteLayout({ children }: { children?: ReactNode }) {
  return (
    <div className="flex min-h-svh flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:bg-ink focus:px-4 focus:py-3 focus:text-small focus:font-semibold focus:text-heat"
      >
        Skip to content
      </a>
      <SiteHeader />
      <RouteMain>{children}</RouteMain>
      <SiteFooter />
    </div>
  )
}
