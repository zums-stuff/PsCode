export function verdictColorClass(verdict: string): string {
  switch (verdict) {
    case "AC":
    case "DONE":
      return "verdict-accepted";
    case "WA":
    case "FAILED":
      return "verdict-failed";
    case "TLE":
    case "RE":
    case "CE":
      return "verdict-rejected";
    case "QUEUED":
    case "RUNNING":
      return "verdict-waiting";
    default:
      return "verdict-waiting";
  }
}

export function verdictFallbackClass(verdict: string): string {
  switch (verdict) {
    case "AC":
    case "DONE":
      return "status-green";
    case "WA":
    case "FAILED":
      return "status-red";
    case "TLE":
      return "status-yellow";
    case "RE":
      return "status-orange";
    case "CE":
      return "status-purple";
    case "QUEUED":
    case "RUNNING":
      return "status-gray";
    default:
      return "status-gray";
  }
}

export function ratingColorClass(rating: number): string {
  if (rating >= 2900) return "rating-2900";
  if (rating >= 2600) return "rating-2600";
  if (rating >= 2400) return "rating-2400";
  if (rating >= 2200) return "rating-2200";
  if (rating >= 1900) return "rating-1900";
  if (rating >= 1600) return "rating-1600";
  if (rating >= 1400) return "rating-1400";
  if (rating >= 1200) return "rating-1200";
  return "rating-500";
}

export function ratingBorderClass(rating: number): string {
  if (rating >= 2900) return "rating-border-2900";
  if (rating >= 2600) return "rating-border-2600";
  if (rating >= 2400) return "rating-border-2400";
  if (rating >= 2200) return "rating-border-2200";
  if (rating >= 1900) return "rating-border-1900";
  if (rating >= 1600) return "rating-border-1600";
  if (rating >= 1400) return "rating-border-1400";
  if (rating >= 1200) return "rating-border-1200";
  return "rating-border-500";
}
