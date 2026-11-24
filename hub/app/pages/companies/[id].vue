<script setup lang="ts">
import type { TableColumn } from '@nuxt/ui'

type Company = {
  id: number
  name: string
  logo_url: string | null
  homepage: string | null
}
type Work = { id: number; title: string; year: number | null }
type Member = {
  id: number
  name: string | null
  native_name: string | null
  period_text: string | null
  is_current: boolean
}
type Payload = {
  company: Company
  types: string[]
  works: Work[]
  people: Member[]
}

const route = useRoute()
const id = computed(() => routeId(route.params.id))
const { data, error, refresh } = await storageFetch<Payload>(
  () => `/api/companies/${id.value}`
)
const logo = ref('')
const homepage = ref('')
const message = ref('')
const pending = ref(false)

watch(
  data,
  value => {
    if (!value) return
    logo.value = value.company.logo_url || ''
    homepage.value = value.company.homepage || ''
  },
  { immediate: true }
)

const workColumns: TableColumn<Work>[] = [
  { accessorKey: 'title', header: '제목' },
  { accessorKey: 'year', header: '연도' }
]
const peopleColumns: TableColumn<Member>[] = [
  { accessorKey: 'name', header: '배우' },
  { accessorKey: 'period_text', header: '기간' },
  { accessorKey: 'is_current', header: '현재' }
]

async function save() {
  message.value = ''
  pending.value = true
  try {
    await $fetch(`/api/companies/${id.value}`, {
      method: 'POST',
      body: { logo_url: logo.value, homepage: homepage.value }
    })
    await refresh()
  } catch (err) {
    message.value = errorText(err)
  } finally {
    pending.value = false
  }
}
</script>

<template>
  <UAlert
    v-if="error"
    color="error"
    variant="subtle"
    :title="errorText(error)"
  />
  <div v-else-if="data">
    <NuxtLink to="/companies" class="text-sm text-muted">
      종합 콘텐츠 스튜디오
    </NuxtLink>
    <section class="mt-3 rounded-lg border border-default bg-default p-6">
      <div class="flex gap-4">
        <span
          v-if="data.company.logo_url"
          class="inline-flex h-[150px] w-[150px] shrink-0 items-center justify-center overflow-hidden rounded-[10px] border border-default bg-default"
        >
          <img
            :src="data.company.logo_url"
            alt=""
            class="max-h-full max-w-full object-contain"
          />
        </span>
        <div class="min-w-0 flex-1">
          <h1 class="text-2xl font-semibold">
            {{ data.company.name }}
          </h1>
          <dl class="mt-4 grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
            <div v-if="data.types.length">
              <dt class="text-muted">타입</dt>
              <dd>{{ data.types.join(', ') }}</dd>
            </div>
            <div v-if="data.company.homepage">
              <dt class="text-muted">홈페이지</dt>
              <dd>
                <a
                  v-if="httpUrl(data.company.homepage)"
                  class="break-all underline"
                  :href="data.company.homepage"
                  target="_blank"
                  rel="noreferrer"
                  >{{ data.company.homepage }}</a
                >
                <template v-else>
                  {{ data.company.homepage }}
                </template>
              </dd>
            </div>
          </dl>
          <form class="mt-4 grid gap-3" @submit.prevent="save">
            <label class="block text-sm">
              <span class="text-muted">로고 이미지 URL</span>
              <UInput v-model="logo" class="mt-1 w-full" />
            </label>
            <label class="block text-sm">
              <span class="text-muted">홈페이지 URL</span>
              <UInput v-model="homepage" class="mt-1 w-full" />
            </label>
            <div>
              <UButton type="submit" :loading="pending"> 저장 </UButton>
            </div>
            <p v-if="message" class="text-sm text-error">
              {{ message }}
            </p>
          </form>
        </div>
      </div>
    </section>
    <section
      class="mt-6 overflow-hidden rounded-lg border border-default bg-default"
    >
      <h2 class="border-b border-default px-4 py-3 text-sm font-semibold">
        작품 {{ data.works.length }}
      </h2>
      <p v-if="!data.works.length" class="px-4 py-6 text-sm text-muted">
        연결된 작품이 없습니다.
      </p>
      <UTable v-else :data="data.works" :columns="workColumns">
        <template #title-cell="{ row }">
          <NuxtLink class="font-medium" :to="`/works/${row.original.id}`">{{
            row.original.title
          }}</NuxtLink>
        </template>
        <template #year-cell="{ row }">
          {{ row.original.year ?? '' }}
        </template>
      </UTable>
    </section>
    <section
      class="mt-6 overflow-hidden rounded-lg border border-default bg-default"
    >
      <h2 class="border-b border-default px-4 py-3 text-sm font-semibold">
        소속 배우 {{ data.people.length }}
      </h2>
      <p v-if="!data.people.length" class="px-4 py-6 text-sm text-muted">
        소속 배우가 없습니다.
      </p>
      <UTable v-else :data="data.people" :columns="peopleColumns">
        <template #name-cell="{ row }">
          <NuxtLink class="font-medium" :to="`/people/${row.original.id}`">{{
            row.original.name || row.original.native_name || '이름 없음'
          }}</NuxtLink>
        </template>
        <template #period_text-cell="{ row }">
          {{ row.original.period_text || '' }}
        </template>
        <template #is_current-cell="{ row }">
          {{ row.original.is_current ? '현재' : '' }}
        </template>
      </UTable>
    </section>
  </div>
</template>
