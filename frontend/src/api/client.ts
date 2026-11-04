import createClient from 'openapi-fetch'
import type { components, paths } from './schema'

export const api = createClient<paths>({
  baseUrl: import.meta.env.VITE_API_ORIGIN ?? '',
})

export type RecipeList = components['schemas']['RecipeListOut']
export type RecipeDetail = components['schemas']['RecipeDetailOut']
export type RecipeIngredient = components['schemas']['RecipeIngredientOut']
export type Ingredient = components['schemas']['IngredientOut']
export type Stats = components['schemas']['StatsOut']
export type CategoryCount = components['schemas']['CategoryCountOut']

type ApiResult<T> = {
  data?: T
  error?: unknown
  response: Response
}

function unwrap<T>(result: ApiResult<T>): T {
  if (result.data !== undefined) {
    return result.data
  }

  const detail = (result.error as { detail?: string } | undefined)?.detail
  throw new Error(detail ?? `Request failed (${result.response.status})`)
}

export type RecipeQuery = {
  q?: string
  category?: string
  page?: number
  pageSize?: number
}

export async function getRecipes({
  q,
  category,
  page = 1,
  pageSize = 20,
}: RecipeQuery = {}) {
  return unwrap(
    await api.GET('/api/recipes/', {
      params: {
        query: {
          q: q || undefined,
          category: category || undefined,
          page,
          page_size: pageSize,
        },
      },
    }),
  )
}

export async function getRecipeBySlug(slug: string) {
  return unwrap(
    await api.GET('/api/recipes/slug/{slug}', {
      params: { path: { slug } },
    }),
  )
}

export type IngredientQuery = {
  q?: string
  category?: string
  page?: number
  pageSize?: number
}

export async function getIngredients({
  q,
  category,
  page = 1,
  pageSize = 24,
}: IngredientQuery = {}) {
  return unwrap(
    await api.GET('/api/ingredients/', {
      params: {
        query: {
          q: q || undefined,
          category: category || undefined,
          page,
          page_size: pageSize,
        },
      },
    }),
  )
}

export async function getStats() {
  return unwrap(await api.GET('/api/stats'))
}
