import { useQuery } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { getIngredients, getRecipes, getStats } from '../api/client'
import { ButtonLink } from '../components/Button'
import { ErrorState, LoadingRows } from '../components/DataState'
import PantryForm from '../components/PantryForm'
import PantryTicker from '../components/PantryTicker'
import RecipeListItem from '../components/RecipeListItem'
import Reveal from '../components/Reveal'
import { taxonomyLabel, ingredientCategoryLabel } from '../lib/labels'

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex flex-col-reverse">
      <dt className="text-sm text-ink/60">{label}</dt>
      <dd className="font-display text-3xl leading-none tabular-nums">{value}</dd>
    </div>
  )
}

const steps = [
  {
    title: 'Type what you have.',
    body: 'Eggs, flour, butter. No account, no quantities, no shopping list.',
    indent: 'md:pl-0',
  },
  {
    title: 'We read the pantry.',
    body: 'Spellings and aliases are matched against a shared index of 8,315 ingredients.',
    indent: 'md:pl-[8.33%]',
  },
  {
    title: 'It ranks the recipes.',
    body: 'Coverage is weighted by recipe lines, so the closest match comes first.',
    indent: 'md:pl-[16.66%]',
  },
  {
    title: 'You cook the closest one.',
    body: 'The missing lines stay visible, so nothing is hidden.',
    indent: 'md:pl-[25%]',
  },
]

