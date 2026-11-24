<script setup lang="ts">
import { h } from 'vue'
import type { TableColumn } from '@nuxt/ui'
import type { PersonListRow } from '~/utils/glow'
import SortHeader from '~/components/SortHeader.vue'

type Progress = {
  on: boolean
  done: number
  total: number
  name: string
  rows: PersonListRow[]
}

const route = useRoute()
const { data, error, refresh } = await storageFetch<{
  people: PersonListRow[]
}>(() => '/api/people')
const progress = ref<Progress | null>(null)
const open = ref(false)
const mdlId = ref('')
const message = ref('')
const pending = ref(false)
let timer: ReturnType<typeof setTimeout> | undefined

const people = computed(() => data.value?.people || [])
const sort = ref<SortState | null>(null)
const page = computed(() => {
  const value = Number(route.query.page)
  if (!Number.isInteger(value) || value < 1) return 1
  return value
})

function showPage(next: number) {
  const query: Record<string, string> = {}
  if (next > 1) query.page = String(next)
  return navigateTo({ path: '/people', query }, { replace: true })
}

function onSort(id: string) {
  sort.value = toggleSort(sort.value, id)
  if (page.value !== 1) showPage(1)
}

function personValue(row: PersonListRow, id: string) {
  if (id === 'name') return row.name || row.native_name || ''
  if (id === 'mdl_id') return Number(row.mdl_id)
  if (id === 'works') return row.works
  if (id === 'collected_at') return row.collected_at
  if (id === 'nationality') return row.nationality
  return row.collect_status
}

const sorted = computed(() => sortRows(people.value, sort.value, personValue))
const visible = computed(() => pageRows(sorted.value, page.value))

watch(
  () => sorted.value.length,
  count => {
    const max = Math.max(1, Math.ceil(count / PAGE_SIZE))
    if (page.value > max) showPage(max)
  },
  { immediate: true }
)

const bar = computed(() => {
  if (!progress.value?.on) return 0
  if (!progress.value.total) return 0
  return Math.floor((progress.value.done * 100) / progress.value.total)
})

const columns = computed<TableColumn<PersonListRow>[]>(() => {
  const col = (label: string, id: string) => ({
    accessorKey: id,
    header: () => h(SortHeader, { label, id, active: sort.value, onSort })
  })
  return [
    { accessorKey: 'image_url', header: '' },
    col('이름', 'name'),
    col('MDL id', 'mdl_id'),
    col('국적', 'nationality'),
    col('상태', 'collect_status'),
    col('출연', 'works'),
    col('수집 시각', 'collected_at')
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
  progress.value = null
  await refresh()
}

function showRegister() {
  message.value = ''
  open.value = true
}

async function submit() {
  message.value = ''
  pending.value = true
  try {
    const result = await $fetch<{ person_id: number }>('/api/people', {
      method: 'POST',
      body: { mdl_id: mdlId.value }
    })
    open.value = false
    await navigateTo(`/people/${result.person_id}`)
  } catch (error) {
    message.value = errorText(error)
  } finally {
    pending.value = false
  }
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
        <div v-if="progress?.on" class="min-w-40">
          <p class="text-xs text-muted">
            작품 {{ progress.done }}/{{ progress.total }} · {{ progress.name }}
          </p>
          <div class="mt-1 h-1.5 w-40 overflow-hidden rounded bg-accented">
            <div class="h-full bg-primary" :style="{ width: `${bar}%` }" />
          </div>
        </div>
        <UButton color="neutral" variant="outline" @click="refreshWorks">
          작품 가져오기
        </UButton>
        <UButton @click="showRegister"> 배우 등록 </UButton>
      </div>
    </div>
    <p v-if="!people.length" class="text-sm text-muted">
      등록된 배우가 없습니다.
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
      <template #name-cell="{ row }">
        <NuxtLink :to="`/people/${row.original.id}`" class="font-medium">
          {{ row.original.name || row.original.native_name || '이름 없음' }}
        </NuxtLink>
        <span
          v-if="
            row.original.native_name &&
            row.original.native_name !==
              (row.original.name || row.original.native_name)
          "
          class="block text-xs text-muted"
          >{{ row.original.native_name }}</span
        >
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
        {{ row.original.works
        }}<span class="text-muted">({{ row.original.hidden }})</span>
      </template>
      <template #collected_at-cell="{ row }">
        <span class="text-muted">{{ stamp(row.original.collected_at) }}</span>
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
