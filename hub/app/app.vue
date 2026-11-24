<script setup lang="ts">
const items = [
  {
    label: '수집',
    defaultOpen: true,
    children: [
      { label: '배우', to: '/people' },
      { label: '작품', to: '/works' },
      { label: '작가·감독', to: '/credits' },
      { label: '종합 콘텐츠 스튜디오', to: '/companies' }
    ]
  }
]

useHead({
  meta: [{ name: 'viewport', content: 'width=device-width, initial-scale=1' }],
  link: [{ rel: 'icon', href: '/favicon.ico' }],
  htmlAttrs: {
    lang: 'ko'
  }
})

const route = useRoute()
const main = ref<HTMLElement | null>(null)

watch(
  () => route.path,
  () => {
    nextTick(() => main.value?.parentElement?.scrollTo(0, 0))
  }
)
</script>

<template>
  <UApp>
    <UDashboardGroup unit="rem" :persistent="false">
      <UDashboardSidebar :default-size="16" :min-size="14" :max-size="20">
        <template #header>
          <NuxtLink to="/people" class="text-lg font-semibold"> Glow </NuxtLink>
        </template>

        <UNavigationMenu orientation="vertical" :items="items" />
      </UDashboardSidebar>

      <UDashboardPanel>
        <template #body>
          <div ref="main" class="px-4 py-8">
            <NuxtLayout>
              <NuxtPage />
            </NuxtLayout>
          </div>
        </template>
      </UDashboardPanel>
    </UDashboardGroup>
  </UApp>
</template>
