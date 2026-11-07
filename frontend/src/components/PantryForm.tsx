import {
  useDeferredValue,
  useState,
  type FormEvent,
  type ReactNode,
} from 'react'
import { useQuery } from '@tanstack/react-query'
import { getIngredientSuggestions } from '../api/client'
import { splitPantry } from '../lib/pantry'
import { Button } from './Button'

type PantryFormProps = {
  initialValue?: string
  onSubmit: (value: string) => void
  compact?: boolean
  hero?: boolean
  support?: ReactNode
  id?: string
}

export default function PantryForm({
  initialValue = '',
  onSubmit,
  compact = false,
  hero = false,
  support,
  id = 'pantry',
}: PantryFormProps) {
  const [value, setValue] = useState(initialValue)
  const deferred = useDeferredValue(value.trim())
  const suggestions = useQuery({
    queryKey: ['ingredient-suggestions', deferred],
    queryFn: () => getIngredientSuggestions(deferred),
    enabled: deferred.length >= 2,
    staleTime: 60_000,
  })

  const chosen = new Set(splitPantry(value).map((item) => item.toLowerCase()))
  const visibleSuggestions = (suggestions.data ?? [])
    .filter((ingredient) => !chosen.has(ingredient.name.toLowerCase()))
    .slice(0, 6)

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    onSubmit(value.trim())
  }

  function addIngredient(name: string) {
    if (chosen.has(name.toLowerCase())) {
      return
    }
    // Suggestions describe the word being typed, so replace the last
    // comma-separated term instead of appending a second one.
    const parts = value
      .split(',')
      .slice(0, -1)
      .map((part) => part.trim())
      .filter(Boolean)
    setValue([...parts, name].join(', '))
  }

  const suggestionList = visibleSuggestions.length > 0 && (
    <div className="mt-4 max-w-3xl">
      <p className="text-sm text-ink/70">Add an ingredient</p>
      <ul className="mt-2 flex flex-wrap gap-2" aria-label="Ingredient suggestions">
        {visibleSuggestions.map((ingredient) => (
          <li key={ingredient.id}>
            <button
              type="button"
              onClick={() => addIngredient(ingredient.name)}
              className="bg-ink px-3 py-2 text-sm font-semibold text-heat transition-colors hover:bg-field hover:text-ink focus-visible:outline-3 focus-visible:outline-offset-3 focus-visible:outline-ink"
            >
              {ingredient.name}
            </button>
          </li>
        ))}
      </ul>
    </div>
  )

  if (hero) {
    return (
      <form onSubmit={handleSubmit} className="mt-10 md:mt-14">
        <h1 className="font-display text-[clamp(3.5rem,11vw,10rem)] leading-[0.86] tracking-[-0.02em]">
          <span className="block">Cook from</span>
          <span className="mt-2 block bg-ember px-3 focus-within:outline-3 focus-within:outline-offset-4 focus-within:outline-ink md:px-5">
            <label htmlFor={id} className="sr-only">
              Ingredients you already have
            </label>
            <input
              id={id}
              type="text"
              value={value}
              onChange={(event) => setValue(event.target.value)}
              placeholder="what you have"
              autoComplete="off"
              autoCapitalize="none"
              spellCheck={false}
              aria-describedby={`${id}-hint`}
              className="w-full bg-transparent py-1 text-inherit text-ink outline-none placeholder:text-ink/50"
            />
          </span>
        </h1>

        {support && <div className="mt-5 max-w-2xl">{support}</div>}

        <div className="mt-7 flex flex-wrap items-center gap-x-5 gap-y-4">
          <Button type="submit" tone="ink">
            Find recipes
          </Button>
          <p id={`${id}-hint`} className="text-sm text-ink/70">
            Separate ingredients with commas. Partial matches count.
          </p>
        </div>

        {suggestionList}
      </form>
    )
  }

  return (
    <form onSubmit={handleSubmit} className={compact ? 'mt-6' : 'mt-9'}>
      <label htmlFor={id} className="sr-only">
        Ingredients you already have
      </label>
      <div className="flex max-w-3xl flex-col gap-2 sm:flex-row">
        <input
          id={id}
          type="text"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          placeholder="eggs, flour, butter"
          autoComplete="off"
          autoCapitalize="none"
          spellCheck={false}
          aria-describedby={`${id}-hint`}
          className="min-h-14 min-w-0 flex-1 bg-ink px-5 text-body text-heat outline-none placeholder:text-heat/50 focus-visible:outline-3 focus-visible:outline-offset-[-3px] focus-visible:outline-field"
        />
        <Button type="submit" tone="ink">
          Find recipes
        </Button>
      </div>
      <p id={`${id}-hint`} className="mt-2 text-sm text-ink/70">
        Separate ingredients with commas. Partial matches count.
      </p>

      {suggestionList}
    </form>
  )
}
