const LABELS: Record<string, string> = {
  'american-historical': 'Classic',
  'ye-old-american': 'Classic',
  modern: 'Modern',
}

const LICENSES: Record<string, string> = {
  'public-domain': 'Public domain',
}

export function taxonomyLabel(value: string) {
  const known = LABELS[value]
  if (known) {
    return known
  }

  // Values arrive as slugs ("east-asian") but the stored data is not always
  // normalised ("middle eastern"), so normalise before title-casing.
  return value
    .replaceAll('_', ' ')
    .replaceAll('-', ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase())
}

export function licenseLabel(value: string) {
  return LICENSES[value] ?? value
}
