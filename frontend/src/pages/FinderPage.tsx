import { useQuery } from '@tanstack/react-query'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { getFinder } from '../api/client'
import { Button } from '../components/Button'
import { EmptyState, ErrorState, LoadingRows } from '../components/DataState'
import FinderResultCard from '../components/FinderResultCard'
import Pagination from '../components/Pagination'
import PantryForm from '../components/PantryForm'
import { usePageTitle } from '../lib/usePageTitle'

const PAGE_SIZE = 10

export default function FinderPage() {
  usePageTitle('Finder')
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const ingredients = params.get('ingredients') ?? ''
  const page = Math.max(1, Number(params.get('page') ?? '1') || 1)

  const results = useQuery({
    queryKey: ['finder', { ingredients, page }],
    queryFn: () => getFinder({ ingredients, page, pageSize: PAGE_SIZE }),
    enabled: Boolean(ingredients.trim()),
    placeholderData: (previous) => previous,
  })

  function goToPage(nextPage: number) {
    const next = new URLSearchParams(params)
    next.set('page', String(nextPage))
    setParams(next)
  }

  return (
    <>
      <section className="bg-heat">
        <div className="shell pb-12 pt-8 md:pb-16 md:pt-10">
          <nav aria-label="Breadcrumb" className="text-small text-ink/80">
            <Link
              to="/"
              className="inline-flex min-h-11 items-center font-semibold underline decoration-2 underline-offset-4 hover:decoration-4"
            >
              Home
            </Link>
            <span aria-hidden="true"> / </span>
            <span>Finder</span>
          </nav>

          <header className="mt-6 max-w-4xl">
            <h1 className="hero-rise font-display text-poster">
              What can you make?
            </h1>
            <p className="mt-6 max-w-2xl text-lead text-ink/80">
              Rank recipes by the ingredients you already have. The list shows
              what each recipe still needs, and every card carries its calories,
              protein, fat and fibre.
            </p>
            <PantryForm
              key={ingredients}
              initialValue={ingredients}
              compact
              id="finder-pantry"
              onSubmit={(value) =>
                navigate(
                  value
                    ? `/finder?ingredients=${encodeURIComponent(value)}`
                    : '/finder',
                )
              }
            />
            <Button
              type="button"
              className="mt-4 w-full sm:w-auto"
              onClick={() =>
                navigate('/finder?ingredients=eggs%2C%20flour%2C%20butter')
              }
            >
              Try eggs, flour, butter
            </Button>
          </header>
        </div>
      </section>

      <section className="bg-field section-sm">
        <div className="shell">
          {!ingredients.trim() && (
            <EmptyState title="Add what you have.">
              Type one or more ingredients above, or browse the list to pick
              them. The finder works with what you already have.
            </EmptyState>
          )}

          {ingredients.trim() && results.isPending && (
            <LoadingRows label="Finding recipes" rows={5} />
          )}

          {ingredients.trim() && results.isError && (
            <ErrorState
              message={(results.error as Error).message}
              onRetry={() => results.refetch()}
            />
          )}

          {results.data && ingredients.trim() && (
            <>
              <div>
                <h2 className="font-display text-head">
                  {results.data.count}{' '}
                  {results.data.count === 1 ? 'recipe' : 'recipes'} found
                </h2>
                <p className="mt-2 max-w-2xl text-body text-muted-field">
                  Using {results.data.ingredients.join(', ')}.
                </p>
              </div>

              {results.data.unmatched.length > 0 && (
                <div className="mt-6 bg-ink px-5 py-4 text-small text-field/80">
                  No recipe uses: {results.data.unmatched.join(', ')}. Try a
                  broader ingredient or remove it.
                </div>
              )}

              {results.data.items.length === 0 ? (
                <div className="mt-8">
                  <EmptyState title="Nothing matched yet.">
                    Try one ingredient at a time, or a broader word such as
                    eggs, flour or milk.
                  </EmptyState>
                </div>
              ) : (
                <ul className="mt-8 space-y-1">
                  {results.data.items.map((hit) => (
                    <li key={hit.recipe.id} className="min-w-0">
                      <FinderResultCard hit={hit} pantry={ingredients} />
                    </li>
                  ))}
                </ul>
              )}

              <Pagination
                page={page}
                count={results.data.count}
                pageSize={PAGE_SIZE}
                onPageChange={goToPage}
              />
            </>
          )}
        </div>
      </section>
    </>
  )
}
