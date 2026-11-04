import { Link } from 'react-router-dom'
import type { RecipeList } from '../api/client'

function metaLine(recipe: RecipeList) {
  return [recipe.contributor, recipe.source_title, recipe.source_year]
    .filter(Boolean)
    .join(' · ')
}

export default function RecipeListItem({ recipe }: { recipe: RecipeList }) {
  const target = recipe.slug ? `/recipes/${recipe.slug}` : `/recipes/${recipe.id}`

  return (
    <Link
      to={target}
      className="group flex items-start justify-between gap-6 bg-paper px-5 py-5 transition-colors hover:bg-surface focus-visible:bg-surface"
    >
      <div className="min-w-0">
        <h3 className="font-display text-2xl leading-tight tracking-tight transition-colors group-hover:text-accent">
          {recipe.name}
        </h3>
        <p className="mt-1 truncate text-base text-ink/80">{metaLine(recipe)}</p>
        {recipe.tags.length > 0 && (
          <p className="mt-2 text-sm text-muted/80">
            {recipe.tags.map((tag) => tag.replaceAll('-', ' ')).join(' · ')}
          </p>
        )}
      </div>
      <span
        aria-hidden="true"
        className="mt-1 text-xl text-muted transition-colors group-hover:text-accent"
      >
        →
      </span>
    </Link>
  )
}
