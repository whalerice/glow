<script setup lang="ts">
type Agent = { name: string, period_text?: string }
type Profile = {
  title: string
  name: string
  url: string
  language?: string
  image_url?: string
  birth_name?: string
  native_name?: string
  birthday?: string
  birth_place?: string
  height?: string
  education?: string
  years_active?: string
  agent?: Agent[]
  career?: string
  fashion?: string
  ambassadorship?: string
  accolades?: string
}

type SearchBody = {
  query: string
  message: string
  hint: string
  allowed: string[]
  profiles: Profile[]
}

const fields: { key: keyof Profile, label: string }[] = [
  { key: 'image_url', label: '프로필 이미지' },
  { key: 'birth_name', label: '본명' },
  { key: 'native_name', label: '원어 이름' },
  { key: 'birthday', label: '생일' },
  { key: 'birth_place', label: '출생지' },
  { key: 'height', label: '키' },
  { key: 'education', label: '학력' },
  { key: 'years_active', label: '활동 기간' },
  { key: 'agent', label: '소속사' },
  { key: 'career', label: 'Career' },
  { key: 'fashion', label: 'Fashion' },
  { key: 'ambassadorship', label: 'Ambassadorship' },
  { key: 'accolades', label: 'Accolades' }
]

const fieldKey: Record<string, string> = { image_url: 'image' }

const route = useRoute()
const id = computed(() => routeId(route.params.id))
const q = computed(() => typeof route.query.q === 'string' ? route.query.q : '')
const draft = ref(q.value)
const saveError = ref('')
const { data, error } = await storageFetch<SearchBody>(
  () => `/api/people/${id.value}/wiki?q=${encodeURIComponent(q.value)}`
)

watch(data, (value) => {
  draft.value = value?.query ?? q.value
}, { immediate: true })

function checks(profile: Profile, allowed: string[]) {
  return fields.flatMap((field) => {
    const key = fieldKey[field.key] || field.key
    if (!allowed.includes(key)) return []
    const value = profile[field.key]
    if (!value || (Array.isArray(value) && !value.length)) return []
    if (field.key === 'agent' && Array.isArray(value)) {
      const label = '소속사 ' + value.map(item => item.name + (item.period_text ? ` ${item.period_text}` : '')).join(', ')
      return [{ key, label }]
    }
    if (field.key === 'image_url' || ['career', 'fashion', 'ambassadorship', 'accolades'].includes(field.key)) {
      return [{ key, label: field.label }]
    }
    return [{ key, label: `${field.label} ${value}` }]
  })
}

async function search() {
  await navigateTo({ path: route.path, query: { q: draft.value } })
}

async function save(profile: Profile, event: Event) {
  saveError.value = ''
  const fieldsPicked = [...new FormData(event.target as HTMLFormElement).getAll('fields')].map(String)
  try {
    await $fetch(`/api/people/${id.value}/wiki`, {
      method: 'POST',
      body: { title: profile.title, lang: profile.language || 'en', fields: fieldsPicked }
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
        위키 검색
      </h1>
      <p class="mt-2 text-sm text-muted">
        {{ data?.hint }}
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
        :key="`${profile.language}-${profile.title}`"
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
            v-for="item in checks(profile, data?.allowed || [])"
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
          <p
            v-if="!checks(profile, data?.allowed || []).length"
            class="text-sm text-muted"
          >
            가져올 항목이 없습니다.
          </p>
        </div>
        <p
          v-if="profile.career && (data?.allowed || []).includes('career')"
          class="mt-4 max-h-72 overflow-y-auto whitespace-pre-line text-sm leading-6"
        >
          {{ profile.career }}
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
