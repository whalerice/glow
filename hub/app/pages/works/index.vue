<script lang="ts">
const workListMemory: {
  q: string
  queer?: string
  status?: string
  sort: { id: string; desc: boolean } | null
  scroll: number
} = { q: '', sort: null, scroll: 0 }
</script>

<script setup lang="ts">
import { h, resolveComponent } from 'vue'
import type { TableColumn } from '@nuxt/ui'
import SortHeader from '~/components/SortHeader.vue'

type CastFace = {
  id: number
  name: string | null
  image_url: string | null
}

type WorkRow = {
  id: number
  title: string
  ko_title: string | null
  kind: string
  year: number | null
  episodes: number | null
  rating: number | null
  image_url: string | null
  tags: string[] | null
  queer: number | null
  queer_name: string | null
  tmdb_id: number | null
  tmdb_status: string | null
  deleted: number
  cast_count: number
  cast: CastFace[]
}

const route = useRoute()
const router = useRouter()
const forward = router.options.history.state.forward
const fromWork =
  typeof forward === 'string' && forward.startsWith('/works/')
const deleted = computed(() => {
  const value = String(route.query.deleted || '0')
  if (value === 'all' || value === '1') return value
  return '0'
})

const q = ref(fromWork ? workListMemory.q : '')
const queerFilter = ref(fromWork ? workListMemory.queer : undefined)
const statusFilter = ref(fromWork ? workListMemory.status : undefined)
const sort = ref<SortState | null>(fromWork ? workListMemory.sort : null)
const pageSizes = [20, 50, 100]
const page = computed(() => {
  const value = Number(route.query.page)
  if (!Number.isInteger(value) || value < 1) return 1
  return value
})
const pageSize = computed(() => {
  const value = Number(route.query.size)
  return pageSizes.includes(value) ? value : 20
})

const { data, error, refresh } = await storageFetch<{
  deleted: string
  page: number
  total: number
  works: WorkRow[]
}>(() => {
  const params = new URLSearchParams({
    deleted: deleted.value,
    page: String(page.value),
    size: String(pageSize.value)
  })
  const needle = q.value.trim()
  if (needle) params.set('q', needle)
  if (queerFilter.value) params.set('queer', queerFilter.value)
  if (statusFilter.value) params.set('status', statusFilter.value)
  if (sort.value) {
    params.set('sort', sort.value.id)
    if (sort.value.desc) params.set('dir', 'desc')
  }
  return `/api/works?${params}`
})

const works = computed(() => data.value?.works || [])
const total = computed(() => data.value?.total ?? 0)

function listQuery(nextPage: number, filter = deleted.value, size = pageSize.value) {
  const query: Record<string, string> = {}
  if (filter !== '0') query.deleted = filter
  if (nextPage > 1) query.page = String(nextPage)
  if (size !== 20) query.size = String(size)
  return query
}

async function onPageSize(value: string) {
  const size = Number(value)
  if (!pageSizes.includes(size) || size === pageSize.value) return
  await navigateTo(
    { path: '/works', query: listQuery(1, deleted.value, size) },
    { replace: true }
  )
}

const list = ref<HTMLElement | null>(null)

function scroller() {
  return list.value?.parentElement?.parentElement
}

function rememberList() {
  workListMemory.q = q.value
  workListMemory.queer = queerFilter.value
  workListMemory.status = statusFilter.value
  workListMemory.sort = sort.value
  workListMemory.scroll = scroller()?.scrollTop ?? 0
}

onBeforeRouteLeave(rememberList)

onMounted(() => {
  if (fromWork) nextTick(() => scroller()?.scrollTo(0, workListMemory.scroll))
  tick()
  tickTmdb()
})

type EpisodeProgress = {
  on: boolean
  done: number
  total: number
  name: string
}

const episodeProgress = ref<EpisodeProgress | null>(null)
let episodeTimer: ReturnType<typeof setTimeout> | undefined

const episodeBar = computed(() => {
  if (!episodeProgress.value?.on || !episodeProgress.value.total) return 0
  return Math.floor((episodeProgress.value.done * 100) / episodeProgress.value.total)
})

async function tick() {
  const body = await $fetch<EpisodeProgress>('/api/works/episodes/progress')
  if (body.on) {
    episodeProgress.value = body
    episodeTimer = setTimeout(tick, 2000)
    return
  }
  episodeProgress.value = null
}

async function collectEpisodes() {
  await $fetch('/api/works/episodes', { method: 'POST', body: {} })
  clearTimeout(episodeTimer)
  await tick()
}

const tmdbProgress = ref<EpisodeProgress | null>(null)
let tmdbTimer: ReturnType<typeof setTimeout> | undefined

