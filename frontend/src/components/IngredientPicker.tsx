import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getAllIngredients, type Ingredient } from '../api/client'
import { commonRank, groupRank, ingredientGroup } from '../lib/ingredients'

const NOISE = [
  ' and ',
  ' or ',
  ' each',
  ' with ',
  ' without ',
  ' to taste',
  ' as needed',
  ' for ',
  ' about ',
  ' into ',
  ' per ',
]

const JUNK = new Set([
  'st',
  'jar',
  'can',
  'tin',
  'packet',
  'package',
  'bunch',
  'sprig',
  'pinch',
  'dash',
  'handful',
  'each',
  'diced',
  'sliced',
  'minced',
  'chopped',
  'beaten',
  'shredded',
  'grated',
  'crushed',
  'peeled',
  'cored',
  'cubed',
  'halved',
  'quartered',
  'rinsed',
  'drained',
  'seeded',
  'trimmed',
  'whites',
  'pestle',
  'optional',
])

const PREP =
  /\b(divided|plus more|more|sifted|raw|cooked|chopped|diced|sliced|minced|shredded|grated|crushed|peeled|cored|cubed|halved|quartered|rinsed|drained|seeded|trimmed|beaten|optional|scalded|salted|unsalted|packed|softened|melted|chilled|warm|hot|cold|boiling|clarified|room temperature|to taste|for frying|for serving|as needed|enough to fry with|or)\b/

const NOTE =
  /\d|\b(optional|optionnal|to taste|to serve|for serving|for frying|to fry|any type|any kind|or more|plus more|divided|about|approx|approximately|packed|softened|melted|sifted|chopped|diced|sliced|minced|shredded|grated|beaten|raw|cooked|chilled|warm|hot|cold|room temperature|as needed|unsalted|salted|scalded|is|was|used|use|best|works|sight)\b/

// Keep meaningful parentheticals ("Flour (almond)", "Cheese (feta)") so they
// stay searchable; drop quantity and prep notes ("Egg (3)", "Oil (to fry)").
function stripNoteParens(name: string) {
  return name.replace(/\(([^)]*)\)/g, (match, inner: string) =>
    NOTE.test(inner.toLowerCase()) ? ' ' : match,
  )
}

// Collapse recipe-line variants ("Oil (to fry)", "Olive Oil, divided") to one
// pickable entry, while keeping genuinely different foods apart.
function keyName(name: string) {
  let base = stripNoteParens(name.toLowerCase())
  const parts = base.split(',')
  if (parts.length > 1 && PREP.test(parts.slice(1).join(' '))) {
    base = parts[0]
  }
  return base.replace(/\s+/g, ' ').trim()
}

function displayName(name: string) {
  const cleaned = stripNoteParens(name)
    .replace(/\s+/g, ' ')
    .replace(/[\s,;:-]+$/, '')
    .replace(/\b(and|or|with|plus)$/i, '')
    .replace(/[\s,;:-]+$/, '')
    .trim()
  return cleaned.charAt(0).toUpperCase() + cleaned.slice(1)
}

function isClean(name: string) {
  const lower = name.toLowerCase()
  return (
    /[a-z]/.test(lower) &&
    name.length >= 2 &&
    name.length <= 42 &&
    !JUNK.has(lower) &&
    !NOISE.some((marker) => lower.includes(marker))
  )
}

type PickItem = { ingredient: Ingredient; group: string }

type Props = {
  selected: Set<string>
  onToggle: (name: string) => void
  onClear: () => void
  onClose: () => void
}

const chipBase =
  'inline-flex min-h-11 min-w-11 items-center justify-center px-3 text-small font-semibold transition-colors'
const chipOff = 'bg-ink/[0.06] text-ink hover:bg-ink hover:text-heat'
const chipOn = 'bg-ink text-heat'

