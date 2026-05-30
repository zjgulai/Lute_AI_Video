export function CardSkeleton() {
  return (
    <div className="apple-card p-4 animate-pulse" aria-hidden="true">
      <div className="h-4 bg-zinc-200 rounded w-3/4 mb-3"></div>
      <div className="h-3 bg-zinc-200 rounded w-1/2 mb-2"></div>
      <div className="h-32 bg-zinc-200 rounded"></div>
    </div>
  );
}

export function ListSkeleton({ count = 8 }: { count?: number }) {
  return (
    <>
      {Array.from({ length: count }).map((_, i) => (
        <CardSkeleton key={i} />
      ))}
    </>
  );
}

export function TableRowSkeleton() {
  return (
    <tr className="animate-pulse" aria-hidden="true">
      <td className="px-4 py-3"><div className="h-3 bg-zinc-200 rounded w-24"></div></td>
      <td className="px-4 py-3"><div className="h-3 bg-zinc-200 rounded w-32"></div></td>
      <td className="px-4 py-3"><div className="h-3 bg-zinc-200 rounded w-16"></div></td>
      <td className="px-4 py-3"><div className="h-3 bg-zinc-200 rounded w-20"></div></td>
    </tr>
  );
}

export function RoutePageSkeleton({ cardCount = 6 }: { cardCount?: number }) {
  return (
    <div
      className="min-h-screen bg-[var(--color-bg)] overflow-x-hidden"
      aria-busy="true"
      aria-live="polite"
    >
      <div className="sticky top-0 z-40 bg-[var(--bg-page)]/85 backdrop-blur-xl border-b border-[var(--divider-subtle)]">
        <div className="max-w-[1440px] mx-auto px-4 sm:px-6 h-14 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-7 h-7 rounded-lg skeleton shrink-0" />
            <div className="hidden sm:block h-3 w-32 skeleton rounded" />
            <div className="flex items-center gap-2">
              <div className="h-8 w-8 skeleton rounded-lg" />
              <div className="h-8 w-8 skeleton rounded-lg" />
              <div className="h-8 w-8 skeleton rounded-lg" />
            </div>
          </div>
          <div className="h-8 w-16 skeleton rounded-full shrink-0" />
        </div>
      </div>

      <main className="max-w-6xl mx-auto px-4 sm:px-6 py-6 space-y-5">
        <div className="space-y-2">
          <div className="h-5 w-44 skeleton rounded" />
          <div className="h-3 w-full max-w-md skeleton rounded" />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: cardCount }).map((_, i) => (
            <div key={i} className="apple-card p-4 space-y-3">
              <div className="h-32 skeleton rounded-xl" />
              <div className="h-3 w-3/4 skeleton rounded" />
              <div className="h-2.5 w-1/2 skeleton rounded" />
            </div>
          ))}
        </div>
      </main>
    </div>
  );
}
