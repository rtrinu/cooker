import { Link, Route, Routes } from 'react-router-dom'
import SiteLayout from './components/SiteLayout'
import HomePage from './pages/HomePage'
import IngredientsPage from './pages/IngredientsPage'
import RecipeDetailPage from './pages/RecipeDetailPage'
import RecipesPage from './pages/RecipesPage'

function NotFoundPage() {
  return (
    <section className="mx-auto max-w-[1320px] px-5 pt-16 md:px-8">
      <h1 className="font-display text-[clamp(3rem,6vw,5.5rem)] leading-none tracking-[-0.04em]">
        Not found
      </h1>
      <p className="mt-4 max-w-lg text-muted">
        This page is not in the archive. The recipes are still where you left them.
      </p>
      <Link
        to="/recipes"
        className="mt-6 inline-block bg-accent px-5 py-3 text-sm text-paper transition-colors hover:bg-ink"
      >
        Browse recipes
      </Link>
    </section>
  )
}

export default function App() {
  return (
    <Routes>
      <Route element={<SiteLayout />}>
        <Route index element={<HomePage />} />
        <Route path="recipes" element={<RecipesPage />} />
        <Route path="recipes/:slug" element={<RecipeDetailPage />} />
        <Route path="ingredients" element={<IngredientsPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  )
}
