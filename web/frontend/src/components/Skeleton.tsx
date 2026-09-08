/**
 * Skeleton loader (UX P0).
 *
 * Drop-in replacement for `<p>Cargando…</p>` text. Provides a shimmer
 * animation that respects `prefers-reduced-motion` automatically.
 *
 * Sizes: text, row (multiple text lines), circle (avatars/icons).
 */

interface SkeletonTextProps {
  width?: string | number;
  height?: string | number;
  className?: string;
}

export function SkeletonText({
  width = "100%",
  height,
  className = "",
}: SkeletonTextProps) {
  return (
    <span
      className={`skeleton skeleton-text ${className}`}
      style={{
        width: typeof width === "number" ? `${width}px` : width,
        height: height ? (typeof height === "number" ? `${height}px` : height) : undefined,
      }}
      aria-hidden="true"
    />
  );
}

interface SkeletonRowProps {
  lines?: number;
  className?: string;
}

export function SkeletonRow({ lines = 3, className = "" }: SkeletonRowProps) {
  return (
    <div className={`skeleton-row ${className}`} aria-hidden="true">
      {Array.from({ length: lines }).map((_, i) => (
        <SkeletonText key={i} width={`${100 - i * 8}%`} />
      ))}
    </div>
  );
}

interface SkeletonCircleProps {
  size: number;
  className?: string;
}

export function SkeletonCircle({ size, className = "" }: SkeletonCircleProps) {
  return (
    <span
      className={`skeleton skeleton-circle ${className}`}
      style={{ width: size, height: size }}
      aria-hidden="true"
    />
  );
}

/**
 * SkeletonTable — renders `rows × cols` skeleton cells.
 */
interface SkeletonTableProps {
  rows: number;
  cols: number;
  className?: string;
}

export function SkeletonTable({
  rows,
  cols,
  className = "",
}: SkeletonTableProps) {
  return (
    <table
      className={`skeleton-table ${className}`}
      aria-busy="true"
      aria-live="polite"
    >
      <tbody>
        {Array.from({ length: rows }).map((_, r) => (
          <tr key={r}>
            {Array.from({ length: cols }).map((__, c) => (
              <td key={c}>
                <SkeletonText width="80%" />
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
