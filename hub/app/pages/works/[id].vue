<script setup lang="ts">
import type { TableColumn } from '@nuxt/ui'

type Work = {
  id: number
  title: string
  kind: string
  year: number | null
  episodes: number | null
  rating: number | null
  mdl_id: string | null
  mdl_url: string | null
  image_url: string | null
  synopsis: string | null
  native_title: string | null
  tags: string[] | null
  aired: string | null
  aired_on: string | null
  content_rating: string | null
  homepage: string | null
  tmdb_id: number | null
  tmdb_kind: string | null
}

type Cast = { id: number, name: string | null, native_name: string | null, role: string, character_name: string | null }
type Credit = { id: number, name: string | null, native_name: string | null, image_url: string | null, role: string }
type Episode = { number: number, title: string | null, air_date: string | null, rating: number | null, image_url: string | null, mdl_url: string | null, summary: string | null }
type Provider = { country: string, name: string, offer: string, url: string | null }
type Network = { id: number, name: string }
type Payload = { work: Work, cast: Cast[], episodes: Episode[], credits: Credit[], providers: Provider[], networks: Network[] }

const route = useRoute()
const id = computed(() => routeId(route.params.id))
const { data, error, refresh } = await storageFetch<Payload>(() => `/api/works/${id.value}`)
const message = ref('')
const tmdbKind = ref('tv')
const tmdbId = ref('')
const pending = ref('')

watch(data, (value) => {
  if (!value) return
  tmdbKind.value = value.work.tmdb_kind || (value.work.kind === 'movie' ? 'movie' : 'tv')
  tmdbId.value = value.work.tmdb_id == null ? '' : String(value.work.tmdb_id)
}, { immediate: true })

const kinds = [
  { label: 'tv', value: 'tv' },
  { label: 'movie', value: 'movie' }
]
const creditColumns: TableColumn<Credit>[] = [
  { accessorKey: 'image_url', header: '' },
  { accessorKey: 'name', header: '이름' },
  { accessorKey: 'role', header: '역할' }
]
const episodeColumns: TableColumn<Episode>[] = [
  { accessorKey: 'image_url', header: '' },
  { accessorKey: 'number', header: '화' },
  { accessorKey: 'title', header: '제목' },
  { accessorKey: 'air_date', header: '방영' },
  { accessorKey: 'rating', header: '평점' },
  { accessorKey: 'summary', header: '설명' }
]
const castColumns: TableColumn<Cast>[] = [
  { accessorKey: 'name', header: '배우' },
  { accessorKey: 'role', header: '구분' },
  { accessorKey: 'character_name', header: '배역' }
]

function providers(country: string) {
  return (data.value?.providers || []).filter(row => row.country === country)
}

