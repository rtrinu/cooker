import { Link, Route, Routes } from 'react-router-dom'
import Reveal from './components/Reveal'
import SiteLayout from './components/SiteLayout'
import FinderPage from './pages/FinderPage'
import HomePage from './pages/HomePage'
import IngredientsPage from './pages/IngredientsPage'
import RecipeDetailPage from './pages/RecipeDetailPage'
import RecipesPage from './pages/RecipesPage'

const elsewhere = [
  { to: '/finder', label: 'The finder' },
  { to: '/recipes', label: 'All recipes' },
  { to: '/ingredients', label: 'The pantry' },
  { to: '/', label: 'The front page' },
]

function NotFoundPage() {
  return (
    <section className="bg-heat">
      <div className="mx-auto max-w-[1440px] px-5 py-20 md:px-10 md:py-32">
        <div className="grid gap-14 lg:grid-cols-12 lg:items-end lg:gap-8">
          <div className="lg:col-span-7">
            <Reveal>
              <p className="hero-rise font-display text-[clamp(7rem,26vw,22rem)] leading-[0.74] tracking-[-0.03em]">
                404
              </p>
            </Reveal>
            <Reveal delay={60}>
              <h1 className="hero-rise mt-8 max-w-3xl font-display text-[clamp(2.5rem,7vw,6rem)] leading-[0.9]">
                This page isn’t here.
              </h1>
            </Reveal>
            <Reveal delay={120}>
              <p className="mt-8 max-w-lg text-lead leading-snug text-ink/80">
                The recipes are still where you left them. Start from the finder
                or browse every recipe.
              </p>
            </Reveal>
          </div>

          <div className="lg:col-span-5">
            <ul className="space-y-1">
              {elsewhere.map((item, index) => (
                <li key={item.to}>
                  <Reveal delay={Math.min(index * 60, 240)}>
                    <Link
                      to={item.to}
                      className="group flex items-baseline justify-between gap-4 py-3 font-display text-[clamp(2rem,4vw,3.5rem)] leading-none transition-colors hover:text-field focus-visible:text-field"
                    >
                      {item.label}
                      <span
                        aria-hidden="true"
                        className="text-2xl transition-transform group-hover:translate-x-1"
                      >
                        →
                      </span>
                    </Link>
                  </Reveal>
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
        <Route path="ingredients" element={<IngredientsPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  )
}
