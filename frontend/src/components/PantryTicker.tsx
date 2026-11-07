import type { Ingredient } from '../api/client'
import { ingredientCategoryLabel } from '../lib/labels'

export default function PantryTicker({ items }: { items: Ingredient[] }) {
  if (items.length === 0) {
    return <p className="text-body text-field/60">Loading the pantry…</p>
  }

  const visible = items.slice(0, 30)

  return (
    <div className="overflow-hidden">
      <div className="pantry-track flex items-center gap-8">
        {[0, 1].map((copy) => (
          <div
            key={copy}
            className="flex items-center gap-8"
            aria-hidden={copy === 1}
          >
            {visible.map((ingredient) => (
              <span
                key={`${copy}-${ingredient.id}`}
                className="flex items-baseline gap-3 whitespace-nowrap"
              >
                <span className="font-display text-2xl text-heat md:text-3xl">
                  {ingredient.name}
                </span>
                <span className="text-sm text-field/50">
                  {ingredientCategoryLabel(ingredient.category) || 'pantry'}
                </span>
                <span aria-hidden="true" className="text-heat/40">
                  /
                </span>
              </span>
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}
