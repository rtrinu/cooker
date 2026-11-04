import { useState, type FormEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { getIngredients, getRecipes, getStats } from '../api/client'
import RecipeListItem from '../components/RecipeListItem'
import Reveal from '../components/Reveal'
import campImage from '../assets/archive/cooking-in-camp-the-kitchen-of-the.jpg'
import cookeryImage from '../assets/archive/american-cookery-1915-14761674076.jpg'
import hearthImage from '../assets/archive/detail-of-fireplace-original-kitchen-daniel-shoemaker.jpg'
import brownBettyImage from '../assets/archive/brown-betty.jpg'
import breadPuddingImage from '../assets/archive/bread-pudding-apple.jpg'

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <p className="font-display text-4xl leading-none tracking-tight">{value}</p>
      <p className="mt-1 text-sm text-muted">{label}</p>
    </div>
  )
}

export default function HomePage() {
  const navigate = useNavigate()
  const [search, setSearch] = useState('')

  const stats = useQuery({ queryKey: ['stats'], queryFn: getStats })
  const recipes = useQuery({
    queryKey: ['recipes', 'home'],
    queryFn: () => getRecipes({ page: 1, pageSize: 6 }),
  })
  const ingredients = useQuery({
    queryKey: ['ingredients', 'home'],
    queryFn: () => getIngredients({ page: 1, pageSize: 12 }),
  })

  function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const query = search.trim()
    navigate(query ? `/recipes?q=${encodeURIComponent(query)}` : '/recipes')
  }

  return (
    <>
      <section className="mx-auto max-w-[1320px] px-5 pb-12 pt-12 md:px-8 md:pb-16 md:pt-20">
        <div className="grid gap-10 lg:grid-cols-12 lg:items-end">
          <Reveal className="min-w-0 lg:col-span-7">
            <h1 className="font-display text-[clamp(3rem,9vw,8rem)] font-normal leading-[0.86] tracking-[-0.045em]">
              <span className="block">The Cooker</span>
              <span className="block text-accent">Archive</span>
            </h1>
            <p className="mt-7 max-w-2xl text-lg leading-relaxed text-ink md:text-xl">
              A public-domain collection of American cookery, transcribed from the printed page.
              Search a hundred recipes, follow a dish back to its source, and read the kitchen
              notes exactly as they were written.
            </p>

            <form role="search" onSubmit={handleSearch} className="mt-9 flex max-w-2xl">
              <label htmlFor="home-search" className="sr-only">
                Search recipes
              </label>
              <input
                id="home-search"
                type="search"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search recipes, authors or sources"
                className="min-w-0 flex-1 bg-surface px-5 py-4 text-base outline-none placeholder:text-muted/80 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent"
              />
              <button
                type="submit"
                className="bg-accent px-6 py-4 text-sm font-medium text-paper transition-colors hover:bg-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
              >
                Search
              </button>
            </form>
          </Reveal>

          <Reveal delay={120} className="min-w-0 lg:col-span-5">
            <figure>
              <div className="overflow-hidden bg-surface">
                <img
                  src={campImage}
                  alt="A camp kitchen of the Fremont Dragoons, with cooks gathered around a large pot, 1861."
                  width={1920}
                  height={1439}
                  className="image-drift aspect-[4/3] w-full object-cover"
                />
              </div>
              <figcaption className="mt-2 text-base text-ink/80">
                “Cooking in Camp”, 1861. Public domain, via Wikimedia Commons.
              </figcaption>
            </figure>
          </Reveal>
        </div>

        <Reveal
          delay={180}
          className="mt-10 grid grid-cols-2 gap-6 bg-surface p-6 sm:grid-cols-4 md:p-8"
        >
          <Stat label="Recipes" value={stats.data?.recipes ?? '—'} />
          <Stat label="Ingredients" value={stats.data?.ingredients ?? '—'} />
          <Stat label="Collections" value={stats.data?.collections ?? '—'} />
          <Stat label="License" value="Public domain" />
        </Reveal>
      </section>

      <section className="mx-auto max-w-[1320px] px-5 md:px-8">
        <Reveal className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h2 className="font-display text-4xl tracking-tight md:text-5xl">From the archive</h2>
            <p className="mt-2 max-w-xl text-ink">
              Six recipes from the collection, read in the order they were printed.
            </p>
          </div>
          <Link
            to="/recipes"
            className="text-sm text-accent underline decoration-accent/30 underline-offset-4 transition-colors hover:decoration-accent"
          >
            Browse all recipes
          </Link>
        </Reveal>

        <div className="mt-7">
          {recipes.isPending && (
            <div className="grid gap-1 md:grid-cols-2" aria-hidden="true">
              {Array.from({ length: 6 }, (_, index) => (
                <div key={index} className="bg-surface px-5 py-6">
                  <div className="h-6 w-2/3 bg-surface-deep" />
                  <div className="mt-3 h-3 w-1/3 bg-surface-deep" />
                </div>
              ))}
            </div>
          )}
          {recipes.isError && (
            <p role="alert" className="bg-surface px-5 py-6 text-sm text-muted">
              {(recipes.error as Error).message}
            </p>
          )}
          {recipes.data && recipes.data.items.length > 0 && (
            <ul className="grid gap-1 md:grid-cols-2">
              {recipes.data.items.map((recipe, index) => (
                <li key={recipe.id} className="min-w-0">
                  <Reveal delay={Math.min(index * 60, 300)} className="min-w-0">
                    <RecipeListItem recipe={recipe} />
                  </Reveal>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="mt-3 grid gap-3 md:grid-cols-[1.35fr_1fr]">
          <Reveal delay={60}>
            <figure className="overflow-hidden bg-surface">
              <img
                src={cookeryImage}
                alt="A scanned page from an American cookery book, 1915."
                width={1920}
                height={1372}
                loading="lazy"
                className="image-drift aspect-[4/3] w-full object-cover"
              />
              <figcaption className="bg-surface px-4 py-3 text-base text-ink/80">
                American Cookery, 1915. Internet Archive Book Images, via Wikimedia Commons.
              </figcaption>
            </figure>
          </Reveal>
          <Reveal delay={120}>
            <figure className="overflow-hidden bg-surface">
              <img
                src={brownBettyImage}
                alt="A brown betty apple pudding in a baking dish."
                width={1920}
                height={1080}
                loading="lazy"
                className="image-drift aspect-[4/3] w-full object-cover"
              />
              <figcaption className="bg-surface px-4 py-3 text-base text-ink/80">
                Brown Betty by KaMan, CC BY-SA 4.0, via Wikimedia Commons.
              </figcaption>
            </figure>
          </Reveal>
        </div>
      </section>

      <section className="mx-auto mt-20 max-w-[1320px] px-5 md:mt-28 md:px-8">
        <div className="grid gap-8 bg-surface p-7 md:grid-cols-[1fr_1.1fr] md:p-12">
          <Reveal>
            <figure>
              <img
                src={hearthImage}
                alt="The original open hearth and fireplace of the Daniel Shoemaker farmhouse kitchen."
                width={1920}
                height={1529}
                loading="lazy"
                className="image-drift aspect-[5/4] w-full object-cover"
              />
              <figcaption className="mt-2 text-base text-ink/80">
                Daniel Shoemaker farmhouse kitchen, HABS. Public domain, via Wikimedia Commons.
              </figcaption>
            </figure>
          </Reveal>
          <Reveal delay={100}>
            <h2 className="font-display text-3xl tracking-tight md:text-4xl">
              About the archive
            </h2>
            <div className="mt-4 space-y-4 text-ink">
              <p>
                The first collection comes from Eliza Leslie's{' '}
                <em>Miss Leslie's Complete Cookery</em> (1851), digitised by Project Gutenberg.
                Ingredients are matched to a shared pantry so the same ingredient can be followed
                across books.
              </p>
              <p>
                The catalogue is read-only and served by a Django Ninja API. It is built for
                browsing, citation and reuse: no accounts, no tracking, no modern rewrites of the
                original instructions.
              </p>
              <p>
                <a
                  href="/api/docs"
                  target="_blank"
                  rel="noreferrer"
                  className="text-accent underline decoration-accent/30 underline-offset-4 hover:decoration-accent"
                >
                  Read the API reference
                </a>
              </p>
            </div>
          </Reveal>
        </div>
      </section>

      <section className="mx-auto mt-20 max-w-[1320px] px-5 md:mt-28 md:px-8">
        <div className="grid gap-10 lg:grid-cols-[1.5fr_1fr] lg:items-start">
          <div>
            <Reveal className="flex flex-wrap items-end justify-between gap-4">
              <div>
                <h2 className="font-display text-4xl tracking-tight md:text-5xl">The pantry</h2>
                <p className="mt-2 max-w-xl text-ink">
                  The shared ingredient index behind the recipes.
                </p>
              </div>
              <Link
                to="/ingredients"
                className="text-sm text-accent underline decoration-accent/30 underline-offset-4 transition-colors hover:decoration-accent"
              >
                Browse all ingredients
              </Link>
            </Reveal>

            <ul className="mt-6 grid gap-x-8 gap-y-3 sm:grid-cols-2">
              {ingredients.data?.items.map((ingredient) => (
                <li key={ingredient.id} className="flex items-baseline justify-between gap-4 py-2">
                  <span className="font-display text-xl">{ingredient.name}</span>
                  <span className="shrink-0 text-sm text-muted">
                    {ingredient.category || 'uncategorised'}
                  </span>
                </li>
              ))}
            </ul>
          </div>

          <Reveal delay={100}>
            <figure>
              <img
                src={breadPuddingImage}
                alt="An apple bread pudding in a shallow dish."
                width={1024}
                height={680}
                loading="lazy"
                className="image-drift aspect-[4/5] w-full object-cover"
              />
              <figcaption className="mt-2 text-base text-ink/80">
                Bread pudding with apple by stu_spivack, CC BY-SA 2.0, via Wikimedia Commons.
              </figcaption>
            </figure>
          </Reveal>
        </div>
      </section>
    </>
  )
}
