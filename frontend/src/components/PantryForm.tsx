import {
  useDeferredValue,
  useId,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from 'react'
import { useQuery } from '@tanstack/react-query'
import { getIngredientSuggestions } from '../api/client'
import { splitPantry } from '../lib/pantry'
import { Button } from './Button'
import IngredientPicker from './IngredientPicker'

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
  const [pickerOpen, setPickerOpen] = useState(false)
  const pickerId = useId()
  const pickerButtonRef = useRef<HTMLButtonElement>(null)
  const deferred = useDeferredValue(value.trim())
  const suggestions = useQuery({
    queryKey: ['ingredient-suggestions', deferred],
    queryFn: () => getIngredientSuggestions(deferred),
    enabled: deferred.length >= 2,
    staleTime: 60_000,
  })

  const terms = splitPantry(value)
  const uniqueTerms = [
    ...new Map(terms.map((term) => [term.toLowerCase(), term])).values(),
  ]
  const chosen = new Set(terms.map((item) => item.toLowerCase()))
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

  function toggleIngredient(name: string) {
    const key = name.toLowerCase()
    if (chosen.has(key)) {
      setValue(
        terms
          .filter((term) => term.toLowerCase() !== key)
          .join(', '),
      )
      return
    }
    setValue([...terms, name].join(', '))
  }

  const selectedList = uniqueTerms.length > 0 && (
    <ul className="mt-4 flex max-w-3xl flex-wrap gap-2" aria-label="Your ingredients">
      {uniqueTerms.map((term) => (
        <li key={term}>
          <button
            type="button"
            onClick={() => toggleIngredient(term)}
            className="group inline-flex min-h-11 items-center gap-2 bg-ink px-3 py-1 text-small font-semibold text-heat transition-[background-color,color,box-shadow] hover:bg-field hover:text-ink hover:shadow-[inset_0_0_0_2px_var(--color-ink)] focus-visible:outline-3 focus-visible:outline-offset-3 focus-visible:outline-ink"
          >
            {term}
            <span aria-hidden="true" className="text-body leading-none">
              ×
            </span>
            <span className="sr-only">Remove</span>
          </button>
        </li>
      ))}
    </ul>
  )

  function closePicker() {
    setPickerOpen(false)
    pickerButtonRef.current?.focus()
  }

  const pickerToggle = (
    <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2">
      <button
        ref={pickerButtonRef}
        type="button"
        onClick={() => setPickerOpen((current) => !current)}
        aria-expanded={pickerOpen}
        aria-controls={pickerId}
        className="inline-flex min-h-11 items-center gap-2 bg-ink px-4 text-small font-semibold text-heat transition-[background-color,color,box-shadow] hover:bg-field hover:text-ink hover:shadow-[inset_0_0_0_2px_var(--color-ink)] focus-visible:outline-3 focus-visible:outline-offset-3 focus-visible:outline-ink"
      >
        <span aria-hidden="true" className="text-body leading-none">
          {pickerOpen ? '−' : '+'}
        </span>
        Browse ingredients
      </button>
      {terms.length > 0 && (
        <button
          type="button"
          onClick={() => setValue('')}
          className="inline-flex min-h-11 min-w-11 items-center justify-center text-small font-semibold text-ink underline decoration-2 underline-offset-4 hover:decoration-4"
        >
          Clear all
        </button>
      )}
    </div>
  )

  const suggestionList = visibleSuggestions.length > 0 && (
    <div className="mt-4 max-w-3xl">
      <p className="text-small text-ink/80">Add an ingredient</p>
      <ul className="mt-2 flex flex-wrap gap-2" aria-label="Ingredient suggestions">
        {visibleSuggestions.map((ingredient) => (
          <li key={ingredient.id}>
            <button
              type="button"
              onClick={() => addIngredient(ingredient.name)}
              className="min-h-11 bg-ink px-3 py-2 text-small font-semibold text-heat transition-[background-color,color,box-shadow] hover:bg-field hover:text-ink hover:shadow-[inset_0_0_0_2px_var(--color-ink)] focus-visible:outline-3 focus-visible:outline-offset-3 focus-visible:outline-ink"
            >
              {ingredient.name}
            </button>
          </li>
        ))}
      </ul>
    </div>
  )

  const picker = pickerOpen && (
    <div id={pickerId}>
      <IngredientPicker
        selected={chosen}
        onToggle={toggleIngredient}
        onClear={() => setValue('')}
        onClose={closePicker}
      />
    </div>
  )

  if (hero) {
    return (
      <form onSubmit={handleSubmit} className="mt-10 md:mt-14">
        <h1 className="font-display text-poster">
          Cook from<span className="sr-only"> what you have</span>
        </h1>
        <div className="mt-3 bg-ink px-3 py-1 focus-within:outline-3 focus-within:outline-offset-[-3px] focus-within:outline-heat md:px-5">
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
            className="w-full bg-transparent py-1 font-display text-poster text-heat outline-none placeholder:text-heat/80"
          />
        </div>

        {support && <div className="mt-5 max-w-2xl">{support}</div>}

        {selectedList}

        <div className="mt-7 flex flex-wrap items-center gap-x-5 gap-y-4">
          <Button type="submit" tone="ink">
            Find recipes
          </Button>
          <p id={`${id}-hint`} className="text-small text-ink/80">
            Separate ingredients with commas. Partial matches count.
          </p>
        </div>

        {pickerToggle}
        {picker}
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
          className="min-h-14 min-w-0 flex-1 bg-ink px-5 text-body text-heat outline-none placeholder:text-heat/80 focus-visible:outline-3 focus-visible:outline-offset-[-3px] focus-visible:outline-heat"
        />
        <Button type="submit" tone="ink">
          Find recipes
        </Button>
      </div>
      <p id={`${id}-hint`} className="mt-2 text-small text-ink/80">
        Separate ingredients with commas. Partial matches count.
      </p>

      {selectedList}
      {pickerToggle}
      {picker}
      {suggestionList}
    </form>
  )
}
