import { Link } from 'react-router-dom'
import type { FinderRecipe } from '../api/client'
import { taxonomyLabel } from '../lib/labels'
import { isPartialNutrition } from '../lib/nutrition'

const MACROS = [
  ['Calories', 'kcal', 'kcal'],
  ['Protein', 'protein_g', 'g'],
  ['Fat', 'fat_g', 'g'],
  ['Fiber', 'fiber_g', 'g'],
] as const

export default function FinderResultCard({
  hit,
  pantry,
}: {
  hit: FinderRecipe
  pantry: string
}) {
  const recipe = hit.recipe
  const target = recipe.slug ? `/recipes/${recipe.slug}` : `/recipes/${recipe.id}`
  const targetWithPantry = `${target}?pantry=${encodeURIComponent(pantry)}`
  const categoryLine = [recipe.category, recipe.cuisine]
    .filter(Boolean)
    .map(taxonomyLabel)
    .join(' · ')
  const missing = hit.missing.slice(0, 4)
  const remaining = hit.missing.length - missing.length
  const filled = Math.round(hit.pantry_coverage * 10)
  const partial = recipe.nutrition
    ? isPartialNutrition(recipe.nutrition)
    : false

  return (
    <Link
      to={targetWithPantry}
      className="group block bg-ink/[0.04] p-5 text-ink transition-colors hover:bg-ink hover:text-heat focus-visible:bg-ink focus-visible:text-heat md:p-7"
    >
      <div className="grid gap-8 lg:grid-cols-12 lg:gap-8">
        <div className="lg:col-span-7">
          <h3 className="font-display text-title">{recipe.name}</h3>
          {categoryLine && (
            <p className="mt-2 text-small text-muted-field group-hover:text-heat/80 group-focus-visible:text-heat/80">
              {categoryLine}
            </p>
          )}

          <div
            className="mt-5 flex flex-wrap gap-2"
            aria-label="Matched ingredients"
          >
            {hit.matched.map((item) => (
              <span
                key={item}
                className="bg-ink px-2.5 py-1 text-small font-semibold text-heat transition-colors group-hover:bg-heat group-hover:text-ink group-focus-visible:bg-heat group-focus-visible:text-ink"
              >
                {item}
              </span>
            ))}
          </div>

          <p className="mt-4 text-body text-muted-field group-hover:text-heat/80 group-focus-visible:text-heat/80">
            Uses {hit.matched.length} of your ingredients ·{' '}
            {hit.matched_ingredients} of {hit.total_ingredients} ingredients
            matched
          </p>

          {hit.missing.length > 0 && (
            <p className="mt-2 max-w-xl text-body text-muted-field group-hover:text-heat/80 group-focus-visible:text-heat/80">
              Still needed: {missing.join(', ')}
              {remaining > 0 ? ` and ${remaining} more` : ''}.
            </p>
          )}
        </div>

        <div className="lg:col-span-5">
          <div className="flex items-baseline gap-3">
            <span className="font-display text-stat tabular-nums">
              {Math.round(hit.pantry_coverage * 100)}
            </span>
            <span className="text-lead text-muted-field group-hover:text-heat/80 group-focus-visible:text-heat/80">
              % of ingredients
            </span>
          </div>
          <div
            className="meter-fill mt-3 flex gap-1 motion-reduce:animate-none"
            aria-hidden="true"
          >
            {Array.from({ length: 10 }, (_, index) => (
              <span
                key={index}
                className={`h-2 flex-1 transition-colors ${
                  index < filled
                    ? 'bg-ink group-hover:bg-heat group-focus-visible:bg-heat'
                    : 'bg-ink/15 group-hover:bg-heat/20 group-focus-visible:bg-heat/20'
                }`}
              />
            ))}
          </div>

          {recipe.nutrition ? (
            <dl className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
              {MACROS.map(([label, field, unit]) => (
                <div key={label}>
                  <dt className="text-small text-muted-field group-hover:text-heat/80 group-focus-visible:text-heat/80">
                    {label}
                  </dt>
                  <dd className="font-display text-title tabular-nums">
                    {partial ? '≥ ' : ''}
                    {Math.round(recipe.nutrition![field])}
                    <span className="ml-1 text-small font-normal text-muted-field group-hover:text-heat/80 group-focus-visible:text-heat/80">
                      {unit}
                    </span>
                  </dd>
                </div>
              ))}
            </dl>
          ) : null}
        </div>
      </div>
    </Link>
  )
}
