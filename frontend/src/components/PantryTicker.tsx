import { useState } from 'react'
import type { Ingredient } from '../api/client'
import { ingredientGroup } from '../lib/ingredients'

export default function PantryTicker({ items }: { items: Ingredient[] }) {
  const [paused, setPaused] = useState(false)

  if (items.length === 0) {
    return <p className="text-body text-field/70">Loading ingredients…</p>
  }

  const visible = items.slice(0, 30)

  return (
    <div>
      <div className="pantry-viewport">
        <div
          className="pantry-track flex items-center gap-8"
          data-paused={paused}
        >
          {[0, 1].map((copy) => (
            <div
              key={copy}
              className="flex items-center gap-8"
              data-dup={copy === 1}
              aria-hidden={copy === 1}
            >
              {visible.map((ingredient) => (
                <span
                  key={`${copy}-${ingredient.id}`}
                  className="flex items-baseline gap-3 whitespace-nowrap"
                >
                  <span className="font-display text-title text-heat">
                    {ingredient.name}
                  </span>
                  <span className="text-small text-field/60">
                    {ingredientGroup(ingredient.name, ingredient.category)}
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
      <button
        type="button"
        onClick={() => setPaused((current) => !current)}
        aria-pressed={paused}
        className="mt-4 inline-flex min-h-11 items-center text-small font-semibold text-field/70 underline decoration-2 underline-offset-4 hover:text-field"
      >
        {paused ? 'Play ticker' : 'Pause ticker'}
      </button>
    </div>
  )
}