const tmdbBar = computed(() => {
  if (!tmdbProgress.value?.on || !tmdbProgress.value.total) return 0
  return Math.floor((tmdbProgress.value.done * 100) / tmdbProgress.value.total)
})

async function tickTmdb() {
  const was = tmdbProgress.value?.on
  const body = await $fetch<EpisodeProgress>('/api/works/collect/progress')
  if (body.on) {
    tmdbProgress.value = body
    tmdbTimer = setTimeout(tickTmdb, 2000)
    return
  }
  tmdbProgress.value = null
  if (was) await refresh()
}

async function recollectTmdb() {
  const ids = picked.value
  if (!ids.length) return
  if (!confirm(`${ids.length}개 작품을 재수집합니다.`)) return
  await $fetch('/api/works/collect', { method: 'POST', body: { ids } })
  rowSelection.value = {}
  clearTimeout(tmdbTimer)
  await tickTmdb()
}

onUnmounted(() => {
  clearTimeout(episodeTimer)
  clearTimeout(tmdbTimer)
})

async function showPage(next: number) {
  await navigateTo(
    { path: '/works', query: listQuery(next) },
    { replace: true }
  )
  await nextTick()
  list.value?.parentElement?.parentElement?.scrollTo(0, 0)
}

function onSort(id: string) {
  sort.value = toggleSort(sort.value, id)
  if (page.value !== 1) showPage(1)
}

watch([q, queerFilter, statusFilter], () => {
  if (page.value !== 1) showPage(1)
})

watch(total, count => {
  if (!data.value) return
  const max = Math.max(1, Math.ceil(count / pageSize.value))
  if (page.value > max) showPage(max)
})

const options = [
  { label: 'All', value: 'all' },
  { label: 'Show', value: '0' },
  { label: 'Hide', value: '1' }
]

const queerOptions = [
  { label: 'BL', value: 'BL' },
  { label: 'GL', value: 'GL' },
  { label: 'LGBTQ', value: 'LGBTQ' },
  { label: '없음', value: 'none' }
]

const statusOptions = [
  { label: 'Returning Series', value: 'Returning Series' },
  { label: 'Planned', value: 'Planned' },
  { label: 'In Production', value: 'In Production' },
  { label: 'Post Production', value: 'Post Production' },
  { label: 'Pilot', value: 'Pilot' },
  { label: 'Ended', value: 'Ended' },
  { label: 'Canceled', value: 'Canceled' },
  { label: 'Released', value: 'Released' },
  { label: 'Rumored', value: 'Rumored' },
  { label: '없음', value: 'none' }
]

function fixed(width: string) {
  return {
    class: { td: 'overflow-hidden' },
    style: { th: { width }, td: { width } }
  }
}

const rowSelection = ref<Record<string, boolean>>({})
const picked = computed(() =>
  Object.entries(rowSelection.value)
    .filter(([, on]) => on)
    .map(([id]) => Number(id))
)

watch([q, queerFilter, statusFilter, deleted], () => {
  rowSelection.value = {}
})

function mark(on: boolean | 'indeterminate') {
  return on === true
}

const columns = computed<TableColumn<WorkRow>[]>(() => {
  const col = (label: string, id: string, width: string) => ({
    accessorKey: id,
    header: () => h(SortHeader, { label, id, active: sort.value, onSort }),
    meta: fixed(width)
  })
  return [
    {
      id: 'select',
      header: ({ table }) =>
        h(resolveComponent('UCheckbox'), {
          modelValue: table.getIsSomePageRowsSelected()
            ? 'indeterminate'
            : table.getIsAllPageRowsSelected(),
          'aria-label': '이 페이지 선택',
          'onUpdate:modelValue': (value: boolean | 'indeterminate') =>
            table.toggleAllPageRowsSelected(mark(value))
        }),
      cell: ({ row }) =>
        h(resolveComponent('UCheckbox'), {
          modelValue: row.getIsSelected(),
          'aria-label': '선택',
          'onUpdate:modelValue': (value: boolean | 'indeterminate') =>
            row.toggleSelected(mark(value))
        }),
      meta: fixed('40px')
    },
    {
      accessorKey: 'image_url',
      header: '',
      meta: {
        style: {
          th: { width: '80px', paddingInline: '0' },
          td: { width: '80px', paddingInline: '0' }
        }
      }
    },
    {
      accessorKey: 'title',
      header: () =>
        h(SortHeader, {
          label: '제목',
          id: 'title',
          active: sort.value,
          onSort
        }),
      meta: { class: { td: 'whitespace-normal' } }
    },
    col('GL/BL', 'queer', '120px'),
    col('종류', 'kind', '88px'),
    col('연도', 'year', '72px'),
    col('에피소드', 'episodes', '96px'),
    col('평점', 'rating', '72px'),
    col('TMDB', 'tmdb_id', '80px'),
    col('상태', 'tmdb_status', '148px'),
    col('출연', 'cast_count', '240px')
  ]
})

