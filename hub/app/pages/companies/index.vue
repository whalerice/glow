<script setup lang="ts">
import type { TableColumn } from '@nuxt/ui'

type CompanyRow = {
  id: number
  name: string
  logo_url: string | null
  members: number
  types: string
}

const { data, error } = await storageFetch<{ companies: CompanyRow[] }>(
  () => '/api/companies'
)
const companies = computed(() => data.value?.companies || [])
const columns: TableColumn<CompanyRow>[] = [
  { accessorKey: 'logo_url', header: '로고' },
  { accessorKey: 'name', header: '이름' },
  { accessorKey: 'types', header: '타입' },
  { accessorKey: 'members', header: '소속 배우' }
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
    <h1 class="mb-4 text-xl font-semibold">종합 콘텐츠 스튜디오</h1>
    <p v-if="!companies.length" class="text-sm text-muted">
      등록된 종합 콘텐츠 스튜디오가 없습니다.
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
  </section>
</template>
