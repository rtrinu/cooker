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
    <nav aria-label="Pagination" className="mt-10 flex flex-wrap items-center gap-2">
      <button
        type="button"
        onClick={() => onPageChange(page - 1)}
        disabled={page <= 1}
        className="bg-surface px-4 py-2 text-sm transition-colors hover:bg-surface-deep disabled:cursor-not-allowed disabled:opacity-40"
      >
        Previous
      </button>
      {pages.map((number) => (
        <button
          key={number}
          type="button"
          onClick={() => onPageChange(number)}
          aria-current={number === page ? 'page' : undefined}
          className={`min-w-10 px-3 py-2 text-sm transition-colors ${
            number === page
              ? 'bg-accent text-paper'
              : 'bg-surface hover:bg-surface-deep'
          }`}
        >
          {number}
        </button>
      ))}
      <button
        type="button"
        onClick={() => onPageChange(page + 1)}
        disabled={page >= totalPages}
        className="bg-surface px-4 py-2 text-sm transition-colors hover:bg-surface-deep disabled:cursor-not-allowed disabled:opacity-40"
      >
        Next
      </button>
      <span className="ml-2 text-sm text-muted">
        Page {page} of {totalPages}
      </span>
    </nav>
  )
}
