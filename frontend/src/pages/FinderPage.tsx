import { useQuery } from '@tanstack/react-query'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { getFinder } from '../api/client'
import { EmptyState, ErrorState, LoadingRows } from '../components/DataState'
import { Button } from '../components/Button'
import FinderResultCard from '../components/FinderResultCard'
import Pagination from '../components/Pagination'
import PantryForm from '../components/PantryForm'
import Reveal from '../components/Reveal'

const PAGE_SIZE = 10

export default function FinderPage() {
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
        <div className="mx-auto max-w-[1440px] px-5 pb-12 pt-10 md:px-10 md:pb-16 md:pt-14">
          <nav aria-label="Breadcrumb" className="text-sm text-ink/70">
            <Link
              to="/"
              className="font-semibold underline decoration-2 underline-offset-4 hover:decoration-4"
            >
              Home
            </Link>
            <span aria-hidden="true"> / </span>
            <span>Finder</span>
          </nav>

          <header className="mt-8 max-w-4xl">
            <h1 className="hero-rise font-display text-[clamp(3rem,8vw,7rem)] leading-[0.88] tracking-[-0.02em]">
              What can you make?
            </h1>
            <p className="mt-8 max-w-2xl text-lead leading-snug text-ink/80 md:mt-10">
              Rank recipes by the ingredients you already have. Partial matches
              are welcome, the list shows what each recipe still needs, and
              every card carries its calories, protein, fat and fibre.
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

      <section className="bg-field py-16 md:py-24">
        <div className="mx-auto max-w-[1440px] px-5 md:px-10">
          {!ingredients.trim() && (
            <EmptyState title="Start with the pantry.">
              Add one or more ingredients above. The finder works with what you
              have.
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
              <Reveal>
                <div>
                  <h2 className="font-display text-head">
                    {results.data.count}{' '}
                    {results.data.count === 1 ? 'recipe' : 'recipes'} found
                  </h2>
                  <p className="mt-3 max-w-2xl text-body text-muted-field">
                    Using {results.data.ingredients.join(', ')}.
                  </p>
                </div>
              </Reveal>

              {results.data.unmatched.length > 0 && (
                <div className="mt-6 bg-ember px-5 py-4 text-sm text-ink/80">
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
                  {results.data.items.map((hit, index) => (
                    <li key={hit.recipe.id} className="min-w-0">
                      <Reveal delay={Math.min(index * 50, 250)}>
                        <FinderResultCard hit={hit} pantry={ingredients} />
                      </Reveal>
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
