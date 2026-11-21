import { useQuery } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { getIngredients, getRecipes, getStats } from '../api/client'
import { ButtonLink } from '../components/Button'
import { ErrorState, LoadingRows } from '../components/DataState'
import NutritionFacts from '../components/NutritionFacts'
import PantryForm from '../components/PantryForm'
import PantryTicker from '../components/PantryTicker'
import RecipeListItem from '../components/RecipeListItem'
import { taxonomyLabel } from '../lib/labels'
import { usePageTitle } from '../lib/usePageTitle'

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex flex-col-reverse">
      <dt className="text-small text-field/60">{label}</dt>
      <dd className="font-display text-stat tabular-nums text-heat">{value}</dd>
    </div>
  )
}

const steps = [
  {
    title: 'Type what you have.',
    body: 'Eggs, flour, butter. No account, no quantities.',
    indent: 'md:pl-0',
  },
  {
    title: 'We read the list.',
    body: 'Spellings and aliases match against the shared ingredient index.',
    indent: 'md:pl-[8.33%]',
  },
  {
    title: 'It ranks the recipes.',
    body: 'Coverage is weighted by ingredients, so the closest match comes first.',
    indent: 'md:pl-[16.66%]',
  },
  {
    title: 'You cook the closest one.',
    body: 'Missing ingredients stay visible. Nothing is hidden.',
    indent: 'md:pl-[25%]',
  },
]

