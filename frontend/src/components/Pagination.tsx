type PaginationProps = {
  page: number
  count: number
  pageSize: number
  onPageChange: (page: number) => void
}

function pageWindow(page: number, totalPages: number): number[] {
  const start = Math.max(1, Math.min(page - 2, totalPages - 4))
  const end = Math.min(totalPages, start + 4)
  return Array.from({ length: end - start + 1 }, (_, index) => start + index)
}

const navButton =
  'min-h-11 bg-ink px-4 text-small font-semibold text-heat transition-colors hover:bg-heat hover:text-ink disabled:cursor-not-allowed disabled:bg-ink/10 disabled:text-ink/60'

export default function Pagination({
  page,
  count,
  pageSize,
  onPageChange,
}: PaginationProps) {
  const totalPages = Math.max(1, Math.ceil(count / pageSize))
  if (totalPages <= 1) {
    return null
  }

  const pages = pageWindow(page, totalPages)

  return (
    <nav
      aria-label="Pagination"
      className="mt-12 flex flex-wrap items-center gap-2"
    >
      <button
        type="button"
        onClick={() => onPageChange(page - 1)}
        disabled={page <= 1}
        className={navButton}
      >
        Previous
      </button>
      {pages.map((number) => (
        <button
          key={number}
          type="button"
          onClick={() => onPageChange(number)}
          aria-current={number === page ? 'page' : undefined}
          className={`min-h-11 min-w-11 px-3 text-small font-semibold transition-colors ${
            number === page
              ? 'bg-ink text-heat'
              : 'bg-ink/10 text-ink hover:bg-ink hover:text-heat'
          }`}
        >
          {number}
        </button>
      ))}
      <button
        type="button"
        onClick={() => onPageChange(page + 1)}
        disabled={page >= totalPages}
        className={navButton}
      >
        Next
      </button>
      <span className="ml-auto text-small text-muted-field">
        Page {page} of {totalPages}
      </span>
    </nav>
  )
}
