export const PAGE_SIZE = 20

export type SortState = { id: string; desc: boolean }

export function toggleSort(current: SortState | null, id: string): SortState {
  if (current?.id !== id) return { id, desc: false }
  return { id, desc: !current.desc }
}

export function compareValue(a: unknown, b: unknown, desc: boolean) {
  const empty = (value: unknown) => value == null || value === ''
  if (empty(a) || empty(b)) {
    if (empty(a) && empty(b)) return 0
    return empty(a) ? 1 : -1
  }
  const base =
    typeof a === 'number' && typeof b === 'number'
      ? a - b
      : String(a).localeCompare(String(b), 'ko', {
          numeric: true,
          sensitivity: 'base'
        })
  return desc ? -base : base
}

export function sortRows<T>(
  rows: readonly T[],
  sort: SortState | null,
  value: (row: T, id: string) => unknown
) {
  if (!sort) return [...rows]
  return [...rows].sort((a, b) =>
    compareValue(value(a, sort.id), value(b, sort.id), sort.desc)
  )
}

export function pageRows<T>(
  rows: readonly T[],
  page: number,
  size = PAGE_SIZE
) {
  const start = Math.max(0, page - 1) * size
  return rows.slice(start, start + size)
}

export function scrollParent(el: HTMLElement | null | undefined) {
  let node: HTMLElement | null | undefined = el
  while (node) {
    const y = getComputedStyle(node).overflowY
    if (y === 'auto' || y === 'scroll' || y === 'overlay') return node
    node = node.parentElement
  }
  return el?.parentElement?.parentElement ?? null
}

export function scrollListTop(el: HTMLElement | null | undefined) {
  const active = document.activeElement
  if (active instanceof HTMLElement) active.blur()
  requestAnimationFrame(() => {
    scrollParent(el)?.scrollTo(0, 0)
  })
}

function selfCheck() {
  const rows = [
    { n: 2, t: 'b' },
    { n: null as number | null, t: '' },
    { n: 10, t: 'a' }
  ]
  const byN = sortRows(rows, { id: 'n', desc: false }, row => row.n)
  if (byN.map(row => row.n).join() !== '2,10,') throw new Error('number sort')
  const byNDesc = sortRows(rows, { id: 'n', desc: true }, row => row.n)
  if (byNDesc.map(row => row.n).join() !== '10,2,') throw new Error('desc sort')
  const byT = sortRows(rows, { id: 't', desc: false }, row => row.t)
  if (byT.map(row => row.t).join() !== 'a,b,') throw new Error('text sort')
  if (pageRows([1, 2, 3, 4], 2, 2).join() !== '3,4') throw new Error('page')
  const toggled = toggleSort(toggleSort(null, 'n'), 'n')
  if (!toggled.desc || toggled.id !== 'n') throw new Error('toggle')
}

selfCheck()
