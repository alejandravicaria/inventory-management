// Pure restock recommendation logic (no Vue or I/O) so it can be unit tested directly.

// Lower rank = bought first
const TREND_RANK = { increasing: 0, stable: 1, decreasing: 2 }

export function getShortfall(item) {
  return Math.max(0, item.forecasted_demand - item.quantity_on_hand)
}

// Percent growth of forecast over current demand. A zero baseline with any
// forecast is treated as unbounded growth so it ranks first within its trend.
export function getGrowth(item) {
  if (!item.current_demand) return item.forecasted_demand > 0 ? Infinity : 0
  return (item.forecasted_demand - item.current_demand) / item.current_demand
}

export function rankCatalog(catalog) {
  return [...catalog].sort((a, b) => {
    const trendDiff = (TREND_RANK[a.trend] ?? 3) - (TREND_RANK[b.trend] ?? 3)
    if (trendDiff !== 0) return trendDiff
    const ga = getGrowth(a)
    const gb = getGrowth(b)
    if (ga !== gb) return gb > ga ? 1 : -1
    return a.item_sku.localeCompare(b.item_sku) // stable, deterministic tie-break
  })
}

// Returns recommended lines [{...catalogItem, quantity, line_total}] for a USD budget.
export function recommendRestock(catalog, budget) {
  // Work in integer cents so floating point costs (e.g. 18.99) never overshoot the budget
  let remainingCents = Math.round(budget * 100)
  let partialUsed = false
  const result = []

  for (const item of rankCatalog(catalog)) {
    const shortfall = getShortfall(item)
    const unitCents = Math.round(item.unit_cost * 100)
    if (shortfall <= 0 || unitCents <= 0) continue

    let quantity = 0
    if (shortfall * unitCents <= remainingCents) {
      quantity = shortfall
    } else if (!partialUsed) {
      // Only the first item that does not fully fit may be bought partially;
      // afterwards later items are included only if their full shortfall fits.
      quantity = Math.floor(remainingCents / unitCents)
      partialUsed = true
    }

    if (quantity <= 0) continue
    remainingCents -= quantity * unitCents
    result.push({
      ...item,
      quantity,
      line_total: (quantity * unitCents) / 100
    })
  }
  return result
}

// Fixed upper limit for the budget slider, in USD. It sits above the cost of covering every
// shortfall in full (about $91K today), so the slider can always reach a "buy everything" budget
// even if forecasts or prices grow somewhat. The catalog argument is kept so callers do not change.
export const MAX_BUDGET = 100000

export function getMaxBudget(catalog) { // eslint-disable-line no-unused-vars
  return MAX_BUDGET
}