export default function IngredientPicker({
  selected,
  onToggle,
  onClear,
  onClose,
}: Props) {
  const [q, setQ] = useState('')
  const [group, setGroup] = useState('')
  const ingredients = useQuery({
    queryKey: ['ingredients', 'all'],
    queryFn: getAllIngredients,
    staleTime: 5 * 60_000,
  })

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        onClose()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  const all = useMemo<PickItem[]>(() => {
    const byKey = new Map<string, PickItem>()
    for (const ingredient of ingredients.data?.items ?? []) {
      const raw = ingredient.name.trim()
      if (!isClean(raw)) {
        continue
      }
      const name = displayName(raw)
      if (!/[a-z]/i.test(name)) {
        continue
      }
      const key = keyName(name)
      if (!key) {
        continue
      }
      const existing = byKey.get(key)
      if (existing && existing.ingredient.name.length <= name.length) {
        continue
      }
      byKey.set(key, {
        ingredient: { ...ingredient, name },
        group: ingredientGroup(name, ingredient.category),
      })
    }
    // If a plainer entry exists ("Flour"), drop qualifier variants that only
    // repeat it ("Flour (basic wheat flour)"). Variants without a plain
    // counterpart stay, so "Flour (almond)" is still pickable.
    for (const key of [...byKey.keys()]) {
      const base = key.match(/^(.+?) \(.+\)$/)?.[1]
      if (base && byKey.has(base)) {
        byKey.delete(key)
      }
    }
    return [...byKey.values()].sort(
      (a, b) =>
        commonRank(a.ingredient.name) - commonRank(b.ingredient.name) ||
        a.ingredient.name.length - b.ingredient.name.length ||
        a.ingredient.name.localeCompare(b.ingredient.name),
    )
  }, [ingredients.data])

  const groups = useMemo(() => {
    const counts = new Map<string, number>()
    for (const item of all) {
      counts.set(item.group, (counts.get(item.group) ?? 0) + 1)
    }
    return [...counts.entries()].sort(
      (a, b) => groupRank(a[0]) - groupRank(b[0]) || b[1] - a[1],
    )
  }, [all])

  const filtered = useMemo(() => {
    const tokens = q.trim().toLowerCase().split(/\s+/).filter(Boolean)
    const pool = group ? all.filter((item) => item.group === group) : all
    return tokens.length > 0
      ? pool.filter((item) => {
          const name = item.ingredient.name.toLowerCase()
          return tokens.every((token) => name.includes(token))
        })
      : pool
  }, [all, group, q])

  const visible = filtered.slice(0, 160)
  const status = ingredients.isPending
    ? 'Loading ingredients…'
    : ingredients.isError
      ? 'Could not load the ingredient list. Type instead.'
      : `${filtered.length} ${filtered.length === 1 ? 'ingredient' : 'ingredients'}`

  return (
    <div
      id="ingredient-picker"
      role="group"
      aria-label="Browse ingredients"
      className="mt-3 max-w-4xl bg-field p-4 text-ink md:p-5"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-small font-semibold">
          Browse ingredients
          {selected.size > 0 ? ` · ${selected.size} selected` : ''}
        </p>
        <div className="flex items-center gap-4">
          {selected.size > 0 && (
            <button
              type="button"
              onClick={onClear}
              className="inline-flex min-h-11 min-w-11 items-center justify-center text-small font-semibold underline decoration-2 underline-offset-4 hover:decoration-4"
            >
              Clear all
            </button>
          )}
          <button
            type="button"
            onClick={onClose}
            className="inline-flex min-h-11 min-w-11 items-center justify-center text-small font-semibold underline decoration-2 underline-offset-4 hover:decoration-4"
          >
            Done
          </button>
        </div>
      </div>

      <label htmlFor="ingredient-picker-search" className="sr-only">
        Search ingredients
      </label>
      <input
        id="ingredient-picker-search"
        type="search"
        value={q}
        onChange={(event) => setQ(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter') {
            event.preventDefault()
          }
        }}
        placeholder="Search ingredients"
        autoFocus
        className="mt-3 min-h-12 w-full bg-ink px-4 text-body text-heat outline-none placeholder:text-heat/80 focus-visible:outline-3 focus-visible:outline-offset-[-3px] focus-visible:outline-heat"
      />

      <div className="-mx-1 mt-3 flex gap-2 overflow-x-auto px-1 pb-1 md:flex-wrap md:overflow-visible">
        <button
          type="button"
          aria-pressed={!group}
          onClick={() => setGroup('')}
          className={`${chipBase} shrink-0 ${!group ? chipOn : chipOff}`}
        >
          All
        </button>
        {groups.map(([label, count]) => (
          <button
            key={label}
            type="button"
            aria-pressed={group === label}
            onClick={() => setGroup((current) => (current === label ? '' : label))}
            className={`${chipBase} shrink-0 ${
              group === label ? chipOn : chipOff
            }`}
          >
            {label} ({count})
          </button>
        ))}
      </div>

      <p className="mt-4 text-small text-muted-field" aria-live="polite">
        {status}
      </p>

      {ingredients.isError && (
        <button
          type="button"
          onClick={() => ingredients.refetch()}
          className="mt-2 inline-flex min-h-11 items-center text-small font-semibold text-ink underline decoration-2 underline-offset-4 hover:decoration-4"
        >
          Try again
        </button>
      )}

      {ingredients.data && filtered.length === 0 && (
        <p className="mt-3 text-body text-muted-field">
          Nothing matches that search.
        </p>
      )}

      {visible.length > 0 && (
        <ul className="mt-2 flex max-h-80 flex-wrap gap-2 overflow-y-auto">
          {visible.map(({ ingredient }) => {
            const isSelected = selected.has(ingredient.name.toLowerCase())
            return (
              <li key={ingredient.id}>
                <button
                  type="button"
                  aria-pressed={isSelected}
                  onClick={() => onToggle(ingredient.name)}
                  className={`${chipBase} ${
                    isSelected ? chipOn : chipOff
                  }`}
                >
                  {isSelected ? '✓ ' : ''}
                  {ingredient.name}
                </button>
              </li>
            )
          })}
        </ul>
      )}

      {filtered.length > visible.length && (
        <p className="mt-3 text-small text-muted-field">
          Showing the first {visible.length}. Keep typing to narrow it.
        </p>
      )}
    </div>
  )
}
