<script setup lang="ts">
type Profile = {
  title: string
  name: string
  url: string
  image_url?: string
  birth_name?: string
  nickname?: string
  native_name?: string
  birthday?: string
  birth_place?: string
  height?: string
  weight?: string
  years_active?: string
  socials?: unknown[]
  early_life?: string
}

type SearchBody = {
  query: string
  blocked: boolean
  message: string
  profiles: Profile[]
}

const route = useRoute()
const id = computed(() => routeId(route.params.id))
const q = computed(() => typeof route.query.q === 'string' ? route.query.q : '')
const draft = ref(q.value)
const saveError = ref('')
const { data, error } = await storageFetch<SearchBody>(
  () => `/api/people/${id.value}/fandom?q=${encodeURIComponent(q.value)}`
)

watch(data, (value) => {
  draft.value = value?.query ?? q.value
}, { immediate: true })

const labels: [keyof Profile, string][] = [
  ['birth_name', '본명'],
  ['nickname', '닉네임'],
  ['native_name', '태국어 이름'],
  ['birthday', '생일'],
  ['birth_place', '출생지'],
  ['height', '키'],
  ['weight', '몸무게'],
  ['years_active', '활동']
]

function checks(profile: Profile) {
  const items: { key: string, label: string }[] = []
  for (const [key, label] of labels) {
    if (profile[key]) items.push({ key, label: `${label} ${profile[key]}` })
  }
  if (profile.image_url) items.push({ key: 'image', label: '프로필 이미지' })
  if (profile.socials?.length) items.push({ key: 'socials', label: `SNS ${profile.socials.length}개` })
  if (profile.early_life) items.push({ key: 'early_life', label: 'Early Life' })
  return items
}

async function search() {
  await navigateTo({ path: route.path, query: { q: draft.value } })
}

async function save(profile: Profile, event: Event) {
  saveError.value = ''
  const fields = [...new FormData(event.target as HTMLFormElement).getAll('fields')].map(String)
  try {
    await $fetch(`/api/people/${id.value}/fandom`, {
      method: 'POST',
      body: { title: profile.title, fields }
    })
    await navigateTo(`/people/${id.value}`)
  } catch (err) {
    saveError.value = errorText(err)
  }
}
</script>

<template>
  <div>
    <NuxtLink
      :to="`/people/${id}`"
      class="text-sm text-muted"
    >
      배우
    </NuxtLink>
    <section class="mt-3 rounded-lg border border-default bg-default p-6">
      <h1 class="text-xl font-semibold">
        GMMTV Wiki 검색
      </h1>
      <p
        v-if="data?.blocked"
        class="mt-2 text-sm text-muted"
      >
        {{ data.message }}
      </p>
      <template v-else>
        <p class="mt-2 text-sm text-muted">
          고른 항목만 이 배우의 GMMTV Wiki 출처로 저장한다.
        </p>
        <form
          class="mt-4 flex gap-2"
          @submit.prevent="search"
        >
          <UInput
            v-model="draft"
            class="w-full"
          />
          <UButton type="submit">
            검색
          </UButton>
        </form>
        <p
          v-if="data?.message && !error && !saveError"
          class="mt-4 text-sm text-muted"
        >
          {{ data.message }}
        </p>
        <UAlert
          v-if="error || saveError"
          color="error"
          variant="subtle"
          class="mt-4"
          :title="saveError || errorText(error)"
        />
      </template>
    </section>
    <div
      v-if="!data?.blocked"
      class="mt-4 space-y-4"
    >
      <form
        v-for="profile in data?.profiles || []"
        :key="profile.title"
        class="rounded-lg border border-default bg-default p-5"
        @submit.prevent="save(profile, $event)"
      >
        <h2 class="text-lg font-semibold">
          {{ profile.name }}
        </h2>
        <a
          class="text-sm text-muted underline"
          :href="profile.url"
          target="_blank"
          rel="noreferrer"
        >{{ profile.title }}</a>
        <img
          v-if="profile.image_url"
          :src="profile.image_url"
          alt=""
          class="mt-3 h-24 w-20 rounded-md object-cover"
        >
        <div class="mt-3 space-y-2">
          <label
            v-for="item in checks(profile)"
            :key="item.key"
            class="flex items-center gap-2 text-sm"
          >
            <input
              type="checkbox"
              name="fields"
              :value="item.key"
              checked
            >
            {{ item.label }}
          </label>
        </div>
        <p
          v-if="profile.early_life"
          class="mt-4 max-h-72 overflow-y-auto whitespace-pre-line text-sm leading-6"
        >
          {{ profile.early_life }}
        </p>
        <UButton
          type="submit"
          class="mt-4"
        >
          이 정보 넣기
        </UButton>
      </form>
    </div>
  </div>
</template>
