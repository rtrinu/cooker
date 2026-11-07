import { Link } from 'react-router-dom'
import type { RecipeList } from '../api/client'
import { taxonomyLabel } from '../lib/labels'

export default function RecipeListItem({ recipe }: { recipe: RecipeList }) {
  const target = recipe.slug ? `/recipes/${recipe.slug}` : `/recipes/${recipe.id}`

  return (
    <Link
      to={target}
      className="group grid gap-3 px-4 py-5 text-ink transition-colors hover:bg-ink hover:text-heat focus-visible:bg-ink focus-visible:text-heat md:grid-cols-[1fr_auto] md:items-baseline md:px-6 md:py-6"
    >
      <div className="min-w-0">
        <h3 className="font-display text-[clamp(1.65rem,2.8vw,2.75rem)] leading-[0.95]">
          {recipe.name}
        </h3>
      </div>
      <div className="flex items-baseline justify-between gap-5 md:justify-end">
        {recipe.category && (
          <span className="text-sm text-ink/50 group-hover:text-heat/60 group-focus-visible:text-heat/60">
            {taxonomyLabel(recipe.category)}
          </span>
        )}
        <span
          aria-hidden="true"
          className="text-xl transition-transform group-hover:translate-x-1 group-focus-visible:translate-x-1"
        >
          →
        </span>
      </div>
    </Link>
  )
}
