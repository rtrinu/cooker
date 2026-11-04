import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { getRecipeBySlug } from '../api/client'
import { ErrorState, LoadingRows } from '../components/DataState'

export default function RecipeDetailPage() {
  const { slug = '' } = useParams()
  const recipe = useQuery({
    queryKey: ['recipe', slug],
    queryFn: () => getRecipeBySlug(slug),
    enabled: Boolean(slug),
  })

  if (recipe.isPending) {
    return (
      <section className="mx-auto max-w-[1320px] px-5 pt-12 md:px-8 md:pt-16">
        <LoadingRows label="Loading recipe" rows={3} />
      </section>
    )
  }

  if (recipe.isError) {
    return (
      <section className="mx-auto max-w-[1320px] px-5 pt-12 md:px-8 md:pt-16">
        <ErrorState
          message={(recipe.error as Error).message}
          onRetry={() => recipe.refetch()}
        />
        <p className="mt-6 text-sm text-muted">
          <Link
            to="/recipes"
            className="text-accent underline decoration-accent/30 underline-offset-4"
          >
            Back to recipes
          </Link>
        </p>
      </section>
    )
  }

  const data = recipe.data
  const steps = data.directions
    .split('\n')
    .map((step) => step.trim())
    .filter(Boolean)
  const sourceLine = [data.contributor, data.source_title, data.source_year]
    .filter(Boolean)
    .join(' · ')

  return (
    <article className="mx-auto max-w-[1320px] px-5 pt-10 md:px-8 md:pt-14">
      <nav aria-label="Breadcrumb" className="text-sm text-muted">
        <Link
          to="/recipes"
          className="text-accent underline decoration-accent/30 underline-offset-4 transition-colors hover:decoration-accent"
        >
          Recipes
        </Link>
        <span aria-hidden="true"> / </span>
        <span>{data.name}</span>
      </nav>

      <header className="mt-8 max-w-4xl">
        <h1 className="font-display text-[clamp(2.8rem,6vw,5.4rem)] leading-[0.95] tracking-[-0.04em]">
          {data.name}
        </h1>
        <p className="mt-4 text-muted">{sourceLine}</p>
        {data.description && (
          <p className="mt-5 max-w-2xl text-lg leading-relaxed text-ink/80">
            {data.description}
          </p>
        )}
        <div className="mt-5 flex flex-wrap items-center gap-x-3 gap-y-2 text-sm text-muted">
          {data.collection && <span>{data.collection.replaceAll('-', ' ')}</span>}
          {data.category && <span aria-hidden="true">·</span>}
          {data.category && <span>{data.category.replaceAll('-', ' ')}</span>}
          {data.tags.length > 0 && <span aria-hidden="true">·</span>}
          {data.tags.length > 0 && (
            <span>{data.tags.map((tag) => tag.replaceAll('-', ' ')).join(', ')}</span>
          )}
        </div>
      </header>

      <div className="mt-12 grid gap-10 lg:grid-cols-12 lg:items-start">
        <aside className="lg:col-span-4">
          <div className="bg-surface p-6 md:p-8 lg:sticky lg:top-8">
            <h2 className="font-display text-3xl tracking-tight">Ingredients</h2>
            <ul className="mt-5 space-y-3">
              {data.ingredients.map((item) => (
                <li key={item.id} className="flex gap-3 text-[15px] leading-snug">
                  <span className="w-24 shrink-0 text-muted">{item.quantity_text}</span>
                  <span>{item.ingredient.name}</span>
                </li>
              ))}
            </ul>
            {data.servings && (
              <p className="mt-6 text-sm text-muted">
                Serves {data.servings}
                {data.serving_size ? ` · ${data.serving_size}` : ''}
              </p>
            )}
          </div>
        </aside>

        <div className="lg:col-span-8">
          <h2 className="font-display text-3xl tracking-tight">Method</h2>
          <ol className="mt-6 space-y-4 pl-5 text-[17px] leading-relaxed marker:text-sm marker:text-muted">
            {steps.map((step, index) => (
              <li key={index} className="pl-2">
                {step}
              </li>
            ))}
          </ol>

          {data.nutrition && (
            <section className="mt-10 bg-surface p-6 md:p-8">
              <h2 className="text-sm text-muted">Nutrition per serving</h2>
              <dl className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-5">
                {[
                  ['Calories', data.nutrition.kcal, 'kcal'],
                  ['Protein', data.nutrition.protein_g, 'g'],
                  ['Carbs', data.nutrition.carbs_g, 'g'],
                  ['Fat', data.nutrition.fat_g, 'g'],
                  ['Fiber', data.nutrition.fiber_g, 'g'],
                ].map(([label, value, unit]) => (
                  <div key={String(label)}>
                    <dt className="text-sm text-muted">{label}</dt>
                    <dd className="mt-1 font-display text-2xl">
                      {value}
                      <span className="ml-1 text-sm text-muted">{unit}</span>
                    </dd>
                  </div>
                ))}
              </dl>
            </section>
          )}

          <section className="mt-10 bg-ink p-6 text-paper md:p-8">
            <h2 className="text-sm text-paper/50">Source</h2>
            <p className="mt-3 font-display text-2xl leading-tight">{data.source_title}</p>
            <p className="mt-2 text-sm text-paper/70">
              {[data.contributor, data.source_year, data.license].filter(Boolean).join(' · ')}
            </p>
            {data.attribution && (
              <p className="mt-4 max-w-xl text-sm leading-relaxed text-paper/60">
                {data.attribution}
              </p>
            )}
            {data.source_url && (
              <a
                href={data.source_url}
                target="_blank"
                rel="noreferrer"
                className="mt-5 inline-block text-sm underline decoration-paper/30 underline-offset-4 transition-colors hover:decoration-paper"
              >
                Read the original source
              </a>
            )}
          </section>
        </div>
      </div>
    </article>
  )
}
