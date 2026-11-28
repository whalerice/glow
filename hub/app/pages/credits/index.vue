<script lang="ts">
import type { SortState } from '~/utils/table'

const creditListMemory: {
  q: string
  sort: SortState | null
  scroll: number
} = { q: '', sort: null, scroll: 0 }
</script>

<script setup lang="ts">
import { h } from 'vue'
import type { TableColumn } from '@nuxt/ui'
import SortHeader from '~/components/SortHeader.vue'

type CreditRow = {
  id: number
  name: string | null
  native_name: string | null
  nationality: string | null
  image_url: string | null
  roles: string[]
  works: number
}

const route = useRoute()
const router = useRouter()
const forward = router.options.history.state.forward
const fromCredit =
  typeof forward === 'string' && forward.startsWith('/credits/')
const q = ref(fromCredit ? creditListMemory.q : '')
const sort = ref<SortState | null>(
  fromCredit ? creditListMemory.sort : { id: 'works', desc: true }
)
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

const { data, error } = await storageFetch<{
  page: number
  total: number
  credits: CreditRow[]
}>(() => {
  const params = new URLSearchParams({
    page: String(page.value),
    size: String(pageSize.value)
  })
  const needle = q.value.trim()
  if (needle) params.set('q', needle)
  if (sort.value) {
    params.set('sort', sort.value.id)
    if (sort.value.desc) params.set('dir', 'desc')
  }
  return `/api/credits?${params}`
})

const credits = computed(() => data.value?.credits || [])
const total = computed(() => data.value?.total ?? 0)
const list = ref<HTMLElement | null>(null)

function scroller() {
  return scrollParent(list.value)
}

function rememberList() {
  creditListMemory.q = q.value
  creditListMemory.sort = sort.value
  creditListMemory.scroll = scroller()?.scrollTop ?? 0
}

onBeforeRouteLeave(rememberList)

onMounted(() => {
  if (!fromCredit) return
  nextTick(() => {
    requestAnimationFrame(() => {
      scroller()?.scrollTo(0, creditListMemory.scroll)
    })
  })
})

function listQuery(nextPage: number, size = pageSize.value) {
  const query: Record<string, string> = {}
  if (nextPage > 1) query.page = String(nextPage)
  if (size !== 20) query.size = String(size)
  return query
}

async function onPageSize(value: string) {
  const size = Number(value)
  if (!pageSizes.includes(size) || size === pageSize.value) return
  await navigateTo(
    { path: '/credits', query: listQuery(1, size) },
    { replace: true }
  )
  await nextTick()
  scrollListTop(list.value)
}

async function showPage(next: number) {
  await navigateTo(
    { path: '/credits', query: listQuery(next) },
    { replace: true }
  )
  await nextTick()
  scrollListTop(list.value)
}

function onSort(id: string) {
  sort.value = toggleSort(sort.value, id)
  if (page.value !== 1) showPage(1)
}

watch(q, () => {
  if (page.value !== 1) showPage(1)
})

watch(total, count => {
  if (!data.value) return
  const max = Math.max(1, Math.ceil(count / pageSize.value))
  if (page.value > max) showPage(max)
})

const columns = computed<TableColumn<CreditRow>[]>(() => [
  {
    accessorKey: 'image_url',
    header: '',
    meta: {
      style: {
        th: { width: '56px', paddingInline: '0' },
        td: { width: '56px', paddingInline: '0' }
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
      })
  },
  { accessorKey: 'roles', header: '역할' },
  {
    accessorKey: 'nationality',
    header: () =>
      h(SortHeader, {
        label: '국적',
        id: 'nationality',
        active: sort.value,
        onSort
      })
  },
  {
    accessorKey: 'works',
    header: () =>
      h(SortHeader, {
        label: '작품',
        id: 'works',
        active: sort.value,
        onSort
      }),
    meta: {
      style: { th: { width: '72px' }, td: { width: '72px' } }
    }
  }
])
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
    <div class="mb-4 flex items-center gap-3">
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
    <p v-if="!credits.length" class="text-sm text-muted">
      {{ q.trim() ? '검색 결과가 없습니다.' : '수집된 작가·감독이 없습니다.' }}
    </p>
    <UTable v-else :data="credits" :columns="columns">
      <template #image_url-cell="{ row }">
        <img
          v-if="row.original.image_url"
          :src="row.original.image_url"
          alt=""
          class="h-12 w-9 rounded object-cover"
        />
      </template>
      <template #name-cell="{ row }">
        <NuxtLink :to="`/credits/${row.original.id}`" class="font-medium">
          {{ row.original.name || '이름 없음' }}
        </NuxtLink>
        <span
          v-if="row.original.native_name"
          class="block text-xs text-muted"
          >{{ row.original.native_name }}</span
        >
      </template>
      <template #roles-cell="{ row }">
        {{ creditLabels(row.original.roles) }}
      </template>
      <template #nationality-cell="{ row }">
        {{ row.original.nationality || '' }}
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
  </section>
</template>
