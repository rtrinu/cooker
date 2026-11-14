import { useQuery } from '@tanstack/react-query'
import { getStats } from '../api/client'
import { ButtonLink } from '../components/Button'
import PageHero from '../components/PageHero'
import { usePageTitle } from '../lib/usePageTitle'

const recipeSources = [
  {
    name: 'Public Domain Recipes',
    licence: 'Unlicense',
    body: 'Modern recipes released into the public domain. No attribution is required, but the source is recorded on every recipe.',
    href: 'https://publicdomainrecipes.com',
  },
  {
    name: 'Open Recipe Archive',
    licence: 'Public domain',
    body: 'Digitised historical cookbooks. Each recipe keeps its book, author, year and a link to the original edition.',
  },
  {
    name: 'USDA Team Nutrition',
    licence: 'U.S. Government work',
    body: 'Recipes from the Recipes for Healthy Kids cards, published by the U.S. Department of Agriculture.',
  },
]

const nutritionSources = [
  {
    name: 'USDA FoodData Central',
    licence: 'CC0 1.0',
    status: 'In use',
    body: 'Per-100g nutrition for generic ingredients. The USDA asks for attribution, so the source is stored on every nutrition record.',
  },
  {
    name: 'UK CoFID (McCance & Widdowson)',
    licence: 'Open Government Licence v3.0',
    status: 'Not in use',
    body: 'Would cover UK-specific ingredients. Any public use must credit the source and Crown copyright.',
  },
  {
    name: 'Open Food Facts',
    licence: 'ODbL 1.0',
    status: 'Not enabled',
    body: 'Branded products. Its share-alike terms are why it is deliberately kept out of the main ingredient database.',
  },
]

export default function DataPage() {
  usePageTitle('Data & licences')
  const stats = useQuery({ queryKey: ['stats'], queryFn: getStats })

  const recipeTotal = stats.data?.recipes ?? '—'
  const collectionTotal = stats.data?.collections ?? '—'

  return (
    <>
      <section className="bg-heat">
        <div className="shell pb-12 pt-8 md:pb-16 md:pt-10">
          <PageHero
            crumb="Data & licences"
            title="Where the food comes from."
            intro="Every recipe and every nutrition figure keeps a record of its source. This page says what Cooker uses, what it does not, and what each licence asks of us."
          />

          <dl className="mt-10 grid grid-cols-2 gap-6 bg-ink p-6 text-field sm:max-w-xl sm:grid-cols-3 md:p-8">
            <div className="flex flex-col-reverse">
              <dt className="text-small text-field/60">Recipes</dt>
              <dd className="font-display text-stat tabular-nums text-heat">
                {recipeTotal}
              </dd>
            </div>
            <div className="flex flex-col-reverse">
              <dt className="text-small text-field/60">Collections</dt>
              <dd className="font-display text-stat tabular-nums text-heat">
                {collectionTotal}
              </dd>
            </div>
            <div className="flex flex-col-reverse">
              <dt className="text-small text-field/60">Nutrition source</dt>
              <dd className="font-display text-title text-heat">USDA</dd>
            </div>
          </dl>
        </div>
      </section>

      <section className="bg-field section">
        <div className="shell">
          <h2 className="font-display text-head">Recipes.</h2>
          <p className="mt-4 max-w-xl text-body text-muted-field">
            Importers only accept public-domain or Unlicense content. The
            attribution stored with each recipe appears under its method.
          </p>

          <ul className="mt-10 grid gap-4 md:grid-cols-3">
            {recipeSources.map((source) => (
              <li
                key={source.name}
                className="on-ink flex flex-col bg-ink p-6 text-field md:p-8"
              >
                <p className="text-small font-semibold uppercase tracking-wide text-heat">
                  {source.licence}
                </p>
                <h3 className="mt-3 font-display text-title">{source.name}</h3>
                <p className="mt-4 flex-1 text-body text-field/70">
                  {source.body}
                </p>
                {source.href && (
                  <a
                    href={source.href}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-6 inline-flex min-h-11 items-center text-small font-semibold text-heat underline decoration-2 underline-offset-4 hover:decoration-4"
                  >
                    Visit the collection →
                  </a>
                )}
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="bg-heat section">
        <div className="shell">
          <h2 className="font-display text-head">Nutrition.</h2>
          <p className="mt-4 max-w-xl text-body text-ink/80">
            Nutrition is matched to ingredients, converted to grams and summed.
            Missing values stay missing; they are never counted as zero.
          </p>

          <ul className="mt-10 divide-y-2 divide-ink/15 border-y-2 border-ink/15">
            {nutritionSources.map((source) => (
              <li
                key={source.name}
                className="grid gap-3 py-6 md:grid-cols-12 md:items-baseline md:gap-8"
              >
                <div className="md:col-span-5">
                  <h3 className="font-display text-title">{source.name}</h3>
                  <p className="mt-1 text-small font-semibold text-ink/70">
                    {source.licence}
                  </p>
                </div>
                <p className="max-w-xl text-body text-ink/80 md:col-span-5">
                  {source.body}
                </p>
                <p className="text-small font-semibold uppercase tracking-wide md:col-span-2 md:text-right">
                  {source.status}
                </p>
              </li>
            ))}
          </ul>

          <p className="mt-8 max-w-2xl text-small text-ink/80">
            This page is an engineering summary, not legal advice. The full
            notes live in <code>DATA_LICENSES.md</code> beside the source code.
          </p>
        </div>
      </section>

      <section className="on-ink bg-ink section text-field">
        <div className="shell grid gap-10 lg:grid-cols-12 lg:items-end">
          <div className="lg:col-span-8">
            <h2 className="font-display text-head text-heat">
              No invented figures.
            </h2>
            <p className="mt-5 max-w-xl text-body text-field/70">
              When only some ingredients can be measured, the panel is marked
              as a lower bound. When a recipe has no reliable serving count, it
              keeps that gap visible instead of guessing.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <ButtonLink to="/recipes" tone="heat">
                Browse the recipes
              </ButtonLink>
              <a
                href="/api/docs"
                target="_blank"
                rel="noreferrer"
                className="inline-flex min-h-12 items-center px-2 text-small font-semibold text-field underline decoration-2 underline-offset-4 hover:decoration-4"
              >
                Read the API reference →
              </a>
            </div>
          </div>
        </div>
      </section>
    </>
  )
}