export default function HomePage() {
  const navigate = useNavigate()

  const stats = useQuery({ queryKey: ['stats'], queryFn: getStats })
  const recipes = useQuery({
    queryKey: ['recipes', 'home'],
    queryFn: async () => {
      const first = await getRecipes({ page: 1, pageSize: 100 })
      if (first.items.length >= first.count) {
        return first
      }
      const rest = await getRecipes({ page: 2, pageSize: 100 })
      return { ...first, items: [...first.items, ...rest.items] }
    },
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
  const nutritionTotal = recipes.data
    ? recipeItems.filter((recipe) => recipe.nutrition).length
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
  const pantry = (ingredients.data?.items ?? []).slice(0, 12)

  return (
    <>
      <section className="overflow-hidden bg-heat">
        <div className="hero-rise mx-auto max-w-[1440px] px-5 pb-16 pt-8 md:px-10 md:pb-24 md:pt-12">
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
              <p className="text-lead leading-snug text-ink/80">
                Type what’s in your kitchen. Cooker ranks every recipe by how
                much of it you can make — partial matches included.
              </p>
            }
          />

          <dl className="mt-12 grid grid-cols-2 gap-6 bg-ember p-6 sm:grid-cols-4 md:p-8">
            <Stat label="Recipes" value={recipeTotal} />
            <Stat label="Ingredients" value={ingredientTotal} />
            <Stat label="With nutrition" value={nutritionTotal} />
            <Stat label="Categories" value={categoryTotal} />
          </dl>
        </div>
      </section>

      <section className="on-ink bg-ink py-12 md:py-16">
        <div className="mx-auto max-w-[1440px] px-5 md:px-10">
          <div>
            <h2 className="font-display text-[clamp(2.5rem,6vw,5.5rem)] text-heat">
              {ingredientTotal} ingredients.
            </h2>
            <p className="mt-2 max-w-xl text-body text-field/70">
              One shared pantry behind every recipe.
            </p>
          </div>
          <div className="mt-8">
            <PantryTicker items={ingredients.data?.items ?? []} />
          </div>
        </div>
      </section>

      <section className="bg-field py-24 md:py-32">
        <div className="mx-auto max-w-[1440px] px-5 md:px-10">
          <Reveal>
            <h2 className="font-display text-head">How it works.</h2>
          </Reveal>
          <div className="mt-14 space-y-10 md:space-y-14">
            {steps.map((step, index) => (
              <Reveal key={step.title} delay={index * 80} className={step.indent}>
                <p
                  className={`font-display text-[clamp(2rem,4.5vw,4.5rem)] leading-[0.95] ${
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
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      <section className="bg-heat py-24 md:py-32">
        <div className="mx-auto max-w-[1440px] px-5 md:px-10">
          <div className="grid gap-12 lg:grid-cols-12 lg:gap-8">
            <div className="lg:col-span-4">
              <Reveal>
                <h2 className="font-display text-head">{recipeTotal} recipes.</h2>
                <p className="mt-4 max-w-sm text-body text-ink/70">
                  Open any recipe for the ingredient list, the method and the
                  nutrition, all on one page.
                </p>
              </Reveal>

              <Reveal delay={80}>
                <ul className="mt-10 space-y-1">
                  {categories.map((item) => (
                    <li key={item.category}>
                      <Link
                        to={`/recipes?category=${encodeURIComponent(item.category)}`}
                        className="group -mx-3 flex items-baseline justify-between gap-4 px-3 py-2 transition-colors hover:bg-ink hover:text-heat focus-visible:bg-ink focus-visible:text-heat"
                      >
                        <span className="text-sm font-semibold capitalize">
                          {taxonomyLabel(item.category)}
                        </span>
                        <span className="shrink-0 text-sm tabular-nums text-ink/50 group-hover:text-heat/60 group-focus-visible:text-heat/60">
                          {item.count}
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>
                <ButtonLink to="/recipes" tone="ink" className="mt-8">
                  Browse all recipes
                </ButtonLink>
              </Reveal>
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
                  {featuredRecipes.map((recipe, index) => (
                    <li key={recipe.id} className="min-w-0">
                      <Reveal delay={Math.min(index * 60, 300)}>
                        <RecipeListItem recipe={recipe} />
                      </Reveal>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>
      </section>

      <section className="on-ink bg-ink py-24 text-field md:py-32">
        <div className="mx-auto grid max-w-[1440px] gap-12 px-5 md:px-10 lg:grid-cols-12">
          <div className="lg:col-span-6">
            <Reveal>
              <h2 className="font-display text-head text-heat">
                Nutrition, on the page.
              </h2>
              <p className="mt-4 max-w-md text-body text-field/70">
                Calories, protein, fat and fibre sit beside the ingredients. If
                the source printed a panel, you see it. If not, Cooker estimates
                from the ingredient lines and says how many it used.
              </p>
            </Reveal>
          </div>
          <Reveal delay={100} className="lg:col-span-6">
            <dl className="grid grid-cols-2 gap-x-6 gap-y-8">
              {[
                ['Calories', 'kcal'],
                ['Protein', 'g'],
                ['Fat', 'g'],
                ['Fibre', 'g'],
              ].map(([label, unit]) => (
                <div key={label} className="flex flex-col-reverse">
                  <dt className="text-sm text-field/60">{label}</dt>
                  <dd className="font-display text-[clamp(2.5rem,4vw,4rem)] leading-none text-heat">
                    {unit}
                  </dd>
                </div>
              ))}
            </dl>
            <p className="mt-10 max-w-md text-sm leading-relaxed text-field/60">
              No panel? No invention. The page tells you what it knows and what
              it does not.
            </p>
          </Reveal>
        </div>
      </section>

      <section className="bg-field py-24 md:py-32">
        <div className="mx-auto max-w-[1440px] px-5 md:px-10">
          <div className="flex flex-wrap items-end justify-between gap-6">
            <Reveal>
              <h2 className="font-display text-head">The pantry.</h2>
              <p className="mt-3 max-w-xl text-body text-muted-field">
                One shared index behind every recipe. Pick an ingredient to see
                what you can make with it.
              </p>
            </Reveal>
          </div>

          {ingredients.isPending && (
            <LoadingRows label="Loading the pantry" rows={4} />
          )}
          {ingredients.isError && (
            <div className="mt-8">
              <ErrorState
                message={(ingredients.error as Error).message}
                onRetry={() => ingredients.refetch()}
              />
            </div>
          )}

          {ingredients.data && (
            <>
              <ul className="mt-10 grid gap-x-10 gap-y-1 sm:grid-cols-2 lg:grid-cols-3">
                {pantry.map((ingredient) => (
                  <li key={ingredient.id}>
                    <Link
                      to={`/finder?ingredients=${encodeURIComponent(ingredient.name)}`}
                      className="group -mx-3 flex items-baseline justify-between gap-4 px-3 py-3 transition-colors hover:bg-ink hover:text-heat focus-visible:bg-ink focus-visible:text-heat"
                    >
                      <span className="text-body font-semibold">
                        {ingredient.name}
                      </span>
                      <span className="shrink-0 text-sm text-ink/50 group-hover:text-heat/60 group-focus-visible:text-heat/60">
                        {ingredientCategoryLabel(ingredient.category) || 'pantry'}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
              <Reveal>
                <ButtonLink to="/ingredients" tone="ink" className="mt-10">
                  Browse the pantry
                </ButtonLink>
              </Reveal>
            </>
          )}
        </div>
      </section>

      <section className="bg-heat py-24 md:py-32">
        <div className="mx-auto grid max-w-[1440px] gap-12 px-5 md:px-10 lg:grid-cols-12">
          <div className="lg:col-span-7">
            <Reveal>
              <h2 className="font-display text-head">
                No accounts. No tracking. No guesswork.
              </h2>
              <div className="mt-6 max-w-2xl space-y-4 text-body text-ink/80">
                <p>
                  Cooker is a recipe finder. Type what you have and get recipes
                  ranked by how much of the ingredient list you can cover.
                </p>
                <p>
                  Partial matches count. The missing ingredients stay visible,
                  and nutrition comes from the recipe or its ingredients, never
                  from thin air.
                </p>
                <p>
                  <a
                    href="/api/docs"
                    target="_blank"
                    rel="noreferrer"
                    className="font-semibold underline decoration-2 underline-offset-4 hover:decoration-4"
                  >
                    Read the API reference →
                  </a>
                </p>
              </div>
            </Reveal>
          </div>

          <Reveal delay={100} className="lg:col-span-5">
            <div className="grid gap-8">
              {[
                ['Partial matches', 'A recipe can still rank when you are missing a line or two.'],
                ['Nutrition on the page', 'Calories, protein, fat and fibre sit beside the ingredients.'],
                ['No tracking', 'No accounts, no cookies, no analytics.'],
              ].map(([title, body]) => (
                <div key={title}>
                  <h3 className="font-display text-3xl">{title}</h3>
                  <p className="mt-2 max-w-sm text-sm leading-relaxed text-ink/70">
                    {body}
                  </p>
                </div>
              ))}
            </div>
          </Reveal>
        </div>
      </section>
    </>
  )
}
