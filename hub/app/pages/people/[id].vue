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
  image_url: string | null
  tags: string[] | null
  queer: number | null
  queer_name: string | null
}

type Affiliation = {
  company_id: number
  name: string
  period_text: string | null
  is_current: boolean
}

type ShipPartner = {
  id: number
  name: string | null
  image_url: string | null
  deleted: number
}

type Ship = {
  slug: string
  name: string
  image_url: string | null
  partners: ShipPartner[]
}

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
const { data, error, refresh } = await storageFetch<Payload>(
  () => `/api/people/${id.value}`
)
const sapphicOpen = ref(false)
const fandomOpen = ref(false)
const wikiOpen = ref(false)

async function onSourceSaved(which: 'sapphic' | 'fandom' | 'wiki') {
  if (which === 'sapphic') sapphicOpen.value = false
  if (which === 'fandom') fandomOpen.value = false
  if (which === 'wiki') wikiOpen.value = false
  await refresh()
}

const person = computed(() => data.value?.person)
const aliases = computed(() => (person.value?.also_known_as || []).join(', '))
const currentAgencies = computed(() =>
  (data.value?.affiliations || []).filter(row => row.is_current)
)
const history = computed(() =>
  (data.value?.affiliations || []).filter(
    row => !row.is_current || row.period_text
  )
)
const sapphic = computed(() => data.value?.sources.sapphic_effect || null)
const fandom = computed(() => data.value?.sources.gmmtv_fandom || null)
const wiki = computed(() => data.value?.sources.en_wikipedia || null)
const gmmtv = computed(() => isGmmtv(sapphic.value))

const sapphicQuery = computed(
  () => person.value?.name || person.value?.mdl_id || ''
)
const fandomQuery = computed(
  () =>
    person.value?.stage_name || person.value?.name || person.value?.mdl_id || ''
)
const wikiQuery = computed(
  () =>
    person.value?.name || person.value?.stage_name || person.value?.mdl_id || ''
)

const page = ref(1)
const works = computed(() => data.value?.works || [])
const visibleWorks = computed(() => pageRows(works.value, page.value))

watch(id, () => {
  page.value = 1
})

watch(
  () => works.value.length,
  count => {
    const max = Math.max(1, Math.ceil(count / PAGE_SIZE))
    if (page.value > max) page.value = max
  }
)

