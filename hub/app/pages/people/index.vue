<script setup lang="ts">
import type { TableColumn } from '@nuxt/ui'
import type { PersonListRow } from '~/utils/glow'

type Progress = {
  on: boolean
  done: number
  total: number
  name: string
  rows: PersonListRow[]
}

const { data, error, refresh } = await storageFetch<{ people: PersonListRow[] }>(() => '/api/people')
const progress = ref<Progress | null>(null)
let timer: ReturnType<typeof setTimeout> | undefined

const people = computed(() => data.value?.people || [])
const bar = computed(() => {
  if (!progress.value?.on) return 0
  if (!progress.value.total) return 0
  return Math.floor(progress.value.done * 100 / progress.value.total)
})

const columns: TableColumn<PersonListRow>[] = [
  { accessorKey: 'image_url', header: '' },
  { accessorKey: 'name', header: '이름' },
  { accessorKey: 'mdl_id', header: 'MDL id' },
  { accessorKey: 'nationality', header: '국적' },
  { accessorKey: 'collect_status', header: '상태' },
  { accessorKey: 'works', header: '출연' },
  { accessorKey: 'collected_at', header: '수집 시각' }
]

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
  progress.value = null
  await refresh()
}

async function refreshWorks() {
  await $fetch('/api/people/works', { method: 'POST' })
  clearTimeout(timer)
  await tick()
}

onUnmounted(() => clearTimeout(timer))
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
    <div class="mb-4 flex items-end justify-between gap-3">
      <h1 class="text-xl font-semibold">
        배우 <span class="text-muted">{{ people.length }}</span>
      </h1>
      <div class="flex items-center gap-2">
        <div
          v-if="progress?.on"
          class="min-w-40"
        >
          <p class="text-xs text-muted">
            작품 {{ progress.done }}/{{ progress.total }} · {{ progress.name }}
          </p>
          <div class="mt-1 h-1.5 w-40 overflow-hidden rounded bg-accented">
            <div
              class="h-full bg-primary"
              :style="{ width: `${bar}%` }"
            />
          </div>
        </div>
        <UButton
          color="neutral"
          variant="outline"
          @click="refreshWorks"
        >
          작품 가져오기
        </UButton>
        <UButton to="/register">
          배우 등록
        </UButton>
      </div>
    </div>
    <p
      v-if="!people.length"
      class="text-sm text-muted"
    >
      등록된 배우가 없습니다.
    </p>
    <UTable
      v-else
      :data="people"
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
      <template #name-cell="{ row }">
        <NuxtLink
          :to="`/people/${row.original.id}`"
          class="font-medium"
        >
          {{ row.original.name || row.original.native_name || '이름 없음' }}
        </NuxtLink>
        <span
          v-if="row.original.native_name && row.original.native_name !== (row.original.name || row.original.native_name)"
          class="block text-xs text-muted"
        >{{ row.original.native_name }}</span>
      </template>
      <template #nationality-cell="{ row }">
        {{ row.original.nationality || '' }}
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
        {{ row.original.works }}<span class="text-muted">({{ row.original.hidden }})</span>
      </template>
      <template #collected_at-cell="{ row }">
        <span class="text-muted">{{ stamp(row.original.collected_at) }}</span>
      </template>
    </UTable>
  </section>
</template>