async function run(path: string, body: Record<string, string> = {}) {
  message.value = ''
  pending.value = path
  try {
    await $fetch(path, { method: 'POST', body })
    if (path.endsWith('/exception')) {
      await navigateTo('/works?deleted=0')
      return
    }
    await refresh()
  } catch (err) {
    message.value = errorText(err)
  } finally {
    pending.value = ''
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
    <NuxtLink
      to="/works"
      class="text-sm text-muted"
    >
      작품
    </NuxtLink>
    <section class="mt-3 rounded-lg border border-default bg-default p-6">
      <div class="flex gap-5">
        <img
          v-if="data.work.image_url"
          :src="data.work.image_url"
          alt=""
          class="h-44 w-32 rounded-md object-cover"
        >
        <div class="min-w-0 flex-1">
          <div class="flex items-start justify-between gap-3">
            <h1 class="text-2xl font-semibold">
              {{ data.work.title }}
            </h1>
            <UButton
              color="neutral"
              variant="outline"
              @click="run(`/api/works/${id}/exception`)"
            >
              예외
            </UButton>
          </div>
          <p class="mt-2 text-sm text-muted">
            원제
          </p>
          <p class="text-lg">
            {{ data.work.native_title || '없음' }}
          </p>
          <dl class="mt-4 grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
            <div>
              <dt class="text-muted">
                종류
              </dt><dd>{{ kindLabel(data.work.kind) }}</dd>
            </div>
            <div v-if="data.work.year != null">
              <dt class="text-muted">
                연도
              </dt><dd>{{ data.work.year }}</dd>
            </div>
            <div v-if="data.work.episodes != null">
              <dt class="text-muted">
                회차
              </dt><dd>{{ data.work.episodes }}</dd>
            </div>
            <div v-if="data.work.rating != null">
              <dt class="text-muted">
                평점
              </dt><dd>{{ data.work.rating }}</dd>
            </div>
            <div v-if="data.work.mdl_id">
              <dt class="text-muted">
                MDL id
              </dt><dd>{{ data.work.mdl_id }}</dd>
            </div>
            <div v-if="data.work.aired">
              <dt class="text-muted">
                방영
              </dt><dd>{{ data.work.aired }}</dd>
            </div>
            <div v-if="data.work.aired_on">
              <dt class="text-muted">
                방영일
              </dt><dd>{{ data.work.aired_on }}</dd>
            </div>
            <div v-if="data.work.content_rating">
              <dt class="text-muted">
                등급
              </dt><dd>{{ data.work.content_rating }}</dd>
            </div>
            <div v-if="data.work.homepage">
              <dt class="text-muted">
                홈페이지
              </dt>
              <dd>
                <a
                  v-if="httpUrl(data.work.homepage)"
                  class="break-all underline"
                  :href="data.work.homepage"
                  target="_blank"
                  rel="noreferrer"
                >{{ data.work.homepage }}</a>
                <template v-else>
                  {{ data.work.homepage }}
                </template>
              </dd>
            </div>
            <div
              v-if="data.networks.length"
              class="col-span-2"
            >
              <dt class="text-muted">
                방송사
              </dt>
              <dd>
                <NuxtLink
                  v-for="(row, index) in data.networks"
                  :key="row.id"
                  class="underline"
                  :to="`/companies/${row.id}`"
                >
                  {{ row.name }}<template v-if="index < data.networks.length - 1">, </template>
                </NuxtLink>
              </dd>
            </div>
            <div class="col-span-2">
              <div class="text-muted">
                TMDB
              </div>
              <form
                class="mt-1 flex gap-2"
                @submit.prevent="run(`/api/works/${id}/tmdb`, { tmdb_id: tmdbId, tmdb_kind: tmdbKind })"
              >
                <USelect
                  v-model="tmdbKind"
                  :items="kinds"
                  class="w-28"
                />
                <UInput
                  v-model="tmdbId"
                  placeholder="TMDB id"
                  class="w-40"
                />
                <UButton
                  type="submit"
                  :loading="pending.endsWith('/tmdb')"
                >
                  다시 가져오기
                </UButton>
              </form>
              <div
                v-for="group in [['KR', '한국'], ['TH', '태국']]"
                :key="group[0]"
              >
                <div
                  v-if="providers(group[0]!).length"
                  class="mt-2"
                >
                  <div class="text-xs text-muted">
                    {{ group[1] }}
                  </div>
                  <div
                    v-for="row in providers(group[0]!)"
                    :key="`${row.country}-${row.name}-${row.offer}`"
                    class="mt-1 flex items-center gap-2"
                  >
                    <a
                      v-if="httpUrl(row.url)"
                      class="underline"
                      :href="row.url!"
                      target="_blank"
                      rel="noreferrer"
                    >{{ row.name }}</a>
                    <span v-else>{{ row.name }}</span>
                    <UBadge
                      color="neutral"
                      variant="subtle"
                    >
                      {{ row.offer }}
                    </UBadge>
                  </div>
                </div>
              </div>
              <p
                v-if="data.work.tmdb_id != null && !data.providers.length"
                class="mt-2 text-sm text-muted"
              >
                한국·태국 제공처가 없습니다.
              </p>
            </div>
          </dl>
          <div class="mt-4">
            <p class="text-sm text-muted">
              태그
            </p>
            <div class="mt-2 flex flex-wrap gap-2">
              <UBadge
                v-for="tag in data.work.tags || []"
                :key="tag"
                color="neutral"
                variant="subtle"
              >
                {{ tag }}
              </UBadge>
              <span
                v-if="!(data.work.tags || []).length"
                class="text-sm text-muted"
              >없음</span>
            </div>
          </div>
          <p
            v-if="data.work.mdl_url"
            class="mt-3 text-sm text-muted"
          >
            출처 <span class="font-medium text-default">MyDramaList</span>
            <a
              class="underline"
              :href="data.work.mdl_url"
              target="_blank"
              rel="noreferrer"
            >원문</a>
          </p>
          <h2
            v-if="data.work.synopsis"
            class="mt-4 text-sm font-semibold"
          >
            설명
          </h2>
          <p
            v-if="data.work.synopsis"
            class="mt-4 max-h-72 overflow-y-auto whitespace-pre-line text-sm leading-6"
          >
            {{ data.work.synopsis }}
          </p>
          <UAlert
            v-if="message"
            color="error"
            variant="subtle"
            :title="message"
            class="mt-4"
          />
        </div>
      </div>
    </section>

    <section class="mt-6 overflow-hidden rounded-lg border border-default bg-default">
      <div class="flex items-center justify-between border-b border-default px-4 py-3">
        <h2 class="text-sm font-semibold">
          작가·감독 {{ data.credits.length }}
        </h2>
        <UButton
          :loading="pending.endsWith('/credits')"
          @click="run(`/api/works/${id}/credits`)"
        >
          작가·감독 가져오기
        </UButton>
      </div>
      <p class="border-b border-default px-4 py-2 text-xs text-muted">
        kuryana /v2/dramas/{slug}/cast · /v2/people/{id}
      </p>
      <p
        v-if="!data.credits.length"
        class="px-4 py-6 text-sm text-muted"
      >
        가져온 작가·감독이 없습니다.
      </p>
      <UTable
        v-else
        :data="data.credits"
        :columns="creditColumns"
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
            class="font-medium"
            :to="`/credits/${row.original.id}`"
          >
            {{ row.original.name || '' }}
          </NuxtLink>
          <span
            v-if="row.original.native_name"
            class="block text-xs text-muted"
          >{{ row.original.native_name }}</span>
        </template>
        <template #role-cell="{ row }">
          {{ creditLabel(row.original.role) }}
        </template>
      </UTable>
    </section>

    <section
      v-if="data.work.kind !== 'movie'"
      class="mt-6 overflow-hidden rounded-lg border border-default bg-default"
    >
      <div class="flex items-center justify-between border-b border-default px-4 py-3">
        <h2 class="text-sm font-semibold">
          에피소드 {{ data.episodes.length }}
        </h2>
        <UButton
          :loading="pending.endsWith('/episodes')"
          @click="run(`/api/works/${id}/episodes`)"
        >
          에피소드 가져오기
        </UButton>
      </div>
      <p class="border-b border-default px-4 py-2 text-xs text-muted">
        kuryana /v2/dramas/{slug}/episodes
      </p>
      <p
        v-if="!data.episodes.length"
        class="px-4 py-6 text-sm text-muted"
      >
        가져온 에피소드가 없습니다.
      </p>
      <UTable
        v-else
        :data="data.episodes"
        :columns="episodeColumns"
      >
        <template #image_url-cell="{ row }">
          <img
            v-if="row.original.image_url"
            :src="row.original.image_url"
            alt=""
            class="h-12 w-20 rounded object-cover"
          >
        </template>
        <template #title-cell="{ row }">
          <a
            v-if="httpUrl(row.original.mdl_url)"
            class="underline"
            :href="row.original.mdl_url!"
            target="_blank"
            rel="noreferrer"
          >{{ row.original.title || '' }}</a>
          <template v-else>
            {{ row.original.title || '' }}
          </template>
        </template>
        <template #air_date-cell="{ row }">
          {{ row.original.air_date || '' }}
        </template>
        <template #rating-cell="{ row }">
          {{ row.original.rating ?? '' }}
        </template>
        <template #summary-cell="{ row }">
          <span class="max-w-md">{{ row.original.summary || '' }}</span>
        </template>
      </UTable>
    </section>

    <section class="mt-6 overflow-hidden rounded-lg border border-default bg-default">
      <h2 class="border-b border-default px-4 py-3 text-sm font-semibold">
        출연 {{ data.cast.length }}
      </h2>
      <p
        v-if="!data.cast.length"
        class="px-4 py-6 text-sm text-muted"
      >
        출연 배우가 없습니다.
      </p>
      <UTable
        v-else
        :data="data.cast"
        :columns="castColumns"
      >
        <template #name-cell="{ row }">
          <NuxtLink
            class="font-medium"
            :to="`/people/${row.original.id}`"
          >
            {{ row.original.name || row.original.native_name || '이름 없음' }}
          </NuxtLink>
        </template>
        <template #character_name-cell="{ row }">
          {{ row.original.character_name || '' }}
        </template>
      </UTable>
    </section>
  </div>
</template>
