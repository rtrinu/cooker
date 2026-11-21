import type { Nutrition } from '../api/client'
import {
  confidencePercent,
  formatWeight,
  isPartialNutrition,
  nutrientsPer100g,
} from '../lib/nutrition'

const MACROS = [
  ['Calories', 'kcal', 'kcal'],
  ['Protein', 'protein_g', 'g'],
  ['Carbs', 'carbs_g', 'g'],
  ['Fat', 'fat_g', 'g'],
  ['Fiber', 'fiber_g', 'g'],
] as const

const formatter = new Intl.NumberFormat('en-US', {
  maximumFractionDigits: 0,
})

const per100gFormatter = new Intl.NumberFormat('en-US', {
  maximumFractionDigits: 1,
})

function format(value: number) {
  return formatter.format(Math.round(value))
}

function formatPer100g(value: number, field: string) {
  return field === 'kcal' ? format(value) : per100gFormatter.format(value)
}

export default function NutritionFacts({
  nutrition,
  servings,
  inverse = false,
}: {
  nutrition: Nutrition
  servings?: number | null
  inverse?: boolean
}) {
  const label = inverse ? 'text-field/60' : 'text-muted-field'
  const value = inverse ? 'text-heat' : 'text-ink'
  const unit = inverse ? 'text-field/60' : 'text-muted-field'
  const divider = inverse ? 'border-field/15' : 'border-ink/10'
  const totalLabel = servings
    ? `Whole recipe (${servings} ${servings === 1 ? 'serving' : 'servings'})`
    : 'Whole recipe'
  const partial = isPartialNutrition(nutrition)
  const per100g = nutrientsPer100g(nutrition, servings)
  const confidence = confidencePercent(nutrition)
  const weight = formatWeight(nutrition.weight_g)
  const hasMeasure = nutrition.method === 'computed' && nutrition.lines_total > 0

  return (
    <>
      <table className="w-full border-collapse text-left">
        <caption className="sr-only">
          Nutrition per serving and for the whole recipe
        </caption>
        <thead>
          <tr className={`text-small ${label}`}>
            <th scope="col" className="pb-3 font-normal">
              <span className="sr-only">Nutrient</span>
            </th>
            <th scope="col" className="pb-3 text-right font-normal">
              Per serving
            </th>
            <th scope="col" className="pb-3 text-right font-normal">
              {totalLabel}
            </th>
          </tr>
        </thead>
        <tbody>
          {MACROS.map(([name, field, suffix]) => (
            <tr key={name} className={`border-t ${divider}`}>
              <th
                scope="row"
                className={`py-3 pr-3 text-small font-normal ${label}`}
              >
                {name}
              </th>
              <td
                className={`py-3 text-right font-display text-lead tabular-nums ${value}`}
              >
                {partial ? '≥ ' : ''}
                {format(nutrition[field])}
                <span className={`ml-1 text-small font-normal ${unit}`}>
                  {suffix}
                </span>
              </td>
              <td
                className={`py-3 pl-3 text-right font-display text-lead tabular-nums ${
                  servings ? value : label
                }`}
              >
                {servings ? (
                  <>
                    {partial ? '≥ ' : ''}
                    {format(nutrition[field] * servings)}
                  </>
                ) : (
                  '—'
                )}
                {servings ? (
                  <span className={`ml-1 text-small font-normal ${unit}`}>
                    {suffix}
                  </span>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {per100g && (
        <div className={`mt-6 border-t ${divider} pt-5`}>
          <p className={`text-small ${label}`}>Per 100 g of measured ingredients</p>
          <dl className="mt-3 grid grid-cols-3 gap-x-4 gap-y-3">
            {MACROS.map(([name, field, suffix]) => (
              <div key={name}>
                <dt className={`text-small ${label}`}>{name}</dt>
                <dd
                  className={`font-display text-lead tabular-nums ${value}`}
                >
                  {formatPer100g(per100g[field], field)}
                  <span className={`ml-1 text-small font-normal ${unit}`}>
                    {suffix}
                  </span>
                </dd>
              </div>
            ))}
          </dl>
        </div>
      )}

      {(hasMeasure || weight || confidence !== null) && (
        <dl
          className={`mt-6 flex flex-wrap gap-x-6 gap-y-2 border-t ${divider} pt-5 text-small`}
        >
          {hasMeasure && (
            <div className="flex items-baseline gap-1.5">
              <dt className={label}>Ingredients</dt>
              <dd className={`font-semibold tabular-nums ${value}`}>
                {nutrition.lines_used}/{nutrition.lines_total}
              </dd>
            </div>
          )}
          {weight && (
            <div className="flex items-baseline gap-1.5">
              <dt className={label}>Measured weight</dt>
              <dd className={`font-semibold tabular-nums ${value}`}>
                {weight}
              </dd>
            </div>
          )}
          {confidence !== null && (
            <div className="flex items-baseline gap-1.5">
              <dt className={label}>Confidence</dt>
              <dd className={`font-semibold tabular-nums ${value}`}>
                {confidence}%
              </dd>
            </div>
          )}
        </dl>
      )}
    </>
  )
}
