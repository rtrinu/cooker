import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { getRecipes, getStats } from '../api/client'
import { EmptyState, ErrorState, LoadingRows } from '../components/DataState'
import Pagination from '../components/Pagination'
import RecipeListItem from '../components/RecipeListItem'
import SearchForm from '../components/SearchForm'

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

  return (
    <section className="mx-auto max-w-[1320px] px-5 pt-12 md:px-8 md:pt-16">
      <div className="flex flex-wrap items-end justify-between gap-6">
        <div>
          <h1 className="font-display text-[clamp(3rem,6vw,5.5rem)] leading-none tracking-[-0.04em]">
            Recipes
          </h1>
          <p className="mt-3 max-w-xl text-muted">
            {recipes.data
              ? `${recipes.data.count} ${
                  recipes.data.count === 1 ? 'recipe' : 'recipes'
                } transcribed from public-domain sources.`
              : 'Transcribed from public-domain sources.'}
          </p>
        </div>
      </div>

      <div className="mt-9 grid gap-3 md:grid-cols-[1fr_260px]">
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
            className="w-full bg-surface px-4 py-3 text-base outline-none focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent"
          >
            <option value="">Every category</option>
            {stats.data?.categories.map((item) => (
              <option key={item.category} value={item.category}>
                {item.category.replaceAll('-', ' ')} ({item.count})
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-sm text-muted">
        <p aria-live="polite">
          {q && (
            <>
              Results for <span className="text-ink">“{q}”</span>
              {recipes.data ? ` — ${recipes.data.count} found` : ''}
            </>
          )}
          {!q && category && (
            <>
              Showing <span className="text-ink">{category.replaceAll('-', ' ')}</span>
            </>
          )}
          {!q && !category && 'Every recipe in the archive.'}
        </p>
        {hasFilters && (
          <button
            type="button"
            onClick={clearFilters}
            className="text-accent underline decoration-accent/30 underline-offset-4 transition-colors hover:decoration-accent"
          >
            Clear filters
          </button>
        )}
      </div>

      <div className="mt-6">
        {recipes.isPending && <LoadingRows label="Loading recipes" rows={6} />}
        {recipes.isError && (
          <ErrorState
            message={(recipes.error as Error).message}
            onRetry={() => recipes.refetch()}
          />
        )}
        {recipes.data && recipes.data.items.length === 0 && (
          <EmptyState>
            No recipes match this search. Try a shorter phrase or clear the filters.
          </EmptyState>
        )}
        {recipes.data && recipes.data.items.length > 0 && (
          <ul className="grid gap-1 md:grid-cols-2">
            {recipes.data.items.map((recipe) => (
              <li key={recipe.id} className="min-w-0">
                <RecipeListItem recipe={recipe} />
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
    </section>
  )
}
