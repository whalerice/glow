<script setup lang="ts">
import type { TableColumn } from '@nuxt/ui'

type CreditRow = {
  id: number
  name: string | null
  native_name: string | null
  nationality: string | null
  image_url: string | null
  roles: string[]
  works: number
}

const { data, error } = await storageFetch<{ credits: CreditRow[] }>(
  () => '/api/credits'
)
const credits = computed(() => data.value?.credits || [])
const columns: TableColumn<CreditRow>[] = [
  { accessorKey: 'image_url', header: '' },
  { accessorKey: 'name', header: '이름' },
  { accessorKey: 'roles', header: '역할' },
  { accessorKey: 'nationality', header: '국적' },
  { accessorKey: 'works', header: '작품' }
]
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
    <h1 class="mb-4 text-xl font-semibold">작가·감독</h1>
    <p v-if="!credits.length" class="text-sm text-muted">
      수집된 작가·감독이 없습니다.
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
  </section>
</template>
