import { useId, useState, type FormEvent } from 'react'

type SearchFormProps = {
  initialValue?: string
  onSubmit: (value: string) => void
  label: string
  placeholder: string
  buttonLabel?: string
}

export default function SearchForm({
  initialValue = '',
  onSubmit,
  label,
  placeholder,
  buttonLabel = 'Search',
}: SearchFormProps) {
  const id = useId()
  const [value, setValue] = useState(initialValue)

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    onSubmit(value.trim())
  }

  return (
    <form role="search" onSubmit={handleSubmit} className="flex w-full">
      <label htmlFor={id} className="sr-only">
        {label}
      </label>
      <input
        id={id}
        type="search"
        value={value}
        onChange={(event) => setValue(event.target.value)}
        placeholder={placeholder}
        className="min-w-0 flex-1 bg-surface px-4 py-3 text-base text-ink outline-none placeholder:text-muted/80 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent"
      />
      <button
        type="submit"
        className="bg-accent px-5 py-3 text-sm font-medium text-paper transition-colors hover:bg-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      >
        {buttonLabel}
      </button>
    </form>
  )
}
