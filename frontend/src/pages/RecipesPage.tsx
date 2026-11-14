import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { getRecipes, getStats } from '../api/client'
import { EmptyState, ErrorState, LoadingRows } from '../components/DataState'
import Pagination from '../components/Pagination'
import RangeSlider, { type RangeValue } from '../components/RangeSlider'
import RecipeListItem from '../components/RecipeListItem'
import SearchForm from '../components/SearchForm'
import { taxonomyLabel } from '../lib/labels'
import { usePageTitle } from '../lib/usePageTitle'

const PAGE_SIZE = 20

type Bounds = {
  min: number
  max: number
  step: number
}

const KCAL = { min: 0, max: 1200, step: 25 }
const PROTEIN = { min: 0, max: 100, step: 1 }

function readNumber(params: URLSearchParams, key: string, fallback: number) {
  const raw = params.get(key)
  if (raw === null || raw.trim() === '') {
    return fallback
  }
  const value = Number(raw)
  return Number.isFinite(value) ? value : fallback
}

function readRange(
  params: URLSearchParams,
  lowKey: string,
  highKey: string,
  bounds: Bounds,
): RangeValue {
  const low = readNumber(params, lowKey, bounds.min)
  const high = readNumber(params, highKey, bounds.max)
  const clampedHigh = Math.min(
    Math.max(high, bounds.min + bounds.step),
    bounds.max,
  )
  const clampedLow = Math.min(
    Math.max(low, bounds.min),
    clampedHigh - bounds.step,
  )
  return [clampedLow, clampedHigh]
}

function writeRange(
  params: URLSearchParams,
  lowKey: string,
  highKey: string,
  [low, high]: RangeValue,
  bounds: Bounds,
) {
  if (low > bounds.min) {
    params.set(lowKey, String(low))
  } else {
    params.delete(lowKey)
  }
  if (high < bounds.max) {
    params.set(highKey, String(high))
  } else {
    params.delete(highKey)
  }
}

