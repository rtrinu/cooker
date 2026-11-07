const STOPWORDS = new Set([
  'fresh',
  'frozen',
  'canned',
  'dried',
  'raw',
  'cooked',
  'prepared',
  'chopped',
  'diced',
  'sliced',
  'minced',
  'shredded',
  'peeled',
  'cored',
  'cubed',
  'grated',
  'crushed',
  'halved',
  'quartered',
  'rinsed',
  'drained',
  'seeded',
  'trimmed',
  'optional',
  'and',
  'or',
  'with',
  'without',
  'of',
  'the',
  'a',
  'an',
  'to',
  'in',
  'into',
  'large',
  'small',
  'medium',
  'cold',
  'hot',
  'warm',
  'sweet',
  'sour',
  'sifted',
  'beaten',
])

function singular(token: string) {
  if (token.length <= 3 || token.endsWith('ss') || token.endsWith('us')) {
    return token
  }
  if (token.endsWith('ies') && token.length > 4) {
    return `${token.slice(0, -3)}y`
  }
  if (token.endsWith('oes')) {
    return token.slice(0, -2)
  }
  if (token.endsWith('s')) {
    return token.slice(0, -1)
  }
  return token
}

export function pantryTokens(text: string) {
  return new Set(
    (text.toLowerCase().match(/[a-z0-9]+/g) ?? [])
      .map(singular)
      .filter((token) => !STOPWORDS.has(token)),
  )
}

export function splitPantry(text: string) {
  return text
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean)
}

export function termsTouch(term: string, ingredient: string) {
  const a = pantryTokens(term)
  const b = pantryTokens(ingredient)
  if (!a.size || !b.size) {
    return false
  }
  const aInB = [...a].every((token) => b.has(token))
  const bInA = [...b].every((token) => a.has(token))
  return aInB || bInA
}
