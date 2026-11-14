import { Link, Route, Routes } from 'react-router-dom'
import SiteLayout from './components/SiteLayout'
import { usePageTitle } from './lib/usePageTitle'
import DataPage from './pages/DataPage'
import FinderPage from './pages/FinderPage'
import HomePage from './pages/HomePage'
import RecipeDetailPage from './pages/RecipeDetailPage'
import RecipesPage from './pages/RecipesPage'

const elsewhere = [
  { to: '/finder', label: 'The finder' },
  { to: '/recipes', label: 'All recipes' },
  { to: '/data', label: 'Data & licences' },
  { to: '/', label: 'The front page' },
]

function NotFoundPage() {
  usePageTitle('Page not found')

  return (
    <section className="bg-heat">
      <div className="shell section">
        <div className="grid gap-12 lg:grid-cols-12 lg:items-end lg:gap-8">
          <div className="lg:col-span-7">
            <p className="hero-rise font-display text-mega">404</p>
            <h1 className="mt-6 max-w-3xl font-display text-head">
              This page isn’t here.
            </h1>
            <p className="mt-6 max-w-lg text-lead text-ink/80">
              The recipes are still where you left them. Start from the finder
              or browse every recipe.
            </p>
          </div>

          <div className="lg:col-span-5">
            <ul>
              {elsewhere.map((item) => (
                <li key={item.to}>
                  <Link
                    to={item.to}
                    className="group flex min-h-14 items-baseline justify-between gap-4 py-3 font-display text-title transition-colors hover:text-field focus-visible:text-field"
                  >
                    {item.label}
                    <span
                      aria-hidden="true"
                      className="text-lead transition-transform group-hover:translate-x-1"
                    >
                      →
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </section>
  )
}

export default function App() {
  return (
    <Routes>
      <Route element={<SiteLayout />}>
        <Route index element={<HomePage />} />
        <Route path="finder" element={<FinderPage />} />
        <Route path="recipes" element={<RecipesPage />} />
        <Route path="recipes/:slug" element={<RecipeDetailPage />} />
        <Route path="data" element={<DataPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  )
}
