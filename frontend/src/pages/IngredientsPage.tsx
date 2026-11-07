import { useQuery } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import { getIngredients, getStats } from '../api/client'
import { EmptyState, ErrorState, LoadingRows } from '../components/DataState'
import Pagination from '../components/Pagination'
import Reveal from '../components/Reveal'
import SearchForm from '../components/SearchForm'
import { ingredientCategoryLabel } from '../lib/labels'

const PAGE_SIZE = 24

export default function IngredientsPage() {
  const [params, setParams] = useSearchParams()
  const q = params.get('q') ?? ''
  const page = Math.max(1, Number(params.get('page') ?? '1') || 1)

  const stats = useQuery({ queryKey: ['stats'], queryFn: getStats })
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

  const total = ingredients.data?.count

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
            <span>Ingredients</span>
          </nav>

          <div className="mt-8 grid gap-8 lg:grid-cols-12 lg:items-end lg:gap-8">
            <div className="lg:col-span-8">
              <h1 className="hero-rise font-display text-[clamp(3.5rem,11vw,10rem)] leading-[0.84] tracking-[-0.02em]">
                The pantry.
              </h1>
              <p className="mt-8 max-w-xl text-lead leading-snug text-ink/80 md:mt-10">
                One shared index behind every recipe. Pick an ingredient to see
                what you can make with it.
              </p>
            </div>

            <div className="lg:col-span-4 lg:pb-2">
              <p className="font-display text-[clamp(3rem,6vw,5rem)] leading-none tabular-nums">
                {stats.data ? stats.data.ingredients.toLocaleString('en-US') : '—'}
              </p>
              <p className="mt-2 text-sm text-ink/70">names indexed</p>
            </div>
          </div>
        </div>
      </section>

      <section className="bg-field py-10 md:py-14">
        <div className="mx-auto max-w-[1440px] px-5 md:px-10">
          <div className="max-w-3xl">
            <SearchForm
              key={q}
              initialValue={q}
              onSubmit={(value) => updateParam('q', value)}
              label="Search ingredients"
              placeholder="Search the pantry"
            />
          </div>

          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-sm text-muted-field">
            <p aria-live="polite">
              {total !== undefined
                ? `${total} ${total === 1 ? 'ingredient' : 'ingredients'}${
                    q ? ` matching “${q}”` : ' in the pantry'
                  }`
                : 'Loading the pantry'}
            </p>
            {q && (
              <button
                type="button"
                onClick={() => updateParam('q', '')}
                className="min-h-11 font-semibold text-ink underline decoration-2 underline-offset-4 hover:decoration-4"
              >
                Clear search
              </button>
            )}
          </div>

          <div className="mt-8">
            {ingredients.isPending && (
              <LoadingRows label="Loading ingredients" rows={6} />
            )}
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
              <ul className="grid gap-x-10 gap-y-0 sm:grid-cols-2 lg:grid-cols-3">
                {ingredients.data.items.map((ingredient) => (
                  <li key={ingredient.id}>
                    <Reveal>
                      <Link
                        to={`/finder?ingredients=${encodeURIComponent(ingredient.name)}`}
                        className="group -mx-3 flex items-baseline gap-4 px-3 py-3 transition-colors hover:bg-ink hover:text-heat focus-visible:bg-ink focus-visible:text-heat"
                      >
                        <span className="min-w-0 flex-1 text-body font-semibold">
                          {ingredient.name}
                        </span>
                        <span className="shrink-0 text-sm text-ink/50 group-hover:text-heat/60 group-focus-visible:text-heat/60">
                          {ingredientCategoryLabel(ingredient.category) || 'pantry'}
                        </span>
                      </Link>
                    </Reveal>
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
        </div>
      </section>
    </>
  )
}
