<script setup lang="ts">
import type { TableColumn } from '@nuxt/ui'

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
}

const route = useRoute()
const deleted = computed(() => {
  const value = String(route.query.deleted || '0')
  if (value === 'all' || value === '1') return value
  return '0'
})

const { data, error, refresh } = await storageFetch<{ deleted: string, works: WorkRow[] }>(
  () => `/api/works?deleted=${deleted.value}`
)

const works = computed(() => data.value?.works || [])
const options = [
  { label: 'All', value: 'all' },
  { label: 'Show', value: '0' },
  { label: 'Hide', value: '1' }
]

const columns: TableColumn<WorkRow>[] = [
  { accessorKey: 'image_url', header: '' },
  { accessorKey: 'title', header: '제목' },
  { accessorKey: 'kind', header: '종류' },
  { accessorKey: 'year', header: '연도' },
  { accessorKey: 'episodes', header: '에피소드' },
  { accessorKey: 'rating', header: '평점' },
  { accessorKey: 'cast_count', header: '출연' },
  { id: 'exception', header: '' }
]

async function onFilter(value: string) {
  await navigateTo({ path: '/works', query: { deleted: value } })
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
      <h1 class="text-xl font-semibold">
        작품
      </h1>
      <USelect
        :model-value="deleted"
        :items="options"
        class="w-28"
        @update:model-value="onFilter(String($event))"
      />
    </div>
    <p
      v-if="!works.length"
      class="text-sm text-muted"
    >
      수집된 작품이 없습니다.
    </p>
    <UTable
      v-else
      :data="works"
      :columns="columns"
    >
      <template #image_url-cell="{ row }">
        <img
          v-if="row.original.image_url"
          :src="row.original.image_url"
          alt=""
          class="h-12 w-9 rounded object-cover"
        >
      </template>
      <template #title-cell="{ row }">
        <NuxtLink
          v-if="row.original.deleted !== 1"
          :to="`/works/${row.original.id}`"
          class="font-medium"
        >
          {{ row.original.title }}
        </NuxtLink>
        <span
          v-else
          class="font-medium"
        >{{ row.original.title }}</span>
        <UBadge
          v-for="label in pairTags(row.original.tags)"
          :key="label"
          color="neutral"
          variant="subtle"
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
      <template #exception-cell="{ row }">
        <UButton
          size="xs"
          color="neutral"
          variant="outline"
          @click="hide(row.original.id)"
        >
          예외
        </UButton>
      </template>
    </UTable>
  </section>
</template>
