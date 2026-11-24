<script setup lang="ts">
import { h } from 'vue'
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
  kind: string
  year: number | null
  episodes: number | null
  rating: number | null
  image_url: string | null
  tags: string[] | null
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
const sort = ref<SortState | null>(null)
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

async function showPage(next: number) {
  await navigateTo(
    { path: '/works', query: listQuery(next) },
    { replace: true }
  )
}

function onSort(id: string) {
  sort.value = toggleSort(sort.value, id)
  if (page.value !== 1) showPage(1)
}

function workValue(row: WorkRow, id: string) {
  if (id === 'title') return row.title
  if (id === 'kind') return kindLabel(row.kind)
  if (id === 'year') return row.year
  if (id === 'episodes') return row.episodes
  if (id === 'rating') return row.rating
  return row.cast_count
}

const sorted = computed(() => sortRows(works.value, sort.value, workValue))
const visible = computed(() => pageRows(sorted.value, page.value))

watch(
  () => sorted.value.length,
  count => {
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

const columns = computed<TableColumn<WorkRow>[]>(() => {
  const col = (label: string, id: string) => ({
    accessorKey: id,
    header: () => h(SortHeader, { label, id, active: sort.value, onSort })
  })
  return [
    { accessorKey: 'image_url', header: '' },
    col('제목', 'title'),
    col('종류', 'kind'),
    col('연도', 'year'),
    col('에피소드', 'episodes'),
    col('평점', 'rating'),
    col('출연', 'cast_count'),
    { id: 'exception', header: '' }
  ]
})

async function onFilter(value: string) {
  await navigateTo({ path: '/works', query: listQuery(1, value) })
}

async function hide(id: number) {
  await $fetch(`/api/works/${id}/exception`, {
    method: 'POST',
    body: { deleted: deleted.value }
  })
  await refresh()
}
</script>

<template>
  <section>
    <UAlert
      v-if="error"
      color="error"
      variant="subtle"
      :title="errorText(error)"
      class="mb-4"
    />
    <div class="mb-4 flex items-end justify-between">
      <h1 class="text-xl font-semibold">작품</h1>
      <USelect
        :model-value="deleted"
        :items="options"
        class="w-28"
        @update:model-value="onFilter(String($event))"
      />
    </div>
    <p v-if="!works.length" class="text-sm text-muted">
      수집된 작품이 없습니다.
    </p>
    <UTable v-else :data="visible" :columns="columns">
      <template #image_url-cell="{ row }">
        <img
          v-if="row.original.image_url"
          :src="row.original.image_url"
          alt=""
          class="h-12 w-9 rounded object-cover"
        />
      </template>
      <template #title-cell="{ row }">
        <NuxtLink
          v-if="row.original.deleted !== 1"
          :to="`/works/${row.original.id}`"
          class="font-medium"
        >
          {{ row.original.title }}
        </NuxtLink>
        <span v-else class="font-medium">{{ row.original.title }}</span>
        <UBadge
          v-for="label in pairTags(row.original.tags)"
          :key="label"
          :color="label === 'BL' ? 'secondary' : 'primary'"
          class="ms-2"
        >
          {{ label }}
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
        <UButton color="warning" @click="hide(row.original.id)"> 예외 </UButton>
      </template>
    </UTable>
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