export default function HomePage() {
  usePageTitle()
  const navigate = useNavigate()

  const stats = useQuery({ queryKey: ['stats'], queryFn: getStats })
  const recipes = useQuery({
    queryKey: ['recipes', 'home'],
    queryFn: () => getRecipes({ page: 1, pageSize: 100 }),
  })
  const ingredients = useQuery({
    queryKey: ['ingredients', 'home'],
    queryFn: () => getIngredients({ page: 1, pageSize: 60 }),
  })

  const recipeItems = recipes.data?.items ?? []
  const categories = (stats.data?.categories ?? []).slice(0, 8)
  const recipeTotal = stats.data?.recipes ?? '—'
  const ingredientTotal = stats.data
    ? stats.data.ingredients.toLocaleString('en-US')
    : '—'
  const categoryTotal = stats.data?.categories.length ?? '—'

  const featuredRecipes = (() => {
    const groups = new Map<string, typeof recipeItems>()
    for (const recipe of recipeItems) {
      const group = groups.get(recipe.category) ?? []
      group.push(recipe)
      groups.set(recipe.category, group)
    }
    return [...groups.values()]
      .flatMap((group) => group.slice(0, 3))
      .slice(0, 6)
  })()

  const featuredExample = featuredRecipes.find((recipe) => recipe.nutrition)
  // The first alphabetical page can have no computed nutrition at all, so
  // fall back to the next page to keep the worked example populated.
  const nutritionExample = useQuery({
    queryKey: ['recipes', 'home', 'nutrition-example'],
    queryFn: () => getRecipes({ page: 2, pageSize: 100 }),
    enabled: recipes.isSuccess && !featuredExample,
  })
  const example =
    featuredExample ??
    nutritionExample.data?.items.find((recipe) => recipe.nutrition)
  const exampleHref = example
    ? `/recipes/${example.slug ?? example.id}`
    : undefined

  return (
    <>
      <section className="bg-heat">
        <div className="shell pb-16 pt-8 md:pb-24 md:pt-12">
          <PantryForm
            hero
            id="home-pantry"
            onSubmit={(value) =>
              navigate(
                value
                  ? `/finder?ingredients=${encodeURIComponent(value)}`
                  : '/finder',
              )
            }
            support={
              <p className="text-lead text-ink/80">
                Type what’s in your kitchen. Cooker ranks every recipe by how
                much of it you can make.
              </p>
            }
          />

          <dl className="mt-10 grid grid-cols-2 gap-6 bg-ink p-6 text-field sm:grid-cols-3 md:p-8">
            <Stat label="Recipes" value={recipeTotal} />
            <Stat label="Ingredients" value={ingredientTotal} />
            <Stat label="Categories" value={categoryTotal} />
          </dl>
        </div>
      </section>

      <section className="on-ink bg-ink section">
        <div className="shell">
          <h2 className="font-display text-head text-heat">
            {ingredientTotal} ingredients.
          </h2>
          <p className="mt-3 max-w-xl text-body text-field/70">
            Every ingredient any recipe uses. The ticker samples the pantry the
            finder searches.
          </p>
          <div className="mt-8">
            <PantryTicker items={ingredients.data?.items ?? []} />
          </div>
        </div>
      </section>

      <section className="bg-field section">
        <div className="shell">
          <h2 className="font-display text-head">How it works.</h2>
          <div className="mt-12 space-y-9 md:space-y-12">
            {steps.map((step, index) => (
              <div key={step.title} className={step.indent}>
                <p
                  className={`font-display text-title ${
                    index === steps.length - 1
                      ? 'inline-block bg-heat px-3 py-1'
                      : ''
                  }`}
                >
                  {step.title}
                </p>
                <p className="mt-3 max-w-[34ch] text-body text-muted-field">
                  {step.body}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="bg-heat section">
        <div className="shell">
          <div className="grid gap-12 lg:grid-cols-12 lg:gap-8">
            <div className="lg:col-span-4">
              <h2 className="font-display text-head">{recipeTotal} recipes.</h2>
              <p className="mt-4 max-w-sm text-body text-ink/80">
                Open any recipe for its ingredients, method and nutrition on one
                page.
              </p>

              <ul className="mt-8 space-y-1">
                {categories.map((item) => (
                  <li key={item.category}>
                    <Link
                      to={`/recipes?category=${encodeURIComponent(item.category)}`}
                      className="group -mx-3 flex min-h-11 items-baseline justify-between gap-4 px-3 py-2 transition-colors hover:bg-ink hover:text-heat focus-visible:bg-ink focus-visible:text-heat"
                    >
                      <span className="text-small font-semibold capitalize">
                        {taxonomyLabel(item.category)}
                      </span>
                      <span className="shrink-0 text-small tabular-nums text-ink/70 group-hover:text-heat/80 group-focus-visible:text-heat/80">
                        {item.count}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
              <ButtonLink to="/recipes" tone="ink" className="mt-7">
                Browse all recipes
              </ButtonLink>
            </div>

            <div className="lg:col-span-8">
              {recipes.isPending && (
                <LoadingRows label="Loading recipes" rows={6} />
              )}
              {recipes.isError && (
                <ErrorState
                  message={(recipes.error as Error).message}
                  onRetry={() => recipes.refetch()}
                />
              )}
              {recipes.data && (
                <ul className="space-y-1">
                  {featuredRecipes.map((recipe) => (
                    <li key={recipe.id} className="min-w-0">
                      <RecipeListItem recipe={recipe} />
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>
      </section>

      <section className="on-ink bg-ink section text-field">
        <div className="shell grid gap-12 lg:grid-cols-12">
          <div className="lg:col-span-6">
            <h2 className="font-display text-head text-heat">
              Nutrition, on the page.
            </h2>
            <p className="mt-4 max-w-md text-body text-field/70">
              Calories, protein, fat and fibre sit beside the ingredients.
              Each panel says how many ingredients it measured, how much they
              weighed and how confident the match is.
            </p>
          </div>
          <div className="lg:col-span-6">
            {example && exampleHref ? (
              <div>
                <p className="text-small text-field/60">Example</p>
                <Link
                  to={exampleHref}
                  className="mt-2 inline-block font-display text-title text-heat hover:underline hover:decoration-2 hover:underline-offset-4"
                >
                  {example.name}
                </Link>
                <div className="mt-7">
                  <NutritionFacts
                    nutrition={example.nutrition!}
                    servings={example.servings}
                    inverse
                  />
                </div>
              </div>
            ) : (
              <p className="max-w-md text-body text-field/70">
                Open any recipe to see its nutrition panel, or how it was
                estimated.
              </p>
            )}
            <p className="mt-8 max-w-md text-small text-field/60">
              No panel? No invention. The page tells you what it knows and what
              it does not.
            </p>
          </div>
        </div>
      </section>

      <section className="bg-heat section">
        <div className="shell">
          <div className="max-w-3xl">
            <h2 className="font-display text-head">
              No accounts. No tracking. No guesswork.
            </h2>
            <p className="mt-6 text-body text-ink/80">
              Cooker is a recipe finder. Type what you have and get recipes
              ranked by how much of the ingredient list you can cover. Missing
              ingredients stay visible, and nutrition comes from the recipe or
              its ingredients, never from thin air.
            </p>
            <p className="mt-4">
              <a
                href="/api/docs"
                target="_blank"
                rel="noreferrer"
                className="inline-flex min-h-11 items-center font-semibold underline decoration-2 underline-offset-4 hover:decoration-4"
              >
                Read the API reference →
              </a>
            </p>
          </div>
        </div>
      </section>
    </>
  )
}
