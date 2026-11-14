import type { Nutrition } from '../api/client'

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

function format(value: number) {
  return formatter.format(Math.round(value))
}

export default function NutritionFacts({
  nutrition,
  servings,
  inverse = false,
  partial = false,
}: {
  nutrition: Nutrition
  servings?: number | null
  inverse?: boolean
  partial?: boolean
}) {
  const label = inverse ? 'text-field/60' : 'text-muted-field'
  const value = inverse ? 'text-heat' : 'text-ink'
  const unit = inverse ? 'text-field/60' : 'text-muted-field'
  const divider = inverse ? 'border-field/15' : 'border-ink/10'
  const totalLabel = servings
    ? `Whole recipe (${servings} ${servings === 1 ? 'serving' : 'servings'})`
    : 'Whole recipe'

  return (
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
  )
}
