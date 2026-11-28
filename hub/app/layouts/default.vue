<script setup lang="ts">
import type { NavigationMenuItem } from '@nuxt/ui'

const route = useRoute()
const router = useRouter()
const open = ref(false)
const main = ref<HTMLElement | null>(null)

function shut() {
  open.value = false
}

const links = [
  [
    {
      label: '배우',
      icon: 'i-lucide-users',
      to: '/people',
      onSelect: shut
    },
    {
      label: '작품',
      icon: 'i-lucide-clapperboard',
      to: '/works',
      onSelect: shut
    },
    {
      label: '작가·감독',
      icon: 'i-lucide-pen-line',
      to: '/credits',
      onSelect: shut
    },
    {
      label: '종합 콘텐츠 스튜디오',
      icon: 'i-lucide-building-2',
      to: '/companies',
      onSelect: shut
    }
  ]
] satisfies NavigationMenuItem[][]

const detail = computed(() => route.path.split('/').filter(Boolean).length >= 2)

const title = computed(() => {
  const path = route.path
  if (path.includes('/fandom')) return '팬덤'
  if (path.includes('/wiki')) return '위키'
  if (path.includes('/sapphic')) return 'Sapphic'
  if (path.startsWith('/people')) return '배우'
  if (path.startsWith('/works')) return '작품'
  if (path.startsWith('/credits')) return '작가·감독'
  if (path.startsWith('/companies')) return '종합 콘텐츠 스튜디오'
  return 'Glow'
})

function back() {
  const previous = router.options.history.state.back
  if (typeof previous === 'string') {
    router.back()
    return
  }
  const section = route.path.split('/').filter(Boolean)[0]
  navigateTo(section ? `/${section}` : '/')
}

watch(
  () => route.path,
  () => {
    nextTick(() => {
      const forward = router.options.history.state.forward
      if (
        (route.path === '/works' ||
          route.path === '/people' ||
          route.path === '/credits' ||
          route.path === '/companies') &&
        typeof forward === 'string' &&
        forward.startsWith(`${route.path}/`)
      ) {
        return
      }
      main.value?.parentElement?.scrollTo(0, 0)
    })
  }
)
</script>

<template>
  <UDashboardGroup unit="rem">
    <UDashboardSidebar
      id="default"
      v-model:open="open"
      collapsible
      resizable
      class="bg-elevated/25"
      :default-size="18"
      :min-size="16"
      :max-size="24"
    >
      <template #header="{ collapsed }">
        <NuxtLink
          to="/people"
          class="flex items-center gap-1.5 px-1.5 py-1 font-semibold text-highlighted"
          :class="collapsed && 'justify-center px-0'"
        >
          <UIcon
            name="i-lucide-sparkles"
            class="size-5 shrink-0 text-primary"
          />
          <span v-if="!collapsed">Glow</span>
        </NuxtLink>
      </template>

      <template #default="{ collapsed }">
        <UNavigationMenu
          :collapsed="collapsed"
          :items="links[0]"
          orientation="vertical"
          tooltip
        />
      </template>
    </UDashboardSidebar>

    <UDashboardPanel id="hub">
      <template #header>
        <UDashboardNavbar :title="title">
          <template #leading>
            <UDashboardSidebarCollapse />
            <UButton
              v-if="detail"
              color="neutral"
              variant="ghost"
              icon="i-lucide-arrow-left"
              @click="back"
            >
              뒤로
            </UButton>
          </template>
          <template #right>
            <UColorModeButton />
          </template>
        </UDashboardNavbar>
      </template>

      <template #body>
        <div ref="main">
          <slot />
        </div>
      </template>
    </UDashboardPanel>
  </UDashboardGroup>
</template>
