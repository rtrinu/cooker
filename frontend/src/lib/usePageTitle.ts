import { useEffect } from 'react'

const SITE = 'Cooker — cook from what you have'

export function usePageTitle(title?: string) {
  useEffect(() => {
    document.title = title ? `${title} — Cooker` : SITE
  }, [title])
}
