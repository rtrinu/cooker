import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { getIngredients } from '../api/client'
import { EmptyState, ErrorState, LoadingRows } from '../components/DataState'
import Pagination from '../components/Pagination'
import SearchForm from '../components/SearchForm'

const PAGE_SIZE = 24

export default function IngredientsPage() {
  const [params, setParams] = useSearchParams()
  const q = params.get('q') ?? ''
  const page = Math.max(1, Number(params.get('page') ?? '1') || 1)

  const ingredients = useQuery({
    queryKey: ['ingredients', { q, page }],
    queryFn: () => getIngredients({ q, page, pageSize: PAGE_SIZE }),
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

  return (
    <section className="mx-auto max-w-[1320px] px-5 pt-12 md:px-8 md:pt-16">
      <h1 className="font-display text-[clamp(3rem,6vw,5.5rem)] leading-none tracking-[-0.04em]">
        Ingredients
      </h1>
      <p className="mt-3 max-w-xl text-muted">
        The shared pantry behind every recipe. Names are normalised so a historic ingredient
        can be followed across books.
      </p>

      <div className="mt-9 max-w-2xl">
        <SearchForm
          key={q}
          initialValue={q}
          onSubmit={(value) => updateParam('q', value)}
          label="Search ingredients"
          placeholder="Search the pantry"
        />
      </div>

      <p className="mt-4 text-sm text-muted" aria-live="polite">
        {ingredients.data
          ? `${ingredients.data.count} ${
              ingredients.data.count === 1 ? 'ingredient' : 'ingredients'
            }${q ? ` matching “${q}”` : ''}`
          : 'Loading the pantry'}
      </p>

      <div className="mt-6">
        {ingredients.isPending && <LoadingRows label="Loading ingredients" rows={6} />}
        {ingredients.isError && (
          <ErrorState
            message={(ingredients.error as Error).message}
            onRetry={() => ingredients.refetch()}
          />
        )}
        {ingredients.data && ingredients.data.items.length === 0 && (
          <EmptyState>
            Nothing in the pantry matches that phrase. Try a shorter search.
          </EmptyState>
        )}
        {ingredients.data && ingredients.data.items.length > 0 && (
          <ul className="grid gap-x-8 gap-y-1 sm:grid-cols-2 lg:grid-cols-3">
            {ingredients.data.items.map((ingredient) => (
              <li
                key={ingredient.id}
                className="flex items-baseline justify-between gap-4 px-4 py-3 transition-colors hover:bg-surface"
              >
                <span className="font-display text-xl leading-tight">{ingredient.name}</span>
                <span className="shrink-0 text-sm text-muted">
                  {ingredient.category || 'uncategorised'}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {ingredients.data && (
        <Pagination
          page={page}
          count={ingredients.data.count}
          pageSize={PAGE_SIZE}
          onPageChange={(nextPage) => updateParam('page', String(nextPage))}
        />
      )}
    </section>
  )
}
