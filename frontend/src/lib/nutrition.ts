import type { Nutrition } from '../api/client'
import { taxonomyLabel } from './labels'

export type NutritionMacro = 'kcal' | 'protein_g' | 'carbs_g' | 'fat_g' | 'fiber_g'

type WarningCopy = {
  label: string
  detail: string
}

// The API keeps warnings as stable codes. The UI owns the words so the
// backend can add codes without breaking a page.
const WARNING_COPY: Record<string, WarningCopy> = {
  partial: {
    label: 'Lower bound',
    detail:
      'Some ingredients could not be measured, so only the measured lines are counted.',
  },
  'low-confidence': {
    label: 'Weak estimate',
    detail:
      'The ingredient matches and measures behind this panel are approximate.',
  },
  'ambiguous-measure': {
    label: 'Ambiguous measure',
    detail: 'At least one amount matched more than one possible measure.',
  },
  'standard-weight': {
    label: 'Standard weight',
    detail:
      'At least one amount used a standard kitchen weight instead of a measured one.',
  },
  'macro-mismatch': {
    label: 'Macro mismatch',
    detail:
      'The calories do not line up with the protein, carbohydrate and fat totals.',
  },
  'implausible-energy-density': {
    label: 'Implausible density',
    detail: 'The energy per 100 g is above what a real dish can contain.',
  },
}

export type NutritionWarning = WarningCopy & { code: string }

export function hasNutritionWarning(nutrition: Nutrition, code: string) {
  return nutrition.warnings.includes(code)
}

export function isPartialNutrition(nutrition: Nutrition) {
  return (
    nutrition.method === 'computed' && hasNutritionWarning(nutrition, 'partial')
  )
}

export function confidencePercent(nutrition: Nutrition) {
  if (nutrition.confidence == null) {
    return null
  }
  return Math.round(nutrition.confidence * 100)
}

export function formatWeight(grams: number) {
  if (!grams) {
    return null
  }
  if (grams >= 1000) {
    return `${(grams / 1000).toFixed(1)} kg`
  }
  if (grams >= 10) {
    return `${Math.round(grams)} g`
  }
  if (grams >= 1) {
    return `${grams.toFixed(1)} g`
  }
  return `${grams.toFixed(2)} g`
}

export function nutrientsPer100g(
  nutrition: Nutrition,
  servings?: number | null,
): Record<NutritionMacro, number> | null {
  if (!nutrition.weight_g || !servings) {
    return null
  }
  // The panel is per serving but ``weight_g`` is the weight of the whole
  // recipe, so scale the serving back up before dividing by that mass.
  const factor = (100 * servings) / nutrition.weight_g
  return {
    kcal: nutrition.kcal * factor,
    protein_g: nutrition.protein_g * factor,
    carbs_g: nutrition.carbs_g * factor,
    fat_g: nutrition.fat_g * factor,
    fiber_g: nutrition.fiber_g * factor,
  }
}

export function nutritionWarnings(nutrition: Nutrition): NutritionWarning[] {
  return nutrition.warnings.map((code) => {
    const copy = WARNING_COPY[code]
    return {
      code,
      label: copy?.label ?? taxonomyLabel(code),
      detail: copy?.detail ?? `The panel was flagged "${code}".`,
    }
  })
}
