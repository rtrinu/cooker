import { Link } from 'react-router-dom'
import type { RecipeList } from '../api/client'
import { taxonomyLabel } from '../lib/labels'
import { isPartialNutrition } from '../lib/nutrition'

export default function RecipeListItem({ recipe }: { recipe: RecipeList }) {
  const target = recipe.slug ? `/recipes/${recipe.slug}` : `/recipes/${recipe.id}`
  const partial = recipe.nutrition ? isPartialNutrition(recipe.nutrition) : false
  const facets = [recipe.category, recipe.cuisine]
    .filter(Boolean)
    .map(taxonomyLabel)

  return (
    <Link
      to={target}
      className="group -mx-4 grid min-h-16 gap-3 px-4 py-5 text-ink transition-colors hover:bg-ink hover:text-heat focus-visible:bg-ink focus-visible:text-heat md:-mx-5 md:grid-cols-[1fr_auto] md:items-baseline md:px-5 md:py-6"
    >
      <h3 className="min-w-0 font-display text-title">{recipe.name}</h3>
      <div className="flex flex-wrap items-baseline justify-between gap-x-5 gap-y-1 md:justify-end">
        {recipe.nutrition && (
          <span className="text-small tabular-nums text-muted-field group-hover:text-heat/80 group-focus-visible:text-heat/80">
            {partial ? '≥ ' : ''}
            {Math.round(recipe.nutrition.kcal)} kcal ·{' '}
            {partial ? '≥ ' : ''}
            {Math.round(recipe.nutrition.protein_g)} g protein
          </span>
        )}
        {facets.length > 0 && (
          <span className="text-small text-muted-field group-hover:text-heat/80 group-focus-visible:text-heat/80">
            {facets.join(' · ')}
          </span>
        )}
        <span
          aria-hidden="true"
          className="text-lead transition-transform group-hover:translate-x-1 group-focus-visible:translate-x-1"
        >
          →
        </span>
      </div>
    </Link>
  )
}
