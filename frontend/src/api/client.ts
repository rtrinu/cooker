import createClient from 'openapi-fetch'
import type { components, paths } from './schema'

const api = createClient<paths>({
  baseUrl: import.meta.env.VITE_API_ORIGIN ?? '',
})

export type RecipeList = components['schemas']['RecipeListOut']
export type Nutrition = components['schemas']['NutritionOut']
export type FinderRecipe = components['schemas']['FinderRecipeOut']
export type Ingredient = components['schemas']['IngredientOut']

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
  cuisine?: string
  contributor?: string
  tag?: string
  kcalMin?: number
  kcalMax?: number
  proteinMin?: number
  proteinMax?: number
  page?: number
  pageSize?: number
}

export async function getRecipes({
  q,
  category,
  cuisine,
  contributor,
  tag,
  kcalMin,
  kcalMax,
  proteinMin,
  proteinMax,
  page = 1,
  pageSize = 20,
}: RecipeQuery = {}) {
  return unwrap(
    await api.GET('/api/recipes/', {
      params: {
        query: {
          q: q || undefined,
          category: category || undefined,
          cuisine: cuisine || undefined,
          contributor: contributor || undefined,
          tag: tag || undefined,
          kcal_min: kcalMin,
          kcal_max: kcalMax,
          protein_min: proteinMin,
          protein_max: proteinMax,
          page,
          page_size: pageSize,
        },
      },
    }),
  )
}

export async function getRecipeBySlug(slug: string) {
  // Old links and hand-entered recipes can use the numeric id instead of a
  // slug. The API keeps both routes, so pick the one the url matches.
  if (/^\d+$/.test(slug)) {
    return unwrap(
      await api.GET('/api/recipes/{recipe_id}', {
        params: { path: { recipe_id: Number(slug) } },
      }),
    )
  }

  return unwrap(
    await api.GET('/api/recipes/slug/{slug}', {
      params: { path: { slug } },
    }),
  )
}

export type FinderQuery = {
  ingredients: string
  page?: number
  pageSize?: number
}

export async function getFinder({
  ingredients,
  page = 1,
  pageSize = 20,
}: FinderQuery) {
  return unwrap(
    await api.GET('/api/recipes/finder', {
      params: {
        query: {
          ingredients,
          page,
          page_size: pageSize,
        },
      },
    }),
  )
}

export async function getIngredientSuggestions(q: string) {
  return unwrap(
    await api.GET('/api/ingredients/suggestions', {
      params: { query: { q } },
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

const INGREDIENT_PAGE_SIZE = 100

export async function getAllIngredients() {
  // The API caps a page at 100 rows, so walk every page once and merge them.
  const first = await unwrap(
    await api.GET('/api/ingredients/', {
      params: { query: { page: 1, page_size: INGREDIENT_PAGE_SIZE } },
    }),
  )
  const pageCount = Math.ceil(first.count / INGREDIENT_PAGE_SIZE)
  if (pageCount <= 1) {
    return first
  }

  const rest = await Promise.all(
    Array.from({ length: pageCount - 1 }, async (_, index) => {
      return unwrap(
        await api.GET('/api/ingredients/', {
          params: {
            query: { page: index + 2, page_size: INGREDIENT_PAGE_SIZE },
          },
        }),
      )
    }),
  )

  return {
    ...first,
    items: [...first.items, ...rest.flatMap((page) => page.items)],
  }
}

export async function getStats() {
  return unwrap(await api.GET('/api/stats'))
}
