import { useQuery } from '@tanstack/react-query'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { getRecipeBySlug } from '../api/client'
import { ButtonAnchor } from '../components/Button'
import { ErrorState, LoadingRows } from '../components/DataState'
import NutritionFacts from '../components/NutritionFacts'
import RecipeImage from '../components/RecipeImage'
import Reveal from '../components/Reveal'
import { taxonomyLabel } from '../lib/labels'
import { splitPantry, termsTouch } from '../lib/pantry'

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

  if (recipe.isPending) {
    return (
      <section className="min-h-[60svh] bg-heat">
        <div className="mx-auto max-w-[1440px] px-5 pt-16 md:px-10 md:pt-24">
          <LoadingRows label="Loading recipe" rows={3} />
        </div>
      </section>
    )
  }

  if (recipe.isError) {
    return (
      <section className="min-h-[60svh] bg-heat">
        <div className="mx-auto max-w-[1440px] px-5 pt-16 md:px-10 md:pt-24">
          <ErrorState
            message={(recipe.error as Error).message}
            onRetry={() => recipe.refetch()}
          />
          <p className="mt-6 text-sm">
            <Link
              to="/recipes"
              className="font-semibold underline decoration-2 underline-offset-4 hover:decoration-4"
            >
              Back to recipes
            </Link>
          </p>
        </div>
      </section>
    )
  }

  const data = recipe.data
  const imageUrl = (data as typeof data & { image_url?: string }).image_url
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
    data.contributor,
    data.servings ? `Serves ${data.servings}` : '',
    data.serving_size,
    timing,
  ].filter(Boolean)
  const nutritionNote = data.nutrition
    ? data.nutrition.method === 'computed'
      ? `Estimated from ${data.nutrition.lines_used} of ${data.nutrition.lines_total} ingredients.`
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

  return (
    <article>
      <section className="bg-heat">
        <div className="mx-auto max-w-[1440px] px-5 pb-14 pt-10 md:px-10 md:pb-20 md:pt-14">
          <nav
            aria-label="Breadcrumb"
            className="flex flex-wrap gap-x-1 text-sm text-ink/70"
          >
            <Link
              to="/"
              className="font-semibold underline decoration-2 underline-offset-4 hover:decoration-4"
            >
              Home
            </Link>
            <span aria-hidden="true"> / </span>
            <Link
              to="/recipes"
              className="font-semibold underline decoration-2 underline-offset-4 hover:decoration-4"
            >
              Recipes
            </Link>
            <span aria-hidden="true"> / </span>
            <span className="max-w-[28ch] truncate">{data.name}</span>
          </nav>

          <header className="mt-8 grid gap-10 lg:grid-cols-12 lg:items-end lg:gap-8">
            <div className="lg:col-span-8">
              <h1 className="hero-rise max-w-5xl font-display text-[clamp(3rem,9vw,8rem)] leading-[0.86] tracking-[-0.02em]">
                {data.name}
              </h1>

              {data.description && (
                <p className="mt-8 max-w-2xl text-lead leading-snug text-ink/80 md:mt-10">
                  {data.description}
                </p>
              )}

              <div className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-4">
                {data.source_url ? (
                  <ButtonAnchor href={data.source_url}>
                    Read the original source
                  </ButtonAnchor>
                ) : (
                  <Link
                    to="/recipes"
                    className="inline-flex min-h-12 items-center bg-ink px-6 py-3 text-sm font-semibold text-heat transition-colors hover:bg-field hover:text-ink"
                  >
                    Browse all recipes
                  </Link>
                )}
                {meta.length > 0 && (
                  <p className="text-sm text-ink/70">{meta.join(' · ')}</p>
                )}
              </div>
            </div>

            <Reveal delay={100} className="lg:col-span-4 lg:pb-2">
              <div className="border-t-2 border-ink/20 pt-3">
                <p className="text-sm text-ink/70">Source</p>
                <p className="mt-2 max-w-[28ch] font-display text-2xl leading-tight">
                  {data.source_title}
                </p>
                {data.source_year && (
                  <p className="mt-2 text-sm tabular-nums text-ink/70">
                    {data.source_year}
                  </p>
                )}
              </div>
            </Reveal>
          </header>
        </div>
      </section>

      <section className="bg-field py-12 md:py-16">
        <div className="mx-auto max-w-[1440px] px-5 md:px-10">
          {imageUrl && (
            <RecipeImage
              src={imageUrl}
              alt={`${data.name} from ${data.source_title}`}
              className="mb-12 aspect-[21/9] w-full md:mb-16"
            />
          )}

          <div className="grid gap-12 lg:grid-cols-12 lg:items-start lg:gap-8">
            <aside className="lg:col-span-4">
              <div className="on-ink bg-ink p-6 text-field md:p-8">
                <div className="flex items-baseline justify-between gap-4">
                  <h2 className="font-display text-3xl leading-none text-heat">
                    Ingredients
                  </h2>
                  <span className="text-sm text-field/60">
                    {data.ingredients.length}
                  </span>
                </div>

                {pantryActive && (
                  <div className="mt-5 bg-field/10 px-4 py-4">
                    <p className="font-display text-2xl leading-none text-heat">
                      {pantryMatches.length} of {data.ingredients.length}
                    </p>
                    <p className="mt-1 text-sm text-field/60">in your pantry</p>
                    {pantryMissing.length > 0 && (
                      <p className="mt-3 text-sm leading-relaxed text-field/70">
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
                        <span className="w-20 shrink-0 text-sm tabular-nums text-field/60">
                          {item.quantity_text || '—'}
                        </span>
                        <span className="min-w-0 flex-1 text-[15px] leading-snug font-semibold">
                          {item.ingredient.name}
                        </span>
                        {pantryActive && (
                          <span
                            className={`shrink-0 px-2 py-0.5 text-xs font-semibold ${
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
                  <p className="mt-6 text-sm text-field/60">
                    {[
                      data.servings ? `Serves ${data.servings}` : '',
                      data.serving_size,
                    ]
                      .filter(Boolean)
                      .join(' · ')}
                  </p>
                )}
              </div>

              <Reveal className="mt-4">
                <section
                  aria-label="Nutrition"
                  className="on-ink bg-ink p-6 text-field md:p-8"
                >
                  <p className="font-display text-3xl leading-none text-heat">
                    Nutrition
                  </p>
                  {data.nutrition ? (
                    <>
                      <div className="mt-6">
                        <NutritionFacts nutrition={data.nutrition} inverse />
                      </div>
                      <p className="mt-8 text-sm text-field/60">
                        Per serving. {nutritionNote}
                      </p>
                    </>
                  ) : (
                    <p className="mt-4 text-sm leading-relaxed text-field/70">
                      This recipe has no nutrition data in its source. Cooker
                      won’t invent a figure.
                    </p>
                  )}
                </section>
              </Reveal>
            </aside>

            <div className="lg:col-span-8">
              <div className="flex flex-wrap items-baseline justify-between gap-4">
                <h2 className="font-display text-head">Method</h2>
                <p className="text-sm text-muted-field">
                  {steps.length} {steps.length === 1 ? 'step' : 'steps'}
                </p>
              </div>

              <ol className="mt-8 list-decimal space-y-7 pl-6 marker:font-display marker:text-xl marker:text-ink/40">
                {steps.map((step, index) => (
                  <li key={index} className="pl-2">
                    <Reveal delay={Math.min(index * 40, 240)}>
                      <p className="max-w-[62ch] text-[1.0625rem] leading-relaxed">
                        {step}
                      </p>
                    </Reveal>
                  </li>
                ))}
              </ol>

              <div className="mt-10 flex flex-wrap items-baseline justify-between gap-x-8 gap-y-4">
                {(data.collection ||
                  data.category ||
                  data.tags.length > 0) && (
                  <p className="max-w-xl text-sm leading-relaxed text-muted-field">
                    {[
                      ...new Set(
                        [data.collection, data.category, ...data.tags]
                          .filter((value) => value.length > 0)
                          .map(taxonomyLabel),
                      ),
                    ].join(' · ')}
                  </p>
                )}
                <Link
                  to="/recipes"
                  className="text-sm font-semibold underline decoration-2 underline-offset-4 hover:decoration-4"
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