async function onFilter(value: string) {
  await navigateTo({ path: '/works', query: listQuery(1, value) })
}

async function bulkException() {
  const ids = picked.value
  if (!ids.length) return
  if (!confirm(`${ids.length}개 작품을 예외 처리합니다.`)) return
  await $fetch('/api/works/exception', {
    method: 'POST',
    body: { ids, deleted: 1 }
  })
  rowSelection.value = {}
  await refresh()
}

async function bulkAdd() {
  const ids = picked.value
  if (!ids.length) return
  if (!confirm(`${ids.length}개 작품을 추가합니다.`)) return
  await $fetch('/api/works/exception', {
    method: 'POST',
    body: { ids, deleted: 0 }
  })
  rowSelection.value = {}
  await refresh()
}

async function bulkDelete() {
  const ids = picked.value
  if (!ids.length) return
  if (!confirm(`${ids.length}개 작품을 삭제합니다. 배우와 회사는 남습니다.`)) return
  await $fetch('/api/works/delete', { method: 'POST', body: { ids } })
  rowSelection.value = {}
  await refresh()
}

const open = ref(false)
const mdlId = ref('')
const message = ref('')
const existing = ref<number | null>(null)
const pending = ref(false)

function showRegister() {
  message.value = ''
  existing.value = null
  open.value = true
}

async function submit() {
  message.value = ''
  existing.value = null
  pending.value = true
  try {
    const result = await $fetch<{ work_id: number; exists: boolean }>('/api/works', {
      method: 'POST',
      body: { mdl_id: mdlId.value }
    })
    if (result.exists) {
      existing.value = result.work_id
      return
    }
    open.value = false
    await navigateTo(`/works/${result.work_id}`)
  } catch (error) {
    message.value = errorText(error)
  } finally {
    pending.value = false
  }
}
</script>

