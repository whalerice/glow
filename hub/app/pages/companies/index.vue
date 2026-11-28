<script lang="ts">
import type { SortState } from '~/utils/table'

const companyListMemory: {
  q: string
  sort: SortState | null
  scroll: number
} = { q: '', sort: null, scroll: 0 }
</script>

<script setup lang="ts">
import { h } from 'vue'
import type { TableColumn } from '@nuxt/ui'
import SortHeader from '~/components/SortHeader.vue'

type CompanyRow = {
  id: number
  name: string
  logo_url: string | null
  members: number
  works: number
  types: string
}

const route = useRoute()
const router = useRouter()
const forward = router.options.history.state.forward
const fromCompany =
  typeof forward === 'string' && forward.startsWith('/companies/')
const q = ref(fromCompany ? companyListMemory.q : '')
const sort = ref<SortState | null>(
  fromCompany ? companyListMemory.sort : { id: 'members', desc: true }
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
  companies: CompanyRow[]
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
  return `/api/companies?${params}`
})

const companies = computed(() => data.value?.companies || [])
const total = computed(() => data.value?.total ?? 0)
const list = ref<HTMLElement | null>(null)

function scroller() {
  return scrollParent(list.value)
}

function rememberList() {
  companyListMemory.q = q.value
  companyListMemory.sort = sort.value
  companyListMemory.scroll = scroller()?.scrollTop ?? 0
}

onBeforeRouteLeave(rememberList)

onMounted(() => {
  if (!fromCompany) return
  nextTick(() => {
    requestAnimationFrame(() => {
      scroller()?.scrollTo(0, companyListMemory.scroll)
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
    { path: '/companies', query: listQuery(1, size) },
    { replace: true }
  )
  await nextTick()
  scrollListTop(list.value)
}

async function showPage(next: number) {
  await navigateTo(
    { path: '/companies', query: listQuery(next) },
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

const columns = computed<TableColumn<CompanyRow>[]>(() => [
  {
    accessorKey: 'logo_url',
    header: '로고',
    meta: {
      style: {
        th: { width: '72px' },
        td: { width: '72px' }
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
  {
    accessorKey: 'types',
    header: () =>
      h(SortHeader, {
        label: '타입',
        id: 'types',
        active: sort.value,
        onSort
      })
  },
  {
    accessorKey: 'members',
    header: () =>
      h(SortHeader, {
        label: '소속 배우',
        id: 'members',
        active: sort.value,
        onSort
      }),
    meta: {
      style: { th: { width: '96px' }, td: { width: '96px' } }
    }
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
    <p v-if="!companies.length" class="text-sm text-muted">
      {{
        q.trim()
          ? '검색 결과가 없습니다.'
          : '등록된 종합 콘텐츠 스튜디오가 없습니다.'
      }}
    </p>
    <UTable v-else :data="companies" :columns="columns">
      <template #logo_url-cell="{ row }">
        <span
          v-if="row.original.logo_url"
          class="inline-flex h-[50px] w-[50px] items-center justify-center overflow-hidden rounded border border-default bg-default"
        >
          <img
            :src="row.original.logo_url"
            alt=""
            class="max-h-full max-w-full object-contain"
          />
        </span>
      </template>
      <template #name-cell="{ row }">
        <NuxtLink :to="`/companies/${row.original.id}`" class="font-medium">
          {{ row.original.name }}
        </NuxtLink>
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
