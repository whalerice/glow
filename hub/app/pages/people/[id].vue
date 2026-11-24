<script setup lang="ts">
import type { TableColumn } from '@nuxt/ui'
import type { SourceRow } from '~/utils/glow'

type Person = {
  id: number
  mdl_id: string
  name: string | null
  native_name: string | null
  stage_name: string | null
  also_known_as: string[] | null
  nationality: string | null
  gender: string | null
  born_text: string | null
  image_url: string | null
  mdl_url: string | null
  collect_status: string
  collect_error: string | null
}

type Work = {
  id: number
  title: string
  kind: string
  year: number | null
  role: string
  character_name: string | null
  rating: number | null
}

type Affiliation = {
  company_id: number
  name: string
  period_text: string | null
  is_current: boolean
}

type Ship = { slug: string, name: string, image_url: string | null }

type Payload = {
  person: Person
  works: Work[]
  affiliations: Affiliation[]
  ships: Ship[]
  actor: boolean
  sources: {
    sapphic_effect: SourceRow
    gmmtv_fandom: SourceRow
    en_wikipedia: SourceRow
  }
}

const route = useRoute()
const id = computed(() => routeId(route.params.id))
const { data, error } = await storageFetch<Payload>(() => `/api/people/${id.value}`)

const person = computed(() => data.value?.person)
const aliases = computed(() => (person.value?.also_known_as || []).join(', '))
const currentAgencies = computed(() => (data.value?.affiliations || []).filter(row => row.is_current))
const history = computed(() => (data.value?.affiliations || []).filter(row => !row.is_current || row.period_text))
const sapphic = computed(() => data.value?.sources.sapphic_effect || null)
const fandom = computed(() => data.value?.sources.gmmtv_fandom || null)
const wiki = computed(() => data.value?.sources.en_wikipedia || null)
const gmmtv = computed(() => isGmmtv(sapphic.value))

const sapphicQuery = computed(() => person.value?.name || person.value?.mdl_id || '')
const fandomQuery = computed(() => person.value?.stage_name || person.value?.name || person.value?.mdl_id || '')
const wikiQuery = computed(() => person.value?.name || person.value?.stage_name || person.value?.mdl_id || '')

const columns: TableColumn<Work>[] = [
  { accessorKey: 'title', header: '제목' },
  { accessorKey: 'kind', header: '종류' },
  { accessorKey: 'year', header: '연도' },
  { accessorKey: 'role', header: '구분' },
  { accessorKey: 'character_name', header: '배역' },
  { accessorKey: 'rating', header: '평점' }
]

function payloadText(source: SourceRow, key: string) {
  const value = source?.payload?.[key]
  return typeof value === 'string' ? value : ''
}

function socials(source: SourceRow) {
  const value = source?.payload?.socials
  if (!Array.isArray(value)) return []
  return value.filter(item => item && typeof item === 'object' && httpUrl((item as { url?: string }).url)) as { kind?: string, url: string }[]
}

async function remove() {
  if (!confirm('이 배우와 연결을 삭제합니다. 작품과 소속사는 남습니다.')) return
  await $fetch(`/api/people/${id.value}/delete`, { method: 'POST', body: {} })
  await navigateTo('/people')
}
</script>

