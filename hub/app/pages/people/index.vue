<script lang="ts">
import type { SortState } from '~/utils/table'

const peopleListMemory: {
  q: string
  sort: SortState | null
  scroll: number
} = { q: '', sort: null, scroll: 0 }
</script>

<script setup lang="ts">
import { h, resolveComponent } from 'vue'
import type { TableColumn } from '@nuxt/ui'
import type { PersonListRow } from '~/utils/glow'
import SortHeader from '~/components/SortHeader.vue'

type Progress = {
  on: boolean
  done: number
  total: number
  name: string
  rows: PersonListRow[]
  created: { id: number; title: string }[]
}

const route = useRoute()
const router = useRouter()
const forward = router.options.history.state.forward
const fromPerson =
  typeof forward === 'string' && forward.startsWith('/people/')
const deleted = computed(() => {
  const value = route.query.deleted
  if (value === undefined || value === null || value === '') return '0'
  const text = String(value)
  if (text === 'all' || text === '0' || text === '1' || text === '2') return text
  return '0'
})
const q = ref(fromPerson ? peopleListMemory.q : '')
const sort = ref<SortState | null>(fromPerson ? peopleListMemory.sort : null)
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
  people: PersonListRow[]
}>(() => {
  const params = new URLSearchParams({
    page: String(page.value),
    size: String(pageSize.value)
  })
  if (deleted.value !== '0') params.set('deleted', deleted.value)
  const needle = q.value.trim()
  if (needle) params.set('q', needle)
  if (sort.value) {
    params.set('sort', sort.value.id)
    if (sort.value.desc) params.set('dir', 'desc')
  }
  return `/api/people?${params}`
})
const progress = ref<Progress | null>(null)
const createdOpen = ref(false)
const createdWorks = ref<{ id: number; title: string }[]>([])
const open = ref(false)
const mdlId = ref('')
const message = ref('')
const existing = ref<{
  person_id: number
  deleted: number
  name: string | null
} | null>(null)
const pending = ref(false)
let timer: ReturnType<typeof setTimeout> | undefined

const people = computed(() => data.value?.people || [])
const total = computed(() => data.value?.total ?? 0)
const rowSelection = ref<Record<string, boolean>>({})
const picked = computed(() =>
  Object.entries(rowSelection.value)
    .filter(([, on]) => on)
    .map(([id]) => Number(id))
)
const list = ref<HTMLElement | null>(null)
const options = [
  { label: '전체', value: 'all' },
  { label: '노출', value: '0' },
  { label: '숨김', value: '1' },
  { label: '삭제', value: '2' }
]

function scroller() {
  return scrollParent(list.value)
}

function rememberList() {
  peopleListMemory.q = q.value
  peopleListMemory.sort = sort.value
  peopleListMemory.scroll = scroller()?.scrollTop ?? 0
}

onBeforeRouteLeave(rememberList)

onMounted(() => {
  if (!fromPerson) return
  nextTick(() => {
    requestAnimationFrame(() => {
      scroller()?.scrollTo(0, peopleListMemory.scroll)
    })
  })
})

function listQuery(nextPage: number, filter = deleted.value, size = pageSize.value) {
  const query: Record<string, string> = {}
  if (filter === 'all' || filter === '1' || filter === '2') query.deleted = filter
  if (nextPage > 1) query.page = String(nextPage)
  if (size !== 20) query.size = String(size)
  return query
}

async function onPageSize(value: string) {
  const size = Number(value)
  if (!pageSizes.includes(size) || size === pageSize.value) return
  await navigateTo(
    { path: '/people', query: listQuery(1, deleted.value, size) },
    { replace: true }
  )
  await nextTick()
  scrollListTop(list.value)
}

async function showPage(next: number) {
  await navigateTo(
    { path: '/people', query: listQuery(next) },
    { replace: true }
  )
  await nextTick()
  scrollListTop(list.value)
}

async function onFilter(value: string) {
  await navigateTo({ path: '/people', query: listQuery(1, value) })
}

function onSort(id: string) {
  sort.value = toggleSort(sort.value, id)
  if (page.value !== 1) showPage(1)
}

function mark(on: boolean | 'indeterminate') {
  return on === true
}

watch([q, deleted], () => {
  rowSelection.value = {}
  if (page.value !== 1) showPage(1)
})

watch(total, count => {
  if (!data.value) return
  const max = Math.max(1, Math.ceil(count / pageSize.value))
  if (page.value > max) showPage(max)
})

async function bulkException() {
  const ids = picked.value
  if (!ids.length) return
  if (!confirm(`${ids.length}명 배우를 예외 처리합니다.`)) return
  await $fetch('/api/people/exception', {
    method: 'POST',
    body: { ids, deleted: 1 }
  })
  rowSelection.value = {}
  await refresh()
}