const columns: TableColumn<Work>[] = [
  { accessorKey: 'image_url', header: '' },
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

function agents(source: SourceRow) {
  const value = source?.payload?.agent
  if (!Array.isArray(value)) return []
  return value.filter(
    (item): item is { name: string; period_text?: string | null } =>
      !!item &&
      typeof item === 'object' &&
      typeof (item as { name?: string }).name === 'string' &&
      !!(item as { name: string }).name.trim()
  )
}

function socials(source: SourceRow) {
  const value = source?.payload?.socials
  if (!Array.isArray(value)) return []
  return value.filter(
    item =>
      item &&
      typeof item === 'object' &&
      httpUrl((item as { url?: string }).url)
  ) as { kind?: string; url: string }[]
}

const collecting = ref(false)
const recollectError = ref('')

async function recollect() {
  if (
    !confirm(
      'MDL로 다시 수집합니다. 성공하면 위키·Sapphic·팬덤·소속·ship을 지웁니다. 작품과 회사는 남고, 작가·감독 연결은 유지합니다.'
    )
  ) {
    return
  }
  collecting.value = true
  recollectError.value = ''
  try {
    await $fetch(`/api/people/${id.value}/recollect`, { method: 'POST', body: {} })
    await refresh()
  } catch (err) {
    recollectError.value = errorText(err)
  } finally {
    collecting.value = false
  }
}

async function hide(deleted: 1 | 2) {
  const text =
    deleted === 1
      ? '이 배우를 예외 처리합니다.'
      : '이 배우를 삭제로 표시합니다. 행은 남습니다.'
  if (!confirm(text)) return
  await $fetch(`/api/people/${id.value}/exception`, {
    method: 'POST',
    body: { deleted }
  })
  await navigateTo('/people?deleted=0')
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
    <section class="rounded-lg border border-default bg-default p-6">
      <div class="flex gap-5">
        <img
          v-if="person.image_url"
          :src="person.image_url"
          alt=""
          class="h-44 w-32 rounded-md object-cover"
        />
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
              color="neutral"
              variant="outline"
              :loading="collecting"
              @click="recollect"
            >
              재수집
            </UButton>
            <UButton
              v-if="data.actor"
              color="neutral"
              variant="outline"
              @click="hide(1)"
            >
              예외
            </UButton>
            <UButton
              v-if="data.actor"
              color="error"
              variant="outline"
              @click="hide(2)"
            >
              삭제
            </UButton>
          </div>
          <p class="mt-1 text-muted">
            {{ person.native_name || '' }}
          </p>
          <p class="mt-3 text-sm text-muted">
            출처 <span class="font-medium text-default">MyDramaList</span> ·
            수집 kuryana
            <span class="font-mono text-xs"
              >/v2/people/{{ person.mdl_id }}</span
            >
            <a
              v-if="httpUrl(person.mdl_url)"
              class="underline"
              :href="person.mdl_url!"
              target="_blank"
              rel="noreferrer"
              >원문</a
            >
          </p>
          <dl class="mt-4 grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
            <div v-if="person.stage_name">
              <dt class="text-muted">활동명</dt>
              <dd>{{ person.stage_name }}</dd>
            </div>
            <div>
              <dt class="text-muted">MDL id</dt>
              <dd>{{ person.mdl_id }}</dd>
            </div>
            <div v-if="person.nationality">
              <dt class="text-muted">국적</dt>
              <dd>{{ person.nationality }}</dd>
            </div>
            <div v-if="person.gender">
              <dt class="text-muted">성별</dt>
              <dd>{{ person.gender }}</dd>
            </div>
            <div v-if="person.born_text">
              <dt class="text-muted">생일</dt>
              <dd>{{ person.born_text }}</dd>
            </div>
            <div v-if="aliases">
              <dt class="text-muted">다른 이름</dt>
              <dd>{{ aliases }}</dd>
            </div>
          </dl>
          <UAlert
            v-if="recollectError || person.collect_error"
            color="error"
            variant="subtle"
            :title="recollectError || person.collect_error"
            class="mt-4"
          />
        </div>
      </div>
    </section>

    <section
      v-if="data.affiliations.length"
      class="mt-6 rounded-lg border border-default bg-default p-6"
    >
      <h2 class="text-sm font-semibold">소속</h2>
      <p class="mt-2 text-sm">
        현재
        <template v-if="currentAgencies.length">
          <NuxtLink
            v-for="row in currentAgencies"
            :key="row.company_id"
            class="underline"
            :to="`/companies/${row.company_id}`"
            >{{ row.name }}</NuxtLink
          >
        </template>
        <template v-else> 없음 </template>
      </p>
      <ul v-if="history.length" class="mt-3 list-disc pl-5 text-sm">
        <li
          v-for="row in history"
          :key="`${row.company_id}-${row.period_text}`"
        >
          <NuxtLink class="underline" :to="`/companies/${row.company_id}`">
            {{ row.name
            }}<template v-if="row.period_text"> {{ row.period_text }}</template
            ><template v-if="row.is_current"> 현재</template>
          </NuxtLink>
        </li>
      </ul>
    </section>

    <section class="mt-6 rounded-lg border border-default bg-default p-6">
      <div class="flex items-start justify-between gap-4">
        <div>
          <h2 class="text-sm font-semibold">Sapphic Effect</h2>
          <p v-if="!sapphic" class="mt-2 text-sm text-muted">
            선택한 추가 정보가 없습니다.
          </p>
          <p v-else class="mt-1 text-sm text-muted">
            출처
            <a
              v-if="httpUrl(sapphic.payload.url)"
              class="font-medium text-default underline"
              :href="String(sapphic.payload.url)"
              target="_blank"
              rel="noreferrer"
              >{{ sapphic.display_name || sapphic.external_key }}</a
            >
            <span v-else>{{
              sapphic.display_name || sapphic.external_key
            }}</span>
            · {{ stamp(sapphic.selected_at) }}
          </p>
        </div>
        <UButton color="neutral" variant="outline" @click="sapphicOpen = true">
          검색해서 고르기
        </UButton>
      </div>
      <div v-if="sapphic" class="mt-4 flex gap-4">
        <img
          v-if="
            httpUrl(sapphic.payload.image_url) ||
            payloadText(sapphic, 'image_url')
          "
          :src="payloadText(sapphic, 'image_url')"
          alt=""
          class="h-24 w-20 rounded-md object-cover"
        />
        <dl class="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
          <div v-if="payloadText(sapphic, 'birthday')">
            <dt class="text-muted">생일</dt>
            <dd>{{ payloadText(sapphic, 'birthday') }}</dd>
          </div>
          <div
            v-if="
              payloadText(sapphic, 'company') ||
              (sapphic.payload.company &&
                typeof sapphic.payload.company === 'object')
            "
          >
            <dt class="text-muted">소속사</dt>
            <dd>
              {{ (sapphic.payload.company as { name?: string })?.name || '' }}
            </dd>
          </div>
        </dl>
      </div>
      <ul v-if="data.ships.length" class="mt-4 space-y-3 text-sm">
        <li v-for="ship in data.ships" :key="ship.slug">
          <a
            class="underline"
            :href="`https://www.sapphiceffect.com/ships/${ship.slug}`"
            target="_blank"
            rel="noreferrer"
            >{{ ship.name }}</a
          >
          <div
            v-if="ship.partners?.length"
            class="mt-2 flex flex-wrap items-center gap-3"
          >
            <NuxtLink
              v-for="mate in ship.partners.filter(p => p.deleted === 0)"
              :key="mate.id"
              :to="`/people/${mate.id}`"
              class="flex items-center gap-2 font-medium"
            >
              <img
                v-if="mate.image_url"
                :src="mate.image_url"
                alt=""
                class="size-10 rounded-full object-cover"
              />
              <span
                v-else
                class="flex size-10 items-center justify-center rounded-full bg-elevated text-xs text-muted"
                >?</span
              >
              {{ mate.name || '이름 없음' }}
            </NuxtLink>
            <span
              v-for="mate in ship.partners.filter(p => p.deleted !== 0)"
              :key="`x-${mate.id}`"
              class="flex items-center gap-2 text-muted"
            >
              <img
                v-if="mate.image_url"
                :src="mate.image_url"
                alt=""
                class="size-10 rounded-full object-cover"
              />
              <span
                v-else
                class="flex size-10 items-center justify-center rounded-full bg-elevated text-xs"
                >?</span
              >
              {{ mate.name || '이름 없음' }}
            </span>
          </div>
        </li>
      </ul>
      <ul v-if="socials(sapphic).length" class="mt-3 list-disc pl-5 text-sm">
        <li v-for="item in socials(sapphic)" :key="item.url">
          <a
            class="underline"
            :href="item.url"
            target="_blank"
            rel="noreferrer"
            >{{ item.kind || item.url }}</a
          >
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
          <h2 class="text-sm font-semibold">GMMTV Wiki</h2>
          <p v-if="!fandom" class="mt-2 text-sm text-muted">
            선택한 위키 정보가 없습니다.
          </p>
          <p v-else class="mt-1 text-sm text-muted">
            출처
            <a
              v-if="httpUrl(fandom.payload.url)"
              class="font-medium text-default underline"
              :href="String(fandom.payload.url)"
              target="_blank"
              rel="noreferrer"
              >{{ fandom.display_name || fandom.external_key }}</a
            >
            · CC-BY-SA · {{ stamp(fandom.selected_at) }}
          </p>
        </div>
        <UButton
          v-if="gmmtv"
          color="neutral"
          variant="outline"
          @click="fandomOpen = true"
        >
          위키에서 고르기
        </UButton>
      </div>
      <div v-if="fandom" class="mt-4 flex gap-4">
        <img
          v-if="
            httpUrl(fandom.payload.image_url) ||
            payloadText(fandom, 'image_url')
          "
          :src="payloadText(fandom, 'image_url')"
          alt=""
          class="h-24 w-20 rounded-md object-cover"
        />
        <div>
          <dl class="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
            <div v-if="payloadText(fandom, 'birth_name')">
              <dt class="text-muted">본명</dt>
              <dd>{{ payloadText(fandom, 'birth_name') }}</dd>
            </div>
            <div v-if="payloadText(fandom, 'nickname')">
              <dt class="text-muted">닉네임</dt>
              <dd>{{ payloadText(fandom, 'nickname') }}</dd>
            </div>
            <div v-if="payloadText(fandom, 'native_name')">
              <dt class="text-muted">태국어 이름</dt>
              <dd>{{ payloadText(fandom, 'native_name') }}</dd>
            </div>
            <div v-if="payloadText(fandom, 'birthday')">
              <dt class="text-muted">생일</dt>
              <dd>{{ payloadText(fandom, 'birthday') }}</dd>
            </div>
            <div v-if="payloadText(fandom, 'birth_place')">
              <dt class="text-muted">출생지</dt>
              <dd>{{ payloadText(fandom, 'birth_place') }}</dd>
            </div>
            <div v-if="payloadText(fandom, 'height')">
              <dt class="text-muted">키</dt>
              <dd>{{ payloadText(fandom, 'height') }}</dd>
            </div>
            <div v-if="payloadText(fandom, 'weight')">
              <dt class="text-muted">몸무게</dt>
              <dd>{{ payloadText(fandom, 'weight') }}</dd>
            </div>
            <div v-if="payloadText(fandom, 'years_active')">
              <dt class="text-muted">활동</dt>
              <dd>{{ payloadText(fandom, 'years_active') }}</dd>
            </div>
          </dl>
          <ul v-if="socials(fandom).length" class="mt-3 list-disc pl-5 text-sm">
            <li v-for="item in socials(fandom)" :key="item.url">
              <a class="underline" :href="item.url" target="_blank" rel="noreferrer">{{
                item.kind || item.url
              }}</a>
            </li>
          </ul>
          <p
            v-if="payloadText(fandom, 'early_life')"
            class="mt-4 max-h-72 overflow-y-auto whitespace-pre-line text-sm leading-6"
          >
            {{ payloadText(fandom, 'early_life') }}
          </p>
        </div>
      </div>
    </section>

    <section class="mt-6 rounded-lg border border-default bg-default p-6">
      <div class="flex items-start justify-between gap-4">
        <div>
          <h2 class="text-sm font-semibold">위키</h2>
          <p v-if="!wiki" class="mt-2 text-sm text-muted">
            {{
              gmmtv
                ? 'GMMTV Wiki에 없는 항목만 고른다.'
                : '선택한 위키 정보가 없습니다.'
            }}
          </p>
          <p v-else class="mt-1 text-sm text-muted">
            출처
            <a
              v-if="httpUrl(wiki.payload.url)"
              class="font-medium text-default underline"
              :href="String(wiki.payload.url)"
              target="_blank"
              rel="noreferrer"
              >{{ wiki.display_name || wiki.external_key }}</a
            >
            · CC-BY-SA · {{ stamp(wiki.selected_at) }}
          </p>
        </div>
        <UButton color="neutral" variant="outline" @click="wikiOpen = true">
          위키에서 고르기
        </UButton>
      </div>
      <div v-if="wiki" class="mt-4 flex gap-4">
        <img
          v-if="
            httpUrl(wiki.payload.image_url) || payloadText(wiki, 'image_url')
          "
          :src="payloadText(wiki, 'image_url')"
          alt=""
          class="h-24 w-20 rounded-md object-cover"
        />
        <div class="min-w-0 flex-1">
          <dl class="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
            <div v-if="payloadText(wiki, 'birth_name')">
              <dt class="text-muted">본명</dt>
              <dd>{{ payloadText(wiki, 'birth_name') }}</dd>
            </div>
            <div v-if="payloadText(wiki, 'native_name')">
              <dt class="text-muted">원어 이름</dt>
              <dd>{{ payloadText(wiki, 'native_name') }}</dd>
            </div>
            <div v-if="payloadText(wiki, 'birthday')">
              <dt class="text-muted">생일</dt>
              <dd>{{ payloadText(wiki, 'birthday') }}</dd>
            </div>
            <div v-if="payloadText(wiki, 'birth_place')">
              <dt class="text-muted">출생지</dt>
              <dd>{{ payloadText(wiki, 'birth_place') }}</dd>
            </div>
            <div v-if="payloadText(wiki, 'height')">
              <dt class="text-muted">키</dt>
              <dd>{{ payloadText(wiki, 'height') }}</dd>
            </div>
            <div v-if="payloadText(wiki, 'education')">
              <dt class="text-muted">학력</dt>
              <dd>{{ payloadText(wiki, 'education') }}</dd>
            </div>
            <div v-if="payloadText(wiki, 'years_active')">
              <dt class="text-muted">활동 기간</dt>
              <dd>{{ payloadText(wiki, 'years_active') }}</dd>
            </div>
            <div v-if="agents(wiki).length" class="col-span-2">
              <dt class="text-muted">소속사</dt>
              <dd>
                <span v-for="(item, index) in agents(wiki)" :key="`${item.name}-${index}`">
                  {{ item.name
                  }}<template v-if="item.period_text">
                    {{ ' ' + item.period_text }}</template
                  ><template v-if="index < agents(wiki).length - 1">, </template>
                </span>
              </dd>
            </div>
          </dl>
          <template
            v-for="block in [
              ['career', 'Career'],
              ['fashion', 'Fashion'],
              ['ambassadorship', 'Ambassadorship'],
              ['accolades', 'Accolades']
            ]"
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
      </div>
    </section>

    <section
      class="mt-6 overflow-hidden rounded-lg border border-default bg-default"
    >
      <div
        class="flex items-center justify-between border-b border-default px-4 py-3"
      >
        <h2 class="text-sm font-semibold">출연작 {{ works.length }}</h2>
        <p class="text-xs text-muted">MyDramaList 인물 응답의 필모그래피</p>
      </div>
      <p v-if="!works.length" class="px-4 py-6 text-sm text-muted">
        출연작이 없습니다.
      </p>
      <UTable v-else :data="visibleWorks" :columns="columns">
        <template #image_url-cell="{ row }">
          <img
            v-if="row.original.image_url"
            :src="row.original.image_url"
            alt=""
            class="h-12 w-9 rounded object-cover"
          />
        </template>
        <template #title-cell="{ row }">
          <NuxtLink class="font-medium" :to="`/works/${row.original.id}`">
            {{ row.original.title }}
          </NuxtLink>
          <UBadge
            v-if="row.original.queer_name"
            :color="row.original.queer_name === 'BL' ? 'secondary' : 'primary'"
            :class="
              row.original.queer_name === 'GL' ? 'gl-badge ms-2' : 'ms-2'
            "
          >
            {{ row.original.queer_name }}
          </UBadge>
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
      <div v-if="works.length > PAGE_SIZE" class="flex justify-end px-4 py-3">
        <UPagination
          :page="page"
          :items-per-page="PAGE_SIZE"
          :total="works.length"
          show-edges
          @update:page="page = $event"
        />
      </div>
    </section>
    <UModal
      v-model:open="sapphicOpen"
      title="Sapphic Effect 검색"
      description="결과에서 넣을 항목만 고르면 이 배우 상세에 저장된다. MDL 값은 바꾸지 않는다."
      :ui="{ content: 'max-w-3xl' }"
    >
      <template #body>
        <Suspense>
          <SapphicPick
            v-if="sapphicOpen"
            :person-id="String(person.id)"
            :query="sapphicQuery"
            @saved="onSourceSaved('sapphic')"
          />
          <template #fallback>
            <p class="text-sm text-muted">검색 중</p>
          </template>
        </Suspense>
      </template>
    </UModal>
    <UModal
      v-model:open="fandomOpen"
      title="GMMTV Wiki 검색"
      :ui="{ content: 'max-w-3xl' }"
    >
      <template #body>
        <Suspense>
          <FandomPick
            v-if="fandomOpen"
            :person-id="String(person.id)"
            :query="fandomQuery"
            @saved="onSourceSaved('fandom')"
          />
          <template #fallback>
            <p class="text-sm text-muted">검색 중</p>
          </template>
        </Suspense>
      </template>
    </UModal>
    <UModal
      v-model:open="wikiOpen"
      title="위키 검색"
      :ui="{ content: 'max-w-3xl' }"
    >
      <template #body>
        <Suspense>
          <WikiPick
            v-if="wikiOpen"
            :person-id="String(person.id)"
            :query="wikiQuery"
            @saved="onSourceSaved('wiki')"
          />
          <template #fallback>
            <p class="text-sm text-muted">검색 중</p>
          </template>
        </Suspense>
      </template>
    </UModal>
  </div>
</template>
