export type PersonListRow = {
  id: number
  mdl_id: string
  name: string | null
  native_name: string | null
  nationality: string | null
  image_url: string | null
  collect_status: string
  collected_at: string | null
  works: number
  hidden: number
  sapphic: boolean
  wiki: boolean
}

export type SourceRow = {
  source: string
  display_name: string | null
  external_key: string
  payload: Record<string, unknown>
  selected_at: string
} | null

const CREDIT_ORDER = ['Screenwriter & Director', 'Director', 'Screenwriter']
const CREDIT_LABEL: Record<string, string> = {
  'Screenwriter & Director': '작가·감독',
  Director: '감독',
  Screenwriter: '작가'
}

export function routeId(value: string | string[] | undefined) {
  if (Array.isArray(value)) return value[0] || ''
  return value || ''
}

export function kindLabel(kind: string) {
  if (kind === 'drama') return '드라마'
  if (kind === 'movie') return '영화'
  if (kind === 'tv_show') return 'TV 쇼'
  return kind
}

export function stamp(value: string | null) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

export function worksCount(works: number, hidden: number) {
  return `${works}(${hidden})`
}

export function creditLabels(roles: string[] | null) {
  const values = new Set(roles || [])
  const writer =
    values.has('Screenwriter') || values.has('Screenwriter & Director')
  const director =
    values.has('Director') || values.has('Screenwriter & Director')
  if (writer && director) return '작가·감독'
  return CREDIT_ORDER.filter(role => values.has(role))
    .map(role => CREDIT_LABEL[role] || role)
    .join(', ')
}

export function creditLabel(role: string) {
  return CREDIT_LABEL[role] || role
}

export function statusColor(status: string) {
  if (status === 'collected') return 'success' as const
  if (status === 'failed') return 'error' as const
  if (status === 'registered') return 'warning' as const
  return 'neutral' as const
}

export function httpUrl(value: unknown) {
  return (
    typeof value === 'string' &&
    (value.startsWith('http://') || value.startsWith('https://'))
  )
}

export function errorText(error: unknown) {
  const data = (error as { data?: { error?: string } })?.data
  if (data?.error) return data.error
  if (error instanceof Error && error.message) return error.message
  return '요청이 실패했습니다'
}

export function isGmmtv(source: SourceRow) {
  const company = source?.payload?.company
  if (!company || typeof company !== 'object') return false
  const row = company as { name?: string; slug?: string }
  const name = String(row.name || '')
    .trim()
    .toLowerCase()
  const slug = String(row.slug || '')
    .trim()
    .toLowerCase()
  return name === 'gmmtv' || slug === 'gmmtv'
}

export function storageFetch<T>(path: () => string) {
  const config = useRuntimeConfig()
  return useFetch<T>(
    path,
    import.meta.server ? { baseURL: config.storageUrl } : {}
  )
}