async function bulkAdd() {
  const ids = picked.value
  if (!ids.length) return
  if (!confirm(`${ids.length}명 배우를 추가합니다.`)) return
  await $fetch('/api/people/exception', {
    method: 'POST',
    body: { ids, deleted: 0 }
  })
  rowSelection.value = {}
  await refresh()
}

async function bulkDelete() {
  const ids = picked.value
  if (!ids.length) return
  if (!confirm(`${ids.length}명 배우를 삭제로 표시합니다. 행은 남습니다.`)) return
  await $fetch('/api/people/exception', {
    method: 'POST',
    body: { ids, deleted: 2 }
  })
  rowSelection.value = {}
  await refresh()
}

const bar = computed(() => {
  if (!progress.value?.on) return 0
  if (!progress.value.total) return 0
  return Math.floor((progress.value.done * 100) / progress.value.total)
})

function fixed(width: string) {
  return {
    class: { td: 'overflow-hidden' },
    style: { th: { width }, td: { width } }
  }
}

function flag(value: boolean) {
  if (!value) return ''
  return h(
    resolveComponent('UBadge'),
    { color: 'neutral', variant: 'subtle' },
    () => '있음'
  )
}

const columns = computed<TableColumn<PersonListRow>[]>(() => {
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
      accessorKey: 'name',
      header: () =>
        h(SortHeader, {
          label: '이름',
          id: 'name',
          active: sort.value,
          onSort
        }),
      meta: { class: { td: 'whitespace-normal' } }
    },
    col('MDL id', 'mdl_id', '96px'),
    col('상태', 'collect_status', '112px'),
    {
      id: 'sapphic',
      accessorKey: 'sapphic',
      header: () =>
        h(SortHeader, {
          label: 'Sapphic',
          id: 'sapphic',
          active: sort.value,
          onSort
        }),
      cell: ({ row }) => flag(row.original.sapphic),
      meta: fixed('88px')
    },
    {
      id: 'wiki',
      accessorKey: 'wiki',
      header: () =>
        h(SortHeader, {
          label: '위키',
          id: 'wiki',
          active: sort.value,
          onSort
        }),
      cell: ({ row }) => flag(row.original.wiki),
      meta: fixed('72px')
    },
    col('출연', 'works', '80px'),
    col('수집 시각', 'collected_at', '168px')
  ]
})

function applyRows(rows: PersonListRow[]) {
  const current = data.value?.people
  if (!current) return
  for (const row of rows) {
    const found = current.find(item => item.id === row.id)
    if (found) Object.assign(found, row)
  }
}

async function tick() {
  const body = await $fetch<Progress>('/api/people/works/progress')
  if (body.on) {
    progress.value = body
    applyRows(body.rows)
    timer = setTimeout(tick, 2000)
    return
  }
  createdWorks.value = body.created || []
  createdOpen.value = true
  progress.value = null
  await refresh()
}

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
    const result = await $fetch<{
      exists?: boolean
      person_id: number
      deleted?: number
      name?: string | null
    }>('/api/people', {
      method: 'POST',
      body: { mdl_id: mdlId.value }
    })
    if (result.exists) {
      existing.value = {
        person_id: result.person_id,
        deleted: result.deleted ?? 0,
        name: result.name ?? null
      }
      return
    }
    open.value = false
    await navigateTo(`/people/${result.person_id}`)
  } catch (error) {
    message.value = errorText(error)
  } finally {
    pending.value = false
  }
}

async function restoreAndOpen() {
  if (!existing.value) return
  pending.value = true
  message.value = ''
  try {
    await $fetch(`/api/people/${existing.value.person_id}/exception`, {
      method: 'POST',
      body: { deleted: 0 }
    })
    open.value = false
    await navigateTo(`/people/${existing.value.person_id}`)
  } catch (error) {
    message.value = errorText(error)
  } finally {
    pending.value = false
  }
}

async function refreshWorks() {
  const ids = picked.value
  if (!ids.length) return
  if (!confirm(`${ids.length}명 작품을 다시 가져옵니다.`)) return
  message.value = ''
  try {
    await $fetch('/api/people/works', { method: 'POST', body: { ids } })
    rowSelection.value = {}
    clearTimeout(timer)
    await tick()
  } catch (error) {
    message.value = errorText(error)
  }
}

onUnmounted(() => clearTimeout(timer))
</script>

