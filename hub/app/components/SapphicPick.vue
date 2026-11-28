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

const props = defineProps<{
  personId: string | number
  query: string
}>()

const emit = defineEmits<{ saved: [] }>()

const draft = ref(props.query)
const q = ref(props.query)
const saveError = ref('')
const saving = ref('')

const { data, error, pending } = await storageFetch<SearchBody>(
  () => `/api/people/${props.personId}/sapphic?q=${encodeURIComponent(q.value)}`
)

watch(
  data,
  value => {
    draft.value = value?.query ?? q.value
  },
  { immediate: true }
)

function checks(profile: Profile) {
  const items: { key: string; label: string }[] = []
  if (profile.birthday)
    items.push({ key: 'birthday', label: `생일 ${profile.birthday}` })
  if (profile.image_url) items.push({ key: 'image', label: '프로필 이미지' })
  if (profile.company?.name)
    items.push({ key: 'company', label: `소속사 ${profile.company.name}` })
  if (profile.ships?.length)
    items.push({ key: 'ships', label: `Ship ${profile.ships.length}개` })
  if (profile.socials?.length)
    items.push({ key: 'socials', label: `SNS ${profile.socials.length}개` })
  if (profile.biography) items.push({ key: 'biography', label: 'Biography' })
  return items
}

async function search() {
  q.value = draft.value
}

async function save(profile: Profile, event: Event) {
  saveError.value = ''
  saving.value = profile.slug
  const fields = [
    ...new FormData(event.target as HTMLFormElement).getAll('fields')
  ].map(String)
  try {
    await $fetch(`/api/people/${props.personId}/sapphic`, {
      method: 'POST',
      body: { slug: profile.slug, fields }
    })
    emit('saved')
  } catch (err) {
    saveError.value = errorText(err)
  } finally {
    saving.value = ''
  }
}
</script>

<template>
  <div>
    <form class="flex gap-2" @submit.prevent="search">
      <UInput v-model="draft" class="w-full" />
      <UButton type="submit" :loading="pending && !saving">검색</UButton>
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
    <div class="mt-4 space-y-4">
      <form
        v-for="profile in data?.profiles || []"
        :key="profile.slug"
        class="rounded-lg border border-default p-4"
        @submit.prevent="save(profile, $event)"
      >
        <div class="flex gap-4">
          <img
            v-if="profile.image_url"
            :src="profile.image_url"
            alt=""
            class="h-20 w-16 rounded-md object-cover"
          />
          <div class="min-w-0 flex-1">
            <h2 class="text-lg font-semibold">{{ profile.name }}</h2>
            <a
              class="text-sm text-muted underline"
              :href="profile.url"
              target="_blank"
              >{{ profile.slug }}</a
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
                />
                {{ item.label }}
              </label>
            </div>
            <p
              v-if="profile.biography"
              class="mt-4 max-h-40 overflow-y-auto whitespace-pre-line text-sm leading-6"
            >
              {{ profile.biography }}
            </p>
            <UButton
              type="submit"
              class="mt-4"
              :loading="saving === profile.slug"
            >
              이 정보 넣기
            </UButton>
          </div>
        </div>
      </form>
    </div>
  </div>
</template>
