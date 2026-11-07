import { useId, useState, type FormEvent } from 'react'
import { Button } from './Button'

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
        className="min-h-14 min-w-0 flex-1 bg-ink px-5 text-body text-field outline-none placeholder:text-field/50 focus-visible:outline-3 focus-visible:outline-offset-[-3px] focus-visible:outline-heat"
      />
      <Button type="submit" tone="ink">
        {buttonLabel}
      </Button>
    </form>
  )
}