export default function RecipesPage() {
  usePageTitle('Recipes')
  const [params, setParams] = useSearchParams()
  const q = params.get('q') ?? ''
  const category = params.get('category') ?? ''
  const cuisine = params.get('cuisine') ?? ''
  const page = Math.max(1, Number(params.get('page') ?? '1') || 1)

  const [kcalRange, setKcalRange] = useState<RangeValue>(() =>
    readRange(params, 'kcal_min', 'kcal_max', KCAL),
  )
  const [proteinRange, setProteinRange] = useState<RangeValue>(() =>
    readRange(params, 'protein_min', 'protein_max', PROTEIN),
  )

  // Keep the sliders in sync when the URL changes from elsewhere, such as the
  // browser back button or Clear filters.
  const rangeSignature = [
    params.get('kcal_min'),
    params.get('kcal_max'),
    params.get('protein_min'),
    params.get('protein_max'),
  ].join('|')
  const [syncedSignature, setSyncedSignature] = useState(rangeSignature)
  if (rangeSignature !== syncedSignature) {
    setSyncedSignature(rangeSignature)
    setKcalRange(readRange(params, 'kcal_min', 'kcal_max', KCAL))
    setProteinRange(readRange(params, 'protein_min', 'protein_max', PROTEIN))
  }

  const [kcalMin, kcalMax] = readRange(params, 'kcal_min', 'kcal_max', KCAL)
  const [proteinMin, proteinMax] = readRange(
    params,
    'protein_min',
    'protein_max',
    PROTEIN,
  )

  const stats = useQuery({ queryKey: ['stats'], queryFn: getStats })
  const recipes = useQuery({
    queryKey: [
      'recipes',
      { q, category, cuisine, kcalMin, kcalMax, proteinMin, proteinMax, page },
    ],
    queryFn: () =>
      getRecipes({
        q,
        category,
        cuisine,
        kcalMin: kcalMin > KCAL.min ? kcalMin : undefined,
        kcalMax: kcalMax < KCAL.max ? kcalMax : undefined,
        proteinMin: proteinMin > PROTEIN.min ? proteinMin : undefined,
        proteinMax: proteinMax < PROTEIN.max ? proteinMax : undefined,
        page,
        pageSize: PAGE_SIZE,
      }),
    placeholderData: (previous) => previous,
  })

  // Push slider movements into the URL after a short pause so dragging does
  // not fire a request on every step.
  useEffect(() => {
    const timeout = window.setTimeout(() => {
      const next = new URLSearchParams(params)
      writeRange(next, 'kcal_min', 'kcal_max', kcalRange, KCAL)
      writeRange(next, 'protein_min', 'protein_max', proteinRange, PROTEIN)
      if (next.toString() !== params.toString()) {
        next.delete('page')
        setParams(next, { replace: true })
      }
    }, 300)

    return () => window.clearTimeout(timeout)
  }, [kcalRange, proteinRange, params, setParams])

  function updateParam(key: string, value: string) {
    const next = new URLSearchParams(params)
    // Preserve a slider move that has not reached the URL yet.
    writeRange(next, 'kcal_min', 'kcal_max', kcalRange, KCAL)
    writeRange(next, 'protein_min', 'protein_max', proteinRange, PROTEIN)
    if (value) {
      next.set(key, value)
    } else {
      next.delete(key)
    }
    if (key !== 'page') {
      next.delete('page')
    }
    setParams(next)
  }

  function clearFilters() {
    setKcalRange([KCAL.min, KCAL.max])
    setProteinRange([PROTEIN.min, PROTEIN.max])
    setParams(new URLSearchParams())
  }

  const hasNutritionFilters =
    kcalRange[0] > KCAL.min ||
    kcalRange[1] < KCAL.max ||
    proteinRange[0] > PROTEIN.min ||
    proteinRange[1] < PROTEIN.max
  const hasFilters = Boolean(q || category || cuisine) || hasNutritionFilters
  const total = recipes.data?.count

  return (
    <>
      <section className="bg-heat">
        <div className="shell pb-12 pt-8 md:pb-16 md:pt-10">
          <nav aria-label="Breadcrumb" className="text-small text-ink/80">
            <Link
              to="/"
              className="inline-flex min-h-11 items-center font-semibold underline decoration-2 underline-offset-4 hover:decoration-4"
            >
              Home
            </Link>
            <span aria-hidden="true"> / </span>
            <span>Recipes</span>
          </nav>

          <div className="mt-6 grid gap-8 lg:grid-cols-12 lg:items-end lg:gap-8">
            <div className="lg:col-span-8">
              <h1 className="hero-rise font-display text-poster">Recipes</h1>
              <p className="mt-6 max-w-xl text-lead text-ink/80">
                Search every recipe by name, then narrow the list by category,
                cuisine, calories and protein. Open one to see its ingredients,
                method, nutrition and original source.
              </p>
            </div>

            <div className="lg:col-span-4 lg:pb-2">
              <p
                aria-live="polite"
                className="font-display text-stat tabular-nums"
              >
                {total ?? '—'}
              </p>
              <p className="mt-2 text-small text-ink/80">
                {hasFilters ? 'matching recipes' : 'recipes to cook'}
              </p>
            </div>
          </div>
        </div>
      </section>

      <section className="bg-field section-sm">
        <div className="shell">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-[1fr_220px_220px]">
            <div className="md:col-span-2 lg:col-span-1">
              <SearchForm
                key={q}
                initialValue={q}
                onSubmit={(value) => updateParam('q', value)}
                label="Search recipes"
                placeholder="Search by recipe name"
              />
            </div>
            <div>
              <label htmlFor="category" className="sr-only">
                Filter by category
              </label>
              <select
                id="category"
                value={category}
                onChange={(event) => updateParam('category', event.target.value)}
                className="min-h-14 w-full bg-ink px-5 text-body text-heat outline-none focus-visible:outline-3 focus-visible:outline-offset-[-3px] focus-visible:outline-heat"
              >
                <option value="">Every category</option>
                {stats.data?.categories.map((item) => (
                  <option key={item.category} value={item.category}>
                    {taxonomyLabel(item.category)} ({item.count})
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="cuisine" className="sr-only">
                Filter by cuisine
              </label>
              <select
                id="cuisine"
                value={cuisine}
                onChange={(event) => updateParam('cuisine', event.target.value)}
                className="min-h-14 w-full bg-ink px-5 text-body text-heat outline-none focus-visible:outline-3 focus-visible:outline-offset-[-3px] focus-visible:outline-heat"
              >
                <option value="">Every cuisine</option>
                {stats.data?.cuisines.map((item) => (
                  <option key={item.cuisine} value={item.cuisine}>
                    {taxonomyLabel(item.cuisine)} ({item.count})
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="mt-6 border-t border-ink/15 pt-6">
            <p className="text-small font-semibold uppercase tracking-wide text-muted-field">
              Nutrition per serving
            </p>
            <div className="mt-4 grid gap-6 md:grid-cols-2 md:gap-10">
              <RangeSlider
                label="Calories"
                min={KCAL.min}
                max={KCAL.max}
                step={KCAL.step}
                unit="kcal"
                value={kcalRange}
                onChange={setKcalRange}
              />
              <RangeSlider
                label="Protein"
                min={PROTEIN.min}
                max={PROTEIN.max}
                step={PROTEIN.step}
                unit="g"
                value={proteinRange}
                onChange={setProteinRange}
              />
            </div>
            <p className="mt-4 text-small text-muted-field">
              Narrowing a range only includes recipes that have nutrition data.
            </p>
          </div>

          {hasFilters && (
            <div className="mt-2 flex justify-end">
              <button
                type="button"
                onClick={clearFilters}
                className="inline-flex min-h-11 items-center text-small font-semibold text-ink underline decoration-2 underline-offset-4 hover:decoration-4"
              >
                Clear filters
              </button>
            </div>
          )}

          <div className="mt-8">
            {recipes.isPending && <LoadingRows label="Loading recipes" rows={6} />}
            {recipes.isError && (
              <ErrorState
                message={(recipes.error as Error).message}
                onRetry={() => recipes.refetch()}
              />
            )}
            {recipes.data && recipes.data.items.length === 0 && (
              <EmptyState>
                No recipes match this search. Try a shorter phrase, widen the
                nutrition range, or clear the filters.
              </EmptyState>
            )}
            {recipes.data && recipes.data.items.length > 0 && (
              <ul className="space-y-1">
                {recipes.data.items.map((recipe) => (
                  <li key={recipe.id} className="min-w-0">
                    <RecipeListItem recipe={recipe} />
                  </li>
                ))}
              </ul>
            )}
          </div>

          {recipes.data && (
            <Pagination
              page={page}
              count={recipes.data.count}
              pageSize={PAGE_SIZE}
              onPageChange={(nextPage) => updateParam('page', String(nextPage))}
            />
          )}
        </div>
      </section>
    </>
  )
}
