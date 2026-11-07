import type { Nutrition } from '../api/client'

const MACROS = [
  ['Calories', 'kcal', 'kcal'],
  ['Protein', 'protein_g', 'g'],
  ['Fat', 'fat_g', 'g'],
  ['Fiber', 'fiber_g', 'g'],
] as const

export default function NutritionFacts({
  nutrition,
  inverse = false,
}: {
  nutrition: Nutrition
  inverse?: boolean
}) {
  const label = inverse ? 'text-field/60' : 'text-ink/60'
  const value = inverse ? 'text-heat' : 'text-ink'
  const unit = inverse ? 'text-heat/60' : 'text-ink/50'

  return (
    <dl
      className={`grid grid-cols-2 gap-x-6 gap-y-6 ${
        inverse ? '' : 'sm:grid-cols-4'
      }`}
    >
      {MACROS.map(([name, field, suffix]) => (
        <div key={name}>
          <dt className={`text-sm ${label}`}>{name}</dt>
          <dd
            className={`font-display leading-none tabular-nums ${
              inverse
                ? 'text-[clamp(2rem,3vw,2.5rem)]'
                : 'text-[clamp(2.25rem,3.5vw,3.5rem)]'
            } ${value}`}
          >
            {Math.round(nutrition[field])}
            <span className={`ml-1 text-sm font-normal ${unit}`}>{suffix}</span>
          </dd>
        </div>
      ))}
    </dl>
  )
}