<template>
  <section ref="list">
    <UAlert
      v-if="error"
      color="error"
      variant="subtle"
      :title="errorText(error)"
      class="mb-4"
    />
    <div class="mb-4 flex flex-wrap items-center justify-between gap-2">
      <div class="flex items-center gap-2">
        <USelect
          v-model="queerFilter"
          :items="queerOptions"
          placeholder="전체"
          class="w-24"
        >
          <template #trailing>
            <UButton
              v-if="queerFilter"
              color="neutral"
              variant="link"
              size="xs"
              icon="i-lucide-x"
              aria-label="전체"
              class="p-0"
              @pointerdown.stop.prevent="queerFilter = undefined"
            />
            <UIcon name="i-lucide-chevron-down" class="size-5 shrink-0 text-dimmed" />
          </template>
        </USelect>
        <USelect
          :model-value="deleted"
          :items="options"
          class="w-28"
          @update:model-value="onFilter(String($event))"
        />
        <USelect
          v-model="statusFilter"
          :items="statusOptions"
          placeholder="상태"
          class="w-44"
        >
          <template #trailing>
            <UButton
              v-if="statusFilter"
              color="neutral"
              variant="link"
              size="xs"
              icon="i-lucide-x"
              aria-label="상태 전체"
              class="p-0"
              @pointerdown.stop.prevent="statusFilter = undefined"
            />
            <UIcon name="i-lucide-chevron-down" class="size-5 shrink-0 text-dimmed" />
          </template>
        </USelect>
        <UInput v-model="q" placeholder="제목" class="w-48" />
        <span class="text-sm text-muted tabular-nums">{{ total }}</span>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <div v-if="episodeProgress?.on" class="min-w-40">
          <p class="text-xs text-muted">
            에피소드 {{ episodeProgress.done }}/{{ episodeProgress.total }} ·
            {{ episodeProgress.name }}
          </p>
          <div class="mt-1 h-1.5 w-40 overflow-hidden rounded bg-accented">
            <div class="h-full bg-primary" :style="{ width: `${episodeBar}%` }" />
          </div>
        </div>
        <div v-if="tmdbProgress?.on" class="min-w-40">
          <p class="text-xs text-muted">
            수집 {{ tmdbProgress.done }}/{{ tmdbProgress.total }} ·
            {{ tmdbProgress.name }}
          </p>
          <div class="mt-1 h-1.5 w-40 overflow-hidden rounded bg-accented">
            <div class="h-full bg-primary" :style="{ width: `${tmdbBar}%` }" />
          </div>
        </div>
        <span v-if="picked.length" class="text-sm text-muted tabular-nums">
          선택 {{ picked.length }}
        </span>
        <UButton
          color="neutral"
          variant="outline"
          :disabled="!picked.length || tmdbProgress?.on"
          @click="recollectTmdb"
        >
          재수집
        </UButton>
        <UButton
          color="warning"
          variant="outline"
          :disabled="!picked.length"
          @click="bulkException"
        >
          일괄예외
        </UButton>
        <UButton :disabled="!picked.length" @click="bulkAdd"> 일괄추가 </UButton>
        <UButton
          color="error"
          variant="outline"
          :disabled="!picked.length"
          @click="bulkDelete"
        >
          일괄삭제
        </UButton>
        <UButton
          color="neutral"
          variant="outline"
          :loading="episodeProgress?.on"
          @click="collectEpisodes"
        >
          에피소드 수집
        </UButton>
        <UButton @click="showRegister"> 작품 등록 </UButton>
      </div>
    </div>
    <p v-if="!works.length" class="text-sm text-muted">
      {{
        q.trim() || queerFilter || statusFilter
          ? '검색 결과가 없습니다.'
          : '수집된 작품이 없습니다.'
      }}
    </p>
    <UTable
      v-else
      v-model:row-selection="rowSelection"
      :data="works"
      :columns="columns"
      :get-row-id="(row: WorkRow) => String(row.id)"
      :ui="{ base: 'table-fixed' }"
    >
      <template #image_url-cell="{ row }">
        <span
          v-if="row.original.image_url"
          class="relative block aspect-3/4 w-full overflow-hidden rounded"
        >
          <img
            :src="row.original.image_url"
            alt=""
            class="absolute inset-0 size-full object-cover"
          />
        </span>
      </template>
      <template #title-cell="{ row }">
        <NuxtLink :to="`/works/${row.original.id}`" class="font-medium">
          {{ row.original.title }}
        </NuxtLink>
        <p v-if="row.original.ko_title" class="text-sm text-muted">
          {{ row.original.ko_title }}
        </p>
      </template>
      <template #queer-cell="{ row }">
        <UBadge
          v-if="row.original.queer_name"
          :color="row.original.queer_name === 'BL' ? 'secondary' : 'primary'"
          :class="row.original.queer_name === 'GL' ? 'gl-badge' : undefined"
        >
          {{ row.original.queer_name }}
        </UBadge>
      </template>
      <template #kind-cell="{ row }">
        {{ kindLabel(row.original.kind) }}
      </template>
      <template #year-cell="{ row }">
        {{ row.original.year ?? '' }}
      </template>
      <template #episodes-cell="{ row }">
        {{ row.original.episodes ?? '' }}
      </template>
      <template #rating-cell="{ row }">
        {{ row.original.rating ?? '' }}
      </template>
      <template #tmdb_status-cell="{ row }">
        {{ row.original.tmdb_status || '' }}
      </template>
      <template #tmdb_id-cell="{ row }">
        <UBadge
          v-if="row.original.tmdb_id != null"
          color="neutral"
          variant="subtle"
        >
          있음
        </UBadge>
      </template>
      <template #cast_count-cell="{ row }">
        <div class="flex flex-wrap gap-1">
          <NuxtLink
            v-for="person in row.original.cast"
            :key="person.id"
            :to="`/people/${person.id}`"
            :title="person.name || ''"
          >
            <img
              v-if="person.image_url"
              :src="person.image_url"
              alt=""
              class="h-12 w-9 rounded object-cover"
            />
          </NuxtLink>
        </div>
      </template>
    </UTable>
    <UModal
      v-model:open="open"
      title="작품 등록"
      description="MyDramaList 숫자 id"
    >
      <template #body>
        <UAlert
          v-if="message"
          color="error"
          variant="subtle"
          :title="message"
          class="mb-4"
        />
        <UAlert
          v-else-if="existing"
          color="warning"
          variant="subtle"
          title="이미 등록된 작품입니다"
          class="mb-4"
          :actions="[{ label: '보기', to: `/works/${existing}` }]"
        />
        <form class="flex gap-2" @submit.prevent="submit">
          <UInput
            v-model="mdlId"
            name="mdl_id"
            class="w-full"
            placeholder="18452"
          />
          <UButton type="submit" :loading="pending"> 저장 </UButton>
        </form>
      </template>
    </UModal>
    <div class="mt-4 flex flex-wrap items-center justify-end gap-2">
      <USelect
        :model-value="String(pageSize)"
        :items="pageSizes.map(size => ({ label: String(size), value: String(size) }))"
        class="w-20"
        @update:model-value="onPageSize(String($event))"
      />
      <UPagination
        v-if="total > pageSize"
        :page="page"
        :items-per-page="pageSize"
        :total="total"
        show-edges
        @update:page="showPage"
      />
    </div>
  </section>
</template>
