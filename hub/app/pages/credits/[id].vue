<script setup lang="ts">
import type { TableColumn } from '@nuxt/ui'

type Person = {
  name: string | null
  native_name: string | null
  stage_name: string | null
  mdl_id: string
  mdl_url: string | null
  nationality: string | null
  gender: string | null
  born_text: string | null
  also_known_as: string[] | null
  image_url: string | null
  about: string | null
  socials: { kind?: string, url?: string }[] | null
}

type Work = { id: number, title: string, kind: string, year: number | null, role: string }
type Payload = { person: Person, works: Work[] }

const route = useRoute()
const id = computed(() => routeId(route.params.id))
const { data, error } = await storageFetch<Payload>(() => `/api/credits/${id.value}`)
const socials = computed(() => (data.value?.person.socials || []).filter(item => httpUrl(item.url)))
const columns: TableColumn<Work>[] = [
  { accessorKey: 'title', header: '제목' },
  { accessorKey: 'kind', header: '종류' },
  { accessorKey: 'year', header: '연도' },
  { accessorKey: 'role', header: '역할' }
]
</script>

<template>
  <UAlert
    v-if="error"
    color="error"
    variant="subtle"
    :title="errorText(error)"
  />
  <div v-else-if="data">
    <NuxtLink
      to="/credits"
      class="text-sm text-muted"
    >
      작가·감독
    </NuxtLink>
    <section class="mt-3 rounded-lg border border-default bg-default p-6">
      <div class="flex gap-5">
        <img
          v-if="data.person.image_url"
          :src="data.person.image_url"
          alt=""
          class="h-44 w-32 rounded-md object-cover"
        >
        <div>
          <h1 class="text-2xl font-semibold">
            {{ data.person.name || '이름 없음' }}
          </h1>
          <p class="mt-1 text-muted">
            {{ data.person.native_name || '' }}
          </p>
          <p class="mt-3 text-sm text-muted">
            출처 <span class="font-medium text-default">MyDramaList</span>
            · 수집 kuryana <span class="font-mono text-xs">/v2/people/{{ data.person.mdl_id }}</span>
            <a
              v-if="httpUrl(data.person.mdl_url)"
              class="underline"
              :href="data.person.mdl_url!"
              target="_blank"
              rel="noreferrer"
            >원문</a>
          </p>
          <dl class="mt-4 grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
            <div v-if="data.person.stage_name">
              <dt class="text-muted">
                활동명
              </dt><dd>{{ data.person.stage_name }}</dd>
            </div>
            <div>
              <dt class="text-muted">
                MDL id
              </dt><dd>{{ data.person.mdl_id }}</dd>
            </div>
            <div v-if="data.person.nationality">
              <dt class="text-muted">
                국적
              </dt><dd>{{ data.person.nationality }}</dd>
            </div>
            <div v-if="data.person.gender">
              <dt class="text-muted">
                성별
              </dt><dd>{{ data.person.gender }}</dd>
            </div>
            <div v-if="data.person.born_text">
              <dt class="text-muted">
                생일
              </dt><dd>{{ data.person.born_text }}</dd>
            </div>
            <div v-if="(data.person.also_known_as || []).length">
              <dt class="text-muted">
                다른 이름
              </dt><dd>{{ (data.person.also_known_as || []).join(', ') }}</dd>
            </div>
          </dl>
          <ul
            v-if="socials.length"
            class="mt-4 list-disc pl-5 text-sm"
          >
            <li
              v-for="item in socials"
              :key="item.url"
            >
              <a
                class="underline"
                :href="item.url"
                target="_blank"
                rel="noreferrer"
              >{{ item.kind || item.url }}</a>
            </li>
          </ul>
          <p
            v-if="data.person.about"
            class="mt-4 max-h-72 overflow-y-auto whitespace-pre-line text-sm leading-6"
          >
            {{ data.person.about }}
          </p>
        </div>
      </div>
    </section>
    <section class="mt-6 overflow-hidden rounded-lg border border-default bg-default">
      <h2 class="border-b border-default px-4 py-3 text-sm font-semibold">
        작품 {{ data.works.length }}
      </h2>
      <p
        v-if="!data.works.length"
        class="px-4 py-6 text-sm text-muted"
      >
        연결된 작품이 없습니다.
      </p>
      <UTable
        v-else
        :data="data.works"
        :columns="columns"
      >
        <template #title-cell="{ row }">
          <NuxtLink
            class="font-medium"
            :to="`/works/${row.original.id}`"
          >{{ row.original.title }}</NuxtLink>
        </template>
        <template #kind-cell="{ row }">
          {{ kindLabel(row.original.kind) }}
        </template>
        <template #year-cell="{ row }">
          {{ row.original.year ?? '' }}
        </template>
        <template #role-cell="{ row }">
          {{ creditLabel(row.original.role) }}
        </template>
      </UTable>
    </section>
  </div>
</template>