<template>
  <UAlert
    v-if="error"
    color="error"
    variant="subtle"
    :title="errorText(error)"
  />
  <div v-else-if="person && data">
    <NuxtLink
      to="/people"
      class="text-sm text-muted"
    >
      배우
    </NuxtLink>
    <section class="mt-3 rounded-lg border border-default bg-default p-6">
      <div class="flex gap-5">
        <img
          v-if="person.image_url"
          :src="person.image_url"
          alt=""
          class="h-44 w-32 rounded-md object-cover"
        >
        <div>
          <div class="flex items-center gap-2">
            <h1 class="text-2xl font-semibold">
              {{ person.name || '이름 없음' }}
            </h1>
            <UBadge
              :color="statusColor(person.collect_status)"
              variant="subtle"
            >
              {{ person.collect_status }}
            </UBadge>
            <UButton
              v-if="data.actor"
              size="xs"
              color="error"
              variant="outline"
              @click="remove"
            >
              삭제
            </UButton>
          </div>
          <p class="mt-1 text-muted">
            {{ person.native_name || '' }}
          </p>
          <p class="mt-3 text-sm text-muted">
            출처 <span class="font-medium text-default">MyDramaList</span>
            · 수집 kuryana <span class="font-mono text-xs">/v2/people/{{ person.mdl_id }}</span>
            <a
              v-if="httpUrl(person.mdl_url)"
              class="underline"
              :href="person.mdl_url!"
              target="_blank"
              rel="noreferrer"
            >원문</a>
          </p>
          <dl class="mt-4 grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
            <div v-if="person.stage_name">
              <dt class="text-muted">
                활동명
              </dt>
              <dd>{{ person.stage_name }}</dd>
            </div>
            <div>
              <dt class="text-muted">
                MDL id
              </dt>
              <dd>{{ person.mdl_id }}</dd>
            </div>
            <div v-if="person.nationality">
              <dt class="text-muted">
                국적
              </dt>
              <dd>{{ person.nationality }}</dd>
            </div>
            <div v-if="person.gender">
              <dt class="text-muted">
                성별
              </dt>
              <dd>{{ person.gender }}</dd>
            </div>
            <div v-if="person.born_text">
              <dt class="text-muted">
                생일
              </dt>
              <dd>{{ person.born_text }}</dd>
            </div>
            <div v-if="aliases">
              <dt class="text-muted">
                다른 이름
              </dt>
              <dd>{{ aliases }}</dd>
            </div>
          </dl>
          <UAlert
            v-if="person.collect_error"
            color="error"
            variant="subtle"
            :title="person.collect_error"
            class="mt-4"
          />
        </div>
      </div>
    </section>

    <section
      v-if="data.affiliations.length"
      class="mt-6 rounded-lg border border-default bg-default p-6"
    >
      <h2 class="text-sm font-semibold">
        소속
      </h2>
      <p class="mt-2 text-sm">
        현재
        <template v-if="currentAgencies.length">
          <NuxtLink
            v-for="row in currentAgencies"
            :key="row.company_id"
            class="underline"
            :to="`/companies/${row.company_id}`"
          >{{ row.name }}</NuxtLink>
        </template>
        <template v-else>
          없음
        </template>
      </p>
      <ul
        v-if="history.length"
        class="mt-3 list-disc pl-5 text-sm"
      >
        <li
          v-for="row in history"
          :key="`${row.company_id}-${row.period_text}`"
        >
          <NuxtLink
            class="underline"
            :to="`/companies/${row.company_id}`"
          >
            {{ row.name }}<template v-if="row.period_text"> {{ row.period_text }}</template><template v-if="row.is_current"> 현재</template>
          </NuxtLink>
        </li>
      </ul>
    </section>

    <section class="mt-6 rounded-lg border border-default bg-default p-6">
      <div class="flex items-start justify-between gap-4">
        <div>
          <h2 class="text-sm font-semibold">
            Sapphic Effect
          </h2>
          <p
            v-if="!sapphic"
            class="mt-2 text-sm text-muted"
          >
            선택한 추가 정보가 없습니다.
          </p>
          <p
            v-else
            class="mt-1 text-sm text-muted"
          >
            출처
            <a
              v-if="httpUrl(sapphic.payload.url)"
              class="font-medium text-default underline"
              :href="String(sapphic.payload.url)"
              target="_blank"
              rel="noreferrer"
            >{{ sapphic.display_name || sapphic.external_key }}</a>
            <span v-else>{{ sapphic.display_name || sapphic.external_key }}</span>
            · {{ stamp(sapphic.selected_at) }}
          </p>
        </div>
        <NuxtLink
          class="text-sm font-medium underline"
          :to="`/people/${person.id}/sapphic?q=${encodeURIComponent(sapphicQuery)}`"
        >
          검색해서 고르기
        </NuxtLink>
      </div>
      <div
        v-if="sapphic"
        class="mt-4 flex gap-4"
      >
        <img
          v-if="httpUrl(sapphic.payload.image_url) || payloadText(sapphic, 'image_url')"
          :src="payloadText(sapphic, 'image_url')"
          alt=""
          class="h-24 w-20 rounded-md object-cover"
        >
        <dl class="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
          <div v-if="payloadText(sapphic, 'birthday')">
            <dt class="text-muted">
              생일
            </dt>
            <dd>{{ payloadText(sapphic, 'birthday') }}</dd>
          </div>
          <div v-if="payloadText(sapphic, 'company') || (sapphic.payload.company && typeof sapphic.payload.company === 'object')">
            <dt class="text-muted">
              소속사
            </dt>
            <dd>{{ (sapphic.payload.company as { name?: string })?.name || '' }}</dd>
          </div>
        </dl>
      </div>
      <ul
        v-if="data.ships.length"
        class="mt-4 list-disc pl-5 text-sm"
      >
        <li
          v-for="ship in data.ships"
          :key="ship.slug"
        >
          <a
            class="underline"
            :href="`https://www.sapphiceffect.com/ships/${ship.slug}`"
            target="_blank"
            rel="noreferrer"
          >{{ ship.name }}</a>
        </li>
      </ul>
      <ul
        v-if="socials(sapphic).length"
        class="mt-3 list-disc pl-5 text-sm"
      >
        <li
          v-for="item in socials(sapphic)"
          :key="item.url"
        >
          <a
            class="underline"
            :href="item.url"
          >{{ item.kind || item.url }}</a>
        </li>
      </ul>
      <p
        v-if="payloadText(sapphic, 'biography')"
        class="mt-4 max-h-72 overflow-y-auto whitespace-pre-line text-sm leading-6"
      >
        {{ payloadText(sapphic, 'biography') }}
      </p>
    </section>

    <section
      v-if="fandom || gmmtv"
      class="mt-6 rounded-lg border border-default bg-default p-6"
    >
      <div class="flex items-start justify-between gap-4">
        <div>
          <h2 class="text-sm font-semibold">
            GMMTV Wiki
          </h2>
          <p
            v-if="!fandom"
            class="mt-2 text-sm text-muted"
          >
            선택한 위키 정보가 없습니다.
          </p>
          <p
            v-else
            class="mt-1 text-sm text-muted"
          >
            출처
            <a
              v-if="httpUrl(fandom.payload.url)"
              class="font-medium text-default underline"
              :href="String(fandom.payload.url)"
              target="_blank"
              rel="noreferrer"
            >{{ fandom.display_name || fandom.external_key }}</a>
            · CC-BY-SA · {{ stamp(fandom.selected_at) }}
          </p>
        </div>
        <NuxtLink
          v-if="gmmtv"
          class="text-sm font-medium underline"
          :to="`/people/${person.id}/fandom?q=${encodeURIComponent(fandomQuery)}`"
        >
          위키에서 고르기
        </NuxtLink>
      </div>
      <div
        v-if="fandom"
        class="mt-4"
      >
        <dl class="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
          <div v-if="payloadText(fandom, 'birth_name')">
            <dt class="text-muted">
              본명
            </dt><dd>{{ payloadText(fandom, 'birth_name') }}</dd>
          </div>
          <div v-if="payloadText(fandom, 'nickname')">
            <dt class="text-muted">
              닉네임
            </dt><dd>{{ payloadText(fandom, 'nickname') }}</dd>
          </div>
          <div v-if="payloadText(fandom, 'native_name')">
            <dt class="text-muted">
              태국어 이름
            </dt><dd>{{ payloadText(fandom, 'native_name') }}</dd>
          </div>
          <div v-if="payloadText(fandom, 'birthday')">
            <dt class="text-muted">
              생일
            </dt><dd>{{ payloadText(fandom, 'birthday') }}</dd>
          </div>
          <div v-if="payloadText(fandom, 'birth_place')">
            <dt class="text-muted">
              출생지
            </dt><dd>{{ payloadText(fandom, 'birth_place') }}</dd>
          </div>
          <div v-if="payloadText(fandom, 'height')">
            <dt class="text-muted">
              키
            </dt><dd>{{ payloadText(fandom, 'height') }}</dd>
          </div>
          <div v-if="payloadText(fandom, 'weight')">
            <dt class="text-muted">
              몸무게
            </dt><dd>{{ payloadText(fandom, 'weight') }}</dd>
          </div>
          <div v-if="payloadText(fandom, 'years_active')">
            <dt class="text-muted">
              활동
            </dt><dd>{{ payloadText(fandom, 'years_active') }}</dd>
          </div>
        </dl>
        <p
          v-if="payloadText(fandom, 'early_life')"
          class="mt-4 max-h-72 overflow-y-auto whitespace-pre-line text-sm leading-6"
        >
          {{ payloadText(fandom, 'early_life') }}
        </p>
      </div>
    </section>

    <section class="mt-6 rounded-lg border border-default bg-default p-6">
      <div class="flex items-start justify-between gap-4">
        <div>
          <h2 class="text-sm font-semibold">
            위키
          </h2>
          <p
            v-if="!wiki"
            class="mt-2 text-sm text-muted"
          >
            {{ gmmtv ? 'GMMTV Wiki에 없는 항목만 고른다.' : '선택한 위키 정보가 없습니다.' }}
          </p>
          <p
            v-else
            class="mt-1 text-sm text-muted"
          >
            출처
            <a
              v-if="httpUrl(wiki.payload.url)"
              class="font-medium text-default underline"
              :href="String(wiki.payload.url)"
              target="_blank"
              rel="noreferrer"
            >{{ wiki.display_name || wiki.external_key }}</a>
            · CC-BY-SA · {{ stamp(wiki.selected_at) }}
          </p>
        </div>
        <NuxtLink
          class="text-sm font-medium underline"
          :to="`/people/${person.id}/wiki?q=${encodeURIComponent(wikiQuery)}`"
        >
          위키에서 고르기
        </NuxtLink>
      </div>
      <div
        v-if="wiki"
        class="mt-4"
      >
        <dl class="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
          <div v-if="payloadText(wiki, 'birth_name')">
            <dt class="text-muted">
              본명
            </dt><dd>{{ payloadText(wiki, 'birth_name') }}</dd>
          </div>
          <div v-if="payloadText(wiki, 'native_name')">
            <dt class="text-muted">
              원어 이름
            </dt><dd>{{ payloadText(wiki, 'native_name') }}</dd>
          </div>
          <div v-if="payloadText(wiki, 'birthday')">
            <dt class="text-muted">
              생일
            </dt><dd>{{ payloadText(wiki, 'birthday') }}</dd>
          </div>
          <div v-if="payloadText(wiki, 'birth_place')">
            <dt class="text-muted">
              출생지
            </dt><dd>{{ payloadText(wiki, 'birth_place') }}</dd>
          </div>
          <div v-if="payloadText(wiki, 'height')">
            <dt class="text-muted">
              키
            </dt><dd>{{ payloadText(wiki, 'height') }}</dd>
          </div>
          <div v-if="payloadText(wiki, 'education')">
            <dt class="text-muted">
              학력
            </dt><dd>{{ payloadText(wiki, 'education') }}</dd>
          </div>
          <div v-if="payloadText(wiki, 'years_active')">
            <dt class="text-muted">
              활동 기간
            </dt><dd>{{ payloadText(wiki, 'years_active') }}</dd>
          </div>
        </dl>
        <template
          v-for="block in [['career', 'Career'], ['fashion', 'Fashion'], ['ambassadorship', 'Ambassadorship'], ['accolades', 'Accolades']]"
          :key="block[0]"
        >
          <h3
            v-if="payloadText(wiki, block[0]!)"
            class="mt-4 text-sm font-medium"
          >
            {{ block[1] }}
          </h3>
          <p
            v-if="payloadText(wiki, block[0]!)"
            class="mt-4 max-h-72 overflow-y-auto whitespace-pre-line text-sm leading-6"
          >
            {{ payloadText(wiki, block[0]!) }}
          </p>
        </template>
      </div>
    </section>

    <section class="mt-6 overflow-hidden rounded-lg border border-default bg-default">
      <div class="flex items-center justify-between border-b border-default px-4 py-3">
        <h2 class="text-sm font-semibold">
          출연작 {{ data.works.length }}
        </h2>
        <p class="text-xs text-muted">
          MyDramaList 인물 응답의 필모그래피
        </p>
      </div>
      <p
        v-if="!data.works.length"
        class="px-4 py-6 text-sm text-muted"
      >
        출연작이 없습니다.
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
          >
            {{ row.original.title }}
          </NuxtLink>
        </template>
        <template #kind-cell="{ row }">
          {{ kindLabel(row.original.kind) }}
        </template>
        <template #year-cell="{ row }">
          {{ row.original.year ?? '' }}
        </template>
        <template #character_name-cell="{ row }">
          {{ row.original.character_name || '' }}
        </template>
        <template #rating-cell="{ row }">
          {{ row.original.rating ?? '' }}
        </template>
      </UTable>
    </section>
  </div>
</template>
