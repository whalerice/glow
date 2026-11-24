<script setup lang="ts">
type Profile = {
  slug: string
  name: string
  url: string
  birthday?: string
  image_url?: string
  company?: { name?: string }
  ships?: unknown[]
  socials?: unknown[]
  biography?: string
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
  () => `/api/people/${id.value}/sapphic?q=${encodeURIComponent(q.value)}`
)

watch(data, (value) => {
  draft.value = value?.query ?? q.value
}, { immediate: true })

function checks(profile: Profile) {
  const items: { key: string, label: string }[] = []
  if (profile.birthday) items.push({ key: 'birthday', label: `생일 ${profile.birthday}` })
  if (profile.image_url) items.push({ key: 'image', label: '프로필 이미지' })
  if (profile.company?.name) items.push({ key: 'company', label: `소속사 ${profile.company.name}` })
  if (profile.ships?.length) items.push({ key: 'ships', label: `Ship ${profile.ships.length}개` })
  if (profile.socials?.length) items.push({ key: 'socials', label: `SNS ${profile.socials.length}개` })
  if (profile.biography) items.push({ key: 'biography', label: 'Biography' })
  return items
}

async function search() {
  await navigateTo({ path: route.path, query: { q: draft.value } })
}

async function save(profile: Profile, event: Event) {
  saveError.value = ''
  const fields = [...new FormData(event.target as HTMLFormElement).getAll('fields')].map(String)
  try {
    await $fetch(`/api/people/${id.value}/sapphic`, {
      method: 'POST',
      body: { slug: profile.slug, fields }
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
        Sapphic Effect 검색
      </h1>
      <p class="mt-2 text-sm text-muted">
        결과에서 넣을 항목만 고르면 이 배우 상세에 저장된다. MDL 값은 바꾸지 않는다.
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
    </section>
    <div class="mt-4 space-y-4">
      <form
        v-for="profile in data?.profiles || []"
        :key="profile.slug"
        class="rounded-lg border border-default bg-default p-5"
        @submit.prevent="save(profile, $event)"
      >
        <div class="flex gap-4">
          <img
            v-if="profile.image_url"
            :src="profile.image_url"
            alt=""
            class="h-20 w-16 rounded-md object-cover"
          >
          <div>
            <h2 class="text-lg font-semibold">
              {{ profile.name }}
            </h2>
            <a
              class="text-sm text-muted underline"
              :href="profile.url"
            >{{ profile.slug }}</a>
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
              v-if="profile.biography"
              class="mt-4 max-h-72 overflow-y-auto whitespace-pre-line text-sm leading-6"
            >
              {{ profile.biography }}
            </p>
            <UButton
              type="submit"
              class="mt-4"
            >
              이 정보 넣기
            </UButton>
          </div>
        </div>
      </form>
    </div>
  </div>
</template>
