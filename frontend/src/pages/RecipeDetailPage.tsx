import { useQuery } from '@tanstack/react-query'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { getRecipeBySlug } from '../api/client'
import { ButtonLink } from '../components/Button'
import { ErrorState, LoadingRows } from '../components/DataState'
import NutritionFacts from '../components/NutritionFacts'
import { licenseLabel, taxonomyLabel } from '../lib/labels'
import { formatWeight, nutritionWarnings } from '../lib/nutrition'
import { splitPantry, termsTouch } from '../lib/pantry'
import { usePageTitle } from '../lib/usePageTitle'

export default function RecipeDetailPage() {
  const { slug = '' } = useParams()
  const [searchParams] = useSearchParams()
  const pantry = searchParams.get('pantry') ?? ''
  const pantryTerms = splitPantry(pantry)
  const recipe = useQuery({
    queryKey: ['recipe', slug],
    queryFn: () => getRecipeBySlug(slug),
    enabled: Boolean(slug),
  })
  usePageTitle(recipe.data?.name)

  if (recipe.isPending) {
    return (
      <section className="min-h-[60svh] bg-heat">
        <div className="shell pt-12 md:pt-16">
          <LoadingRows label="Loading recipe" rows={3} />
        </div>
      </section>
    )
  }

  if (recipe.isError) {
    return (
      <section className="min-h-[60svh] bg-heat">
        <div className="shell pt-12 md:pt-16">
          <ErrorState
            message={(recipe.error as Error).message}
            onRetry={() => recipe.refetch()}
          />
          <p className="mt-6 text-small">
            <Link
              to="/recipes"
              className="inline-flex min-h-11 items-center font-semibold underline decoration-2 underline-offset-4 hover:decoration-4"
            >
              Back to recipes
            </Link>
          </p>
        </div>
      </section>
    )
  }

  const data = recipe.data
  const steps = data.directions
    .split('\n')
    .map((step) => step.trim())
    .filter(Boolean)
  const timing = [
    data.prep_mins ? `${data.prep_mins} min prep` : '',
    data.cook_mins ? `${data.cook_mins} min cook` : '',
  ]
    .filter(Boolean)
    .join(' · ')
  const meta = [
    data.servings ? `Serves ${data.servings}` : '',
    data.serving_size,
    timing,
    data.cuisine ? taxonomyLabel(data.cuisine) : '',
  ].filter(Boolean)
  const nutritionFlags = data.nutrition
    ? nutritionWarnings(data.nutrition)
    : []
  const nutritionPrimary =
    nutritionFlags.find(
      (flag) =>
        flag.code === 'macro-mismatch' ||
        flag.code === 'implausible-energy-density',
    ) ??
    nutritionFlags.find((flag) => flag.code === 'partial') ??
    nutritionFlags.find((flag) => flag.code === 'low-confidence') ??
    null
  const nutritionNotes = nutritionFlags.filter(
    (flag) => flag !== nutritionPrimary,
  )
  const nutritionNote = data.nutrition
    ? data.nutrition.method === 'computed'
      ? 'Calculated from the ingredient list, not a lab test.'
      : 'From the recipe’s printed nutrition panel.'
    : ''
  const pantryActive = pantryTerms.length > 0
  const pantryMatches = data.ingredients.filter((item) =>
    pantryTerms.some((term) => termsTouch(term, item.ingredient.name)),
  )
  const pantryMissing = data.ingredients.filter(
    (item) =>
      !pantryTerms.some((term) => termsTouch(term, item.ingredient.name)),
  )
  const resultHref = pantryActive
    ? `/finder?ingredients=${encodeURIComponent(pantry)}`
    : '/recipes'
  const taxonomy = [
    ...new Set(
      [data.category, data.cuisine, ...data.tags]
        .filter((value) => value.length > 0)
        .map(taxonomyLabel),
    ),
  ]
  const attribution =
    data.attribution ||
    [data.contributor, data.source_title, data.source_year]
      .filter(Boolean)
      .join(' — ')
  const hasSource = Boolean(
    attribution || data.source_url || data.source_title || data.license,
  )

  return (
    <article>
      <section className="bg-heat">
        <div className="shell pb-12 pt-8 md:pb-16 md:pt-10">
          <nav
            aria-label="Breadcrumb"
            className="flex min-w-0 items-center gap-x-1 whitespace-nowrap text-small text-ink/80"
          >
            <Link
              to="/"
              className="inline-flex min-h-11 items-center font-semibold underline decoration-2 underline-offset-4 hover:decoration-4"
            >
              Home
            </Link>
            <span aria-hidden="true"> / </span>
            <Link
              to="/recipes"
              className="inline-flex min-h-11 items-center font-semibold underline decoration-2 underline-offset-4 hover:decoration-4"
            >
              Recipes
            </Link>
            <span aria-hidden="true"> / </span>
            <span className="min-w-0 truncate">{data.name}</span>
          </nav>

          <header className="mt-6">
            <h1 className="hero-rise max-w-5xl font-display text-poster">
              {data.name}
            </h1>

            {data.description && (
              <p className="mt-6 max-w-2xl text-lead text-ink/80">
                {data.description}
              </p>
            )}

            <div className="mt-7 flex flex-wrap items-center gap-x-6 gap-y-3">
              <ButtonLink to={resultHref}>
                {pantryActive ? 'Back to results' : 'Browse all recipes'}
              </ButtonLink>
              {meta.length > 0 && (
                <p className="text-small text-ink/80">{meta.join(' · ')}</p>
              )}
            </div>
          </header>
        </div>
      </section>

      <section className="bg-field section-sm">
        <div className="shell">
          <div className="grid gap-12 lg:grid-cols-12 lg:items-start lg:gap-8">
            <aside className="lg:col-span-4">
              <div className="on-ink bg-ink p-6 text-field md:p-8">
                <div className="flex items-baseline justify-between gap-4">
                  <h2 className="font-display text-title text-heat">
                    Ingredients
                  </h2>
                  <span className="text-small text-field/60">
                    {data.ingredients.length}
                  </span>
                </div>

                {pantryActive && (
                  <div className="mt-5 bg-field/10 px-4 py-4">
                    <p className="font-display text-title text-heat">
                      {pantryMatches.length} of {data.ingredients.length}
                    </p>
                    <p className="mt-1 text-small text-field/60">
                      in your ingredients
                    </p>
                    {pantryMissing.length > 0 && (
                      <p className="mt-3 text-small text-field/70">
                        Still needed:{' '}
                        {pantryMissing
                          .slice(0, 4)
                          .map((item) => item.ingredient.name)
                          .join(', ')}
                        {pantryMissing.length > 4
                          ? ` and ${pantryMissing.length - 4} more`
                          : ''}
                        .
                      </p>
                    )}
                  </div>
                )}

                <ul className="mt-6 space-y-1">
                  {data.ingredients.map((item) => {
                    const have =
                      pantryActive &&
                      pantryTerms.some((term) =>
                        termsTouch(term, item.ingredient.name),
                      )
                    return (
                      <li
                        key={item.id}
                        className="flex items-start gap-4 px-2 py-2 odd:bg-field/5"
                      >
                        <span className="w-24 shrink-0 text-small tabular-nums text-field/60">
                          <span className="block">
                            {item.quantity_text || '—'}
                          </span>
                          {item.grams != null && (
                            <span
                              className="block text-field/50"
                              title={item.grams_detail || undefined}
                            >
                              {formatWeight(item.grams)}
                            </span>
                          )}
                        </span>
                        <span className="min-w-0 flex-1 text-body font-semibold">
                          {item.ingredient.name}
                        </span>
                        {pantryActive && (
                          <span
                            className={`shrink-0 px-2 py-0.5 text-small font-semibold ${
                              have
                                ? 'bg-heat text-ink'
                                : 'bg-field/10 text-field/60'
                            }`}
                          >
                            {have ? 'have' : 'need'}
                          </span>
                        )}
                      </li>
                    )
                  })}
                </ul>

                {(data.servings || data.serving_size) && (
                  <p className="mt-6 text-small text-field/60">
                    {[
                      data.servings ? `Serves ${data.servings}` : '',
                      data.serving_size,
                    ]
                      .filter(Boolean)
                      .join(' · ')}
                  </p>
                )}
              </div>

              <section
                aria-label="Nutrition"
                className="on-ink mt-4 bg-ink p-6 text-field md:p-8"
              >
                <h2 className="font-display text-title text-heat">Nutrition</h2>
                {data.nutrition ? (
                  <>
                    <div className="mt-6">
                      <NutritionFacts
                        nutrition={data.nutrition}
                        servings={data.servings}
                        inverse
                      />
                    </div>
                    <p className="mt-6 text-small text-field/60">
                      {data.servings
                        ? 'Per serving and for the whole recipe. '
                        : 'Per serving. Whole-recipe totals need a serving count. '}
                      {nutritionNote}
                    </p>

                    {nutritionPrimary && (
                      <p className="mt-3 text-small text-heat">
                        <span className="font-semibold">
                          {nutritionPrimary.label}.
                        </span>{' '}
                        {nutritionPrimary.code === 'partial'
                          ? `Only ${data.nutrition.lines_used} of ${data.nutrition.lines_total} ingredients could be measured.`
                          : nutritionPrimary.detail}
                      </p>
                    )}

                    {nutritionNotes.length > 0 && (
                      <details className="group mt-5 border-t border-field/15 pt-5">
                        <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-4 text-small font-semibold text-field/80 [&::-webkit-details-marker]:hidden">
                          <span>
                            How this estimate was built
                            {nutritionNotes.length > 1
                              ? ` (${nutritionNotes.length} notes)`
                              : ''}
                          </span>
                          <span
                            aria-hidden="true"
                            className="text-lead leading-none text-heat transition-transform group-open:rotate-45"
                          >
                            +
                          </span>
                        </summary>
                        <ul className="mt-2 space-y-3">
                          {nutritionNotes.map((flag) => (
                            <li
                              key={flag.code}
                              className="text-small text-field/70"
                            >
                              <span className="font-semibold text-field/90">
                                {flag.label}.
                              </span>{' '}
                              {flag.detail}
                            </li>
                          ))}
                        </ul>
                      </details>
                    )}
                  </>
                ) : (
                  <p className="mt-4 text-small text-field/70">
                    This recipe doesn’t have enough measured ingredients for a
                    reliable nutrition estimate. Cooker won’t invent a figure.
                  </p>
                )}
              </section>
            </aside>

            <div className="lg:col-span-8">
              <div className="flex flex-wrap items-baseline justify-between gap-4">
                <h2 className="font-display text-head">Method</h2>
                <p className="text-small text-muted-field">
                  {steps.length} {steps.length === 1 ? 'step' : 'steps'}
                </p>
              </div>

              <ol className="mt-8 list-decimal space-y-7 pl-6 marker:font-display marker:text-lead marker:text-ink/60">
                {steps.map((step, index) => (
                  <li key={index} className="pl-2">
                    <p className="max-w-[62ch] text-body">{step}</p>
                  </li>
                ))}
              </ol>

              {hasSource && (
                <section
                  aria-labelledby="source-heading"
                  className="mt-12 border-t-2 border-ink/15 pt-7"
                >
                  <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2">
                    <h2
                      id="source-heading"
                      className="font-display text-title"
                    >
                      Source
                    </h2>
                    {data.license && (
                      <p className="text-small font-semibold uppercase tracking-wide text-muted-field">
                        {licenseLabel(data.license)}
                      </p>
                    )}
                  </div>

                  {attribution && (
                    <p className="mt-4 max-w-[62ch] text-body text-ink/80">
                      {attribution}
                    </p>
                  )}

                  <div className="mt-5 flex flex-wrap items-baseline gap-x-6 gap-y-2 text-small">
                    {data.source_url && (
                      <a
                        href={data.source_url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex min-h-11 items-center font-semibold underline decoration-2 underline-offset-4 hover:decoration-4"
                      >
                        Read the original source →
                      </a>
                    )}
                    {data.collection && (
                      <span className="text-muted-field">
                        Collection: {taxonomyLabel(data.collection)}
                      </span>
                    )}
                    <Link
                      to="/data"
                      className="inline-flex min-h-11 items-center font-semibold underline decoration-2 underline-offset-4 hover:decoration-4"
                    >
                      How Cooker credits data
                    </Link>
                  </div>
                </section>
              )}

              <div className="mt-10 flex flex-wrap items-baseline justify-between gap-x-8 gap-y-4">
                {taxonomy.length > 0 && (
                  <p className="max-w-xl text-small text-muted-field">
                    {taxonomy.join(' · ')}
                  </p>
                )}
                <Link
                  to="/recipes"
                  className="inline-flex min-h-11 items-center text-small font-semibold underline decoration-2 underline-offset-4 hover:decoration-4"
                >
                  All recipes
                </Link>
              </div>
            </div>
          </div>
        </div>
      </section>
    </article>
  )
}
