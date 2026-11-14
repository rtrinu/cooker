export type RangeValue = [number, number]

type RangeSliderProps = {
  label: string
  min: number
  max: number
  step: number
  value: RangeValue
  onChange: (value: RangeValue) => void
  unit: string
}

function formatSummary(
  [low, high]: RangeValue,
  min: number,
  max: number,
  unit: string,
) {
  if (low <= min && high >= max) {
    return 'Any'
  }
  if (low <= min) {
    return `≤ ${high} ${unit}`
  }
  if (high >= max) {
    return `${low}+ ${unit}`
  }
  return `${low}–${high} ${unit}`
}

export default function RangeSlider({
  label,
  min,
  max,
  step,
  value,
  onChange,
  unit,
}: RangeSliderProps) {
  const [low, high] = value
  const span = max - min
  const lowPercent = ((low - min) / span) * 100
  const highPercent = ((high - min) / span) * 100

  return (
    <div>
      <div className="flex items-baseline justify-between gap-4">
        <span className="text-small font-semibold">{label}</span>
        <span className="text-small tabular-nums text-muted-field">
          {formatSummary(value, min, max, unit)}
        </span>
      </div>

      <div className="relative mt-2 h-8">
        <div
          aria-hidden="true"
          className="absolute inset-x-0 top-1/2 h-1 -translate-y-1/2 bg-ink/20"
        />
        <div
          aria-hidden="true"
          className="absolute top-1/2 h-1 -translate-y-1/2 bg-ink"
          style={{ left: `${lowPercent}%`, right: `${100 - highPercent}%` }}
        />
        <input
          type="range"
          className="range-input z-10"
          min={min}
          max={high - step}
          step={step}
          value={low}
          aria-label={`${label} minimum`}
          aria-valuetext={`${low} ${unit}`}
          onChange={(event) => onChange([Number(event.target.value), high])}
        />
        <input
          type="range"
          className="range-input z-20"
          min={low + step}
          max={max}
          step={step}
          value={high}
          aria-label={`${label} maximum`}
          aria-valuetext={`${high} ${unit}`}
          onChange={(event) => onChange([low, Number(event.target.value)])}
        />
      </div>

      <div className="mt-1 flex justify-between text-small tabular-nums text-muted-field">
        <span>
          {min} {unit}
        </span>
        <span>
          {max}+ {unit}
        </span>
      </div>
    </div>
  )
}