<template>
  <section ref="list">
    <UAlert
      v-if="error || (message && !open)"
      color="error"
      variant="subtle"
      :title="message || errorText(error)"
      class="mb-4"
    />
    <div class="mb-4 flex items-center justify-between gap-3">
      <div class="flex items-center gap-3">
        <USelect
          :model-value="deleted"
          :items="options"
          class="w-28"
          @update:model-value="onFilter(String($event))"
        />
        <UInput v-model="q" placeholder="이름" class="w-48">
          <template #trailing>
            <UButton
              v-if="q"
              color="neutral"
              variant="link"
              size="xs"
              icon="i-lucide-x"
              aria-label="검색 지우기"
              class="p-0"
              @click="q = ''"
            />
          </template>
        </UInput>
        <span class="text-sm text-muted tabular-nums">{{ total }}</span>
      </div>
      <div class="flex items-center gap-2">
        <div v-if="progress?.on" class="min-w-40">
          <p class="text-xs text-muted">
            작품 {{ progress.done }}/{{ progress.total }} · {{ progress.name }}
          </p>
          <div class="mt-1 h-1.5 w-40 overflow-hidden rounded bg-accented">
            <div class="h-full bg-primary" :style="{ width: `${bar}%` }" />
          </div>
        </div>
        <span v-if="picked.length" class="text-sm text-muted tabular-nums">
          선택 {{ picked.length }}
        </span>
        <UButton
          color="neutral"
          variant="outline"
          :disabled="!picked.length || progress?.on"
          @click="refreshWorks"
        >
          작품 가져오기
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
        <UButton @click="showRegister"> 배우 등록 </UButton>
      </div>
    </div>
    <p v-if="!people.length" class="text-sm text-muted">
      {{ q.trim() ? '검색 결과가 없습니다.' : '등록된 배우가 없습니다.' }}
    </p>
    <UTable
      v-else
      v-model:row-selection="rowSelection"
      :data="people"
      :columns="columns"
      :get-row-id="(row: PersonListRow) => String(row.id)"
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
      <template #name-cell="{ row }">
        <NuxtLink
          v-if="row.original.deleted === 0"
          :to="`/people/${row.original.id}`"
          class="font-medium"
        >
          {{ row.original.name || row.original.native_name || '이름 없음' }}
        </NuxtLink>
        <span v-else class="font-medium">
          {{ row.original.name || row.original.native_name || '이름 없음' }}
        </span>
        <span
          v-if="
            row.original.native_name &&
            row.original.native_name !==
              (row.original.name || row.original.native_name)
          "
          class="block text-xs text-muted"
          >{{ row.original.native_name }}</span
        >
        <div
          v-if="row.original.ship_partners?.length"
          class="mt-1 flex flex-wrap items-center gap-1"
        >
          <NuxtLink
            v-for="mate in row.original.ship_partners"
            :key="mate.id"
            :to="`/people/${mate.id}`"
            :title="mate.name || '이름 없음'"
            class="block"
          >
            <img
              v-if="mate.image_url"
              :src="mate.image_url"
              alt=""
              class="size-8 rounded-full object-cover"
            />
            <span
              v-else
              class="flex size-8 items-center justify-center rounded-full bg-elevated text-xs text-muted"
              >?</span
            >
          </NuxtLink>
        </div>
      </template>
      <template #collect_status-cell="{ row }">
        <UBadge
          :color="statusColor(row.original.collect_status)"
          variant="subtle"
        >
          {{ row.original.collect_status }}
        </UBadge>
      </template>
      <template #works-cell="{ row }">
        {{ row.original.works
        }}<span class="text-muted">({{ row.original.hidden }})</span>
      </template>
      <template #collected_at-cell="{ row }">
        <span class="text-muted">{{ stamp(row.original.collected_at) }}</span>
      </template>
    </UTable>
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
    <UModal
      v-model:open="createdOpen"
      title="새로 등록된 작품"
      :description="
        createdWorks.length
          ? `${createdWorks.length}개`
          : '새로 등록된 작품이 없습니다.'
      "
    >
      <template #body>
        <ul v-if="createdWorks.length" class="space-y-1 text-sm">
          <li v-for="work in createdWorks" :key="work.id">
            <NuxtLink
              class="underline"
              :to="`/works/${work.id}`"
              @click="createdOpen = false"
            >
              {{ work.title || '제목 없음' }}
            </NuxtLink>
          </li>
        </ul>
      </template>
    </UModal>
    <UModal
      v-model:open="open"
      title="배우 등록"
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
          v-else-if="existing && existing.deleted === 0"
          color="warning"
          variant="subtle"
          title="이미 등록된 배우입니다"
          :description="existing.name || undefined"
          class="mb-4"
          :actions="[{ label: '보기', to: `/people/${existing.person_id}` }]"
        />
        <UAlert
          v-else-if="existing"
          color="warning"
          variant="subtle"
          :title="existing.deleted === 1 ? '숨김 처리된 배우입니다' : '삭제된 배우입니다'"
          :description="existing.name || undefined"
          class="mb-4"
          :actions="[
            {
              label: '노출로 되돌리고 열기',
              loading: pending,
              onClick: restoreAndOpen
            }
          ]"
        />
        <form class="flex gap-2" @submit.prevent="submit">
          <UInput
            v-model="mdlId"
            name="mdl_id"
            class="w-full"
            placeholder="70935"
          />
          <UButton type="submit" :loading="pending"> 저장 </UButton>
        </form>
      </template>
    </UModal>
  </section>
</template>
