import type { ReactNode } from 'react'
import { Link, NavLink, Outlet } from 'react-router-dom'

function PotMark({ className = '' }: { className?: string }) {
  return (
    <svg
      aria-hidden="true"
      className={className}
      viewBox="0 0 32 32"
      fill="none"
    >
      <path
        d="M9.5 12.5h13v8.2a4.3 4.3 0 0 1-4.3 4.3h-4.4a4.3 4.3 0 0 1-4.3-4.3v-8.2Z"
        fill="currentColor"
      />
      <rect x="6.5" y="10.4" width="19" height="2.2" rx="1.1" fill="currentColor" />
      <rect x="13.6" y="6.5" width="4.8" height="2.2" rx="1.1" fill="currentColor" />
      <path d="M4.5 15.5h3M24.5 15.5h3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  )
}

const navItems = [
  { to: '/recipes', label: 'Recipes' },
  { to: '/ingredients', label: 'Ingredients' },
]

function SiteHeader() {
  return (
    <header className="bg-surface">
      <div className="mx-auto flex max-w-[1320px] items-center justify-between gap-6 px-5 py-5 md:px-8">
        <Link to="/" className="flex items-center gap-3">
          <PotMark className="h-7 w-7 text-accent" />
          <span className="font-display text-xl tracking-tight">
            Cooker <span className="text-muted">Archive</span>
          </span>
        </Link>
        <nav aria-label="Main" className="flex items-center gap-5 text-sm sm:gap-7">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `transition-colors hover:text-accent ${
                  isActive ? 'text-accent' : 'text-ink/75'
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
            className="text-ink/75 transition-colors hover:text-accent"
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
    <footer className="mx-auto mt-24 max-w-[1320px] px-5 pb-12 md:px-8">
      <div className="bg-ink px-6 py-10 text-paper md:px-10 md:py-12">
        <div className="grid gap-10 md:grid-cols-[1.6fr_1fr]">
          <div>
            <p className="font-display text-4xl leading-none tracking-tight md:text-5xl">
              Cooker Archive
            </p>
            <p className="mt-4 max-w-md text-base leading-relaxed text-paper/70">
              A read-only archive of historical American cookery. Recipes keep their source,
              year and attribution so the original can always be checked.
            </p>
          </div>
          <div className="grid grid-cols-1 gap-6 text-sm sm:grid-cols-2 md:grid-cols-1">
            <div>
              <p className="text-paper/50">Sources</p>
              <ul className="mt-2 space-y-1">
                <li>
                  <a
                    href="https://www.gutenberg.org/"
                    target="_blank"
                    rel="noreferrer"
                    className="underline decoration-paper/30 underline-offset-4 hover:decoration-paper"
                  >
                    Project Gutenberg
                  </a>
                </li>
                <li>
                  <a
                    href="https://github.com/"
                    target="_blank"
                    rel="noreferrer"
                    className="underline decoration-paper/30 underline-offset-4 hover:decoration-paper"
                  >
                    OpenRecipeArchive
                  </a>
                </li>
              </ul>
            </div>
            <div>
              <p className="text-paper/50">Developers</p>
              <ul className="mt-2 space-y-1">
                <li>
                  <a
                    href="/api/docs"
                    target="_blank"
                    rel="noreferrer"
                    className="underline decoration-paper/30 underline-offset-4 hover:decoration-paper"
                  >
                    API reference
                  </a>
                </li>
                <li>
                  <a
                    href="/api/openapi.json"
                    target="_blank"
                    rel="noreferrer"
                    className="underline decoration-paper/30 underline-offset-4 hover:decoration-paper"
                  >
                    OpenAPI schema
                  </a>
                </li>
              </ul>
            </div>
          </div>
        </div>
        <p className="mt-10 max-w-[64ch] text-sm leading-relaxed text-paper/50">
          Images: “Cooking in Camp” (1861), American Cookery (1915) via Internet Archive Book
          Images, and Daniel Shoemaker farmhouse kitchen (HABS), all public domain; “Brown Betty”
          by KaMan, CC BY-SA 4.0; apple bread pudding by stu_spivack, CC BY-SA 2.0. All via
          Wikimedia Commons.
        </p>
      </div>
    </footer>
  )
}

export default function SiteLayout({ children }: { children?: ReactNode }) {
  return (
    <div className="flex min-h-svh flex-col">
      <SiteHeader />
      <main className="flex-1">{children ?? <Outlet />}</main>
      <SiteFooter />
    </div>
  )
}
