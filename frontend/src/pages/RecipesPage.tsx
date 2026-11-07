import { useQuery } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import { getRecipes, getStats } from '../api/client'
import { EmptyState, ErrorState, LoadingRows } from '../components/DataState'
import Pagination from '../components/Pagination'
import RecipeListItem from '../components/RecipeListItem'
import Reveal from '../components/Reveal'
import SearchForm from '../components/SearchForm'
import { taxonomyLabel } from '../lib/labels'

const PAGE_SIZE = 20

export default function RecipesPage() {
  const [params, setParams] = useSearchParams()
  const q = params.get('q') ?? ''
  const category = params.get('category') ?? ''
  const page = Math.max(1, Number(params.get('page') ?? '1') || 1)

  const stats = useQuery({ queryKey: ['stats'], queryFn: getStats })
  const recipes = useQuery({
    queryKey: ['recipes', { q, category, page }],
    queryFn: () => getRecipes({ q, category, page, pageSize: PAGE_SIZE }),
    placeholderData: (previous) => previous,
  })

  function updateParam(key: string, value: string) {
    const next = new URLSearchParams(params)
    if (value) {
      next.set(key, value)
    } else {
      next.delete(key)
    }
    if (key !== 'page') {
      next.delete('page')
    }
    setParams(next)
  }

  function clearFilters() {
    setParams(new URLSearchParams())
  }

  const hasFilters = Boolean(q || category)
  const total = recipes.data?.count

  return (
    <>
      <section className="bg-heat">
        <div className="mx-auto max-w-[1440px] px-5 pb-14 pt-10 md:px-10 md:pb-20 md:pt-14">
          <nav aria-label="Breadcrumb" className="text-sm text-ink/70">
            <Link
              to="/"
              className="font-semibold underline decoration-2 underline-offset-4 hover:decoration-4"
            >
              Home
            </Link>
            <span aria-hidden="true"> / </span>
            <span>Recipes</span>
          </nav>

          <div className="mt-8 grid gap-8 lg:grid-cols-12 lg:items-end lg:gap-8">
            <div className="lg:col-span-8">
              <h1 className="hero-rise font-display text-[clamp(3.5rem,11vw,10rem)] leading-[0.84] tracking-[-0.02em]">
                Recipes
              </h1>
              <p className="mt-8 max-w-xl text-lead leading-snug text-ink/80 md:mt-10">
                Search every recipe by name or category. Open one to see its
                ingredients, method and nutrition.
              </p>
            </div>

            <div className="lg:col-span-4 lg:pb-2">
              <p
                aria-live="polite"
                className="font-display text-[clamp(3rem,6vw,5rem)] leading-none tabular-nums"
              >
                {total ?? '—'}
              </p>
              <p className="mt-2 text-sm text-ink/70">
                {hasFilters ? 'matching recipes' : 'recipes to cook'}
              </p>
            </div>
          </div>
        </div>
      </section>

      <section className="bg-field py-10 md:py-14">
        <div className="mx-auto max-w-[1440px] px-5 md:px-10">
          <div className="grid gap-3 md:grid-cols-[1fr_280px]">
            <SearchForm
              key={q}
              initialValue={q}
              onSubmit={(value) => updateParam('q', value)}
              label="Search recipes"
              placeholder="Search by recipe name"
            />
            <div>
              <label htmlFor="category" className="sr-only">
                Filter by category
              </label>
              <select
                id="category"
                value={category}
                onChange={(event) => updateParam('category', event.target.value)}
                className="min-h-14 w-full bg-ink px-5 text-body text-heat outline-none focus-visible:outline-3 focus-visible:outline-offset-[-3px] focus-visible:outline-heat"
              >
                <option value="">Every category</option>
                {stats.data?.categories.map((item) => (
                  <option key={item.category} value={item.category}>
                    {taxonomyLabel(item.category)} ({item.count})
                  </option>
                ))}
              </select>
            </div>
          </div>

          {hasFilters && (
            <div className="mt-4 flex justify-end">
              <button
                type="button"
                onClick={clearFilters}
                className="min-h-11 text-sm font-semibold text-ink underline decoration-2 underline-offset-4 hover:decoration-4"
              >
                Clear filters
              </button>
            </div>
          )}

          <div className="mt-8">
            {recipes.isPending && <LoadingRows label="Loading recipes" rows={6} />}
            {recipes.isError && (
              <ErrorState
                message={(recipes.error as Error).message}
                onRetry={() => recipes.refetch()}
              />
            )}
            {recipes.data && recipes.data.items.length === 0 && (
              <EmptyState>
                No recipes match this search. Try a shorter phrase or clear the
                filters.
              </EmptyState>
            )}
            {recipes.data && recipes.data.items.length > 0 && (
              <ul className="space-y-1">
                {recipes.data.items.map((recipe, index) => (
                  <li key={recipe.id} className="min-w-0">
                    <Reveal delay={Math.min(index * 30, 240)}>
                      <RecipeListItem recipe={recipe} />
                    </Reveal>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {recipes.data && (
            <Pagination
              page={page}
              count={recipes.data.count}
              pageSize={PAGE_SIZE}
              onPageChange={(nextPage) => updateParam('page', String(nextPage))}
            />
          )}
        </div>
      </section>
    </>
  )
}
