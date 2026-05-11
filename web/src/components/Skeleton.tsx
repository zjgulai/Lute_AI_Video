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
