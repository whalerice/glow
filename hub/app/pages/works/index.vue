<script lang="ts">
const workListMemory: {
  q: string
  queer?: string
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
  deleted: number
  cast_count: number
  cast: CastFace[]
}

const route = useRoute()
const deleted = computed(() => {
  const value = String(route.query.deleted || '0')
  if (value === 'all' || value === '1') return value
  return '0'
})

const { data, error, refresh } = await storageFetch<{
  deleted: string
  works: WorkRow[]
}>(() => `/api/works?deleted=${deleted.value}`)

const works = computed(() => data.value?.works || [])
const router = useRouter()
const forward = router.options.history.state.forward
const fromWork =
  typeof forward === 'string' && forward.startsWith('/works/')
const q = ref(fromWork ? workListMemory.q : '')
const queerFilter = ref(fromWork ? workListMemory.queer : undefined)
const sort = ref<SortState | null>(fromWork ? workListMemory.sort : null)
const page = computed(() => {
  const value = Number(route.query.page)
  if (!Number.isInteger(value) || value < 1) return 1
  return value
})

function listQuery(nextPage: number, filter = deleted.value) {
  const query: Record<string, string> = {}
  if (filter !== '0') query.deleted = filter
  if (nextPage > 1) query.page = String(nextPage)
  return query
}

const list = ref<HTMLElement | null>(null)

function scroller() {
  return list.value?.parentElement?.parentElement
}

function rememberList() {
  workListMemory.q = q.value
  workListMemory.queer = queerFilter.value
  workListMemory.sort = sort.value
  workListMemory.scroll = scroller()?.scrollTop ?? 0
}

onBeforeRouteLeave(rememberList)

onMounted(() => {
  if (fromWork) nextTick(() => scroller()?.scrollTo(0, workListMemory.scroll))
  tick()
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

onUnmounted(() => clearTimeout(episodeTimer))

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

function workValue(row: WorkRow, id: string) {
  if (id === 'title') return row.title
  if (id === 'queer') return row.queer_name || ''
  if (id === 'kind') return kindLabel(row.kind)
  if (id === 'year') return row.year
  if (id === 'episodes') return row.episodes
  if (id === 'rating') return row.rating
  if (id === 'tmdb_id') return row.tmdb_id == null ? '' : 1
  return row.cast_count
}

const filtered = computed(() => {
  const needle = q.value.trim().toLowerCase()
  const kind = queerFilter.value
  return works.value.filter(row => {
    if (needle && !row.title.toLowerCase().includes(needle)) return false
    if (!kind) return true
    if (kind === 'none') return row.queer == null
    return row.queer_name === kind
  })
})
const sorted = computed(() => sortRows(filtered.value, sort.value, workValue))
const visible = computed(() => pageRows(sorted.value, page.value))

watch([q, queerFilter], () => {
  if (page.value !== 1) showPage(1)
})

watch(
  () => sorted.value.length,
  count => {
    if (!data.value) return
    const max = Math.max(1, Math.ceil(count / PAGE_SIZE))
    if (page.value > max) showPage(max)
  },
  { immediate: true }
)

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

watch([q, queerFilter, deleted], () => {
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
    col('출연', 'cast_count', '240px'),
    { id: 'exception', header: '', meta: fixed('168px') }
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

async function bulkDelete() {
  const ids = picked.value
  if (!ids.length) return
  if (!confirm(`${ids.length}개 작품을 삭제합니다. 배우와 회사는 남습니다.`)) return
  await $fetch('/api/works/delete', { method: 'POST', body: { ids } })
  rowSelection.value = {}
  await refresh()
}

async function removeWork(id: number) {
  if (!confirm('이 작품을 삭제합니다. 배우와 회사는 남습니다.')) return
  await $fetch(`/api/works/${id}/delete`, { method: 'POST', body: {} })
  await refresh()
}

async function setDeleted(id: number, deleted: 0 | 1) {
  await $fetch(`/api/works/${id}/exception`, {
    method: 'POST',
    body: { deleted }
  })
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
    <div class="mb-4 flex items-center justify-between gap-2">
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
        <UInput v-model="q" placeholder="제목" class="w-48" />
      </div>
      <div class="flex items-center gap-2">
        <div v-if="episodeProgress?.on" class="min-w-40">
          <p class="text-xs text-muted">
            에피소드 {{ episodeProgress.done }}/{{ episodeProgress.total }} ·
            {{ episodeProgress.name }}
          </p>
          <div class="mt-1 h-1.5 w-40 overflow-hidden rounded bg-accented">
            <div class="h-full bg-primary" :style="{ width: `${episodeBar}%` }" />
          </div>
        </div>
        <UButton
          color="warning"
          variant="outline"
          :disabled="!picked.length"
          @click="bulkException"
        >
          일괄예외
        </UButton>
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
    <p v-if="!sorted.length" class="text-sm text-muted">
      {{
        q.trim() || queerFilter ? '검색 결과가 없습니다.' : '수집된 작품이 없습니다.'
      }}
    </p>
    <UTable
      v-else
      v-model:row-selection="rowSelection"
      :data="visible"
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
      <template #exception-cell="{ row }">
        <div class="flex gap-1">
          <UButton
            v-if="row.original.deleted === 1"
            @click="setDeleted(row.original.id, 0)"
          >
            추가
          </UButton>
          <UButton
            v-else
            color="warning"
            @click="setDeleted(row.original.id, 1)"
          >
            예외
          </UButton>
          <UButton
            color="error"
            variant="outline"
            @click="removeWork(row.original.id)"
          >
            삭제
          </UButton>
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
    <div v-if="sorted.length > PAGE_SIZE" class="mt-4 flex justify-end">
      <UPagination
        :page="page"
        :items-per-page="PAGE_SIZE"
        :total="sorted.length"
        show-edges
        @update:page="showPage"
      />
    </div>
  </section>
</template>
