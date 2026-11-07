import { Link } from 'react-router-dom'
import type { FinderRecipe } from '../api/client'
import { taxonomyLabel } from '../lib/labels'
import Reveal from './Reveal'

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
  const categoryLine = recipe.category ? taxonomyLabel(recipe.category) : ''
  const missing = hit.missing.slice(0, 4)
  const remaining = hit.missing.length - missing.length
  const filled = Math.round(hit.pantry_coverage * 10)

  return (
    <Link
      to={targetWithPantry}
      className="group block bg-field p-5 text-ink transition-colors hover:bg-ink hover:text-heat focus-visible:bg-ink focus-visible:text-heat md:p-7"
    >
      <div className="grid gap-8 lg:grid-cols-12 lg:gap-8">
        <div className="lg:col-span-7">
          <h3 className="font-display text-[clamp(2rem,3.5vw,3.5rem)] leading-[0.92]">
            {recipe.name}
          </h3>
          {categoryLine && (
            <p className="mt-2 text-base text-ink/60 group-hover:text-heat/70 group-focus-visible:text-heat/70">
              {categoryLine}
            </p>
          )}

          <div className="mt-6 flex flex-wrap gap-2" aria-label="Matched ingredients">
            {hit.matched.map((item) => (
              <span
                key={item}
                className="bg-ink px-2.5 py-1 text-sm font-semibold text-heat transition-colors group-hover:bg-heat group-hover:text-ink group-focus-visible:bg-heat group-focus-visible:text-ink"
              >
                {item}
              </span>
            ))}
          </div>

          <p className="mt-4 text-base text-ink/60 group-hover:text-heat/70 group-focus-visible:text-heat/70">
            Uses {hit.matched.length} of your ingredients · {hit.matched_lines} of{' '}
            {hit.total_lines} recipe lines matched
          </p>

          {hit.missing.length > 0 && (
            <p className="mt-2 max-w-xl text-base leading-relaxed text-ink/60 group-hover:text-heat/70 group-focus-visible:text-heat/70">
              Still needed: {missing.join(', ')}
              {remaining > 0 ? ` and ${remaining} more` : ''}.
            </p>
          )}
        </div>

        <Reveal className="lg:col-span-5">
          <div className="flex items-baseline gap-3">
            <span className="font-display text-[clamp(3.5rem,6vw,5.5rem)] leading-none tabular-nums">
              {Math.round(hit.pantry_coverage * 100)}
            </span>
            <span className="text-xl text-ink/60 group-hover:text-heat/70 group-focus-visible:text-heat/70">
              % of lines
            </span>
          </div>
          <div className="mt-3 flex gap-1" aria-hidden="true">
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
                  <dt className="text-sm text-ink/60 group-hover:text-heat/60 group-focus-visible:text-heat/60">
                    {label}
                  </dt>
                  <dd className="font-display text-2xl leading-none tabular-nums">
                    {Math.round(recipe.nutrition![field])}
                    <span className="ml-1 text-sm font-normal text-ink/50 group-hover:text-heat/60 group-focus-visible:text-heat/60">
                      {unit}
                    </span>
                  </dd>
                </div>
              ))}
            </dl>
          ) : null}
        </Reveal>
      </div>
    </Link>
  )
}
