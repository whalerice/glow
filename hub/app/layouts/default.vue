<script setup lang="ts">
const route = useRoute()
const router = useRouter()

const detail = computed(() => route.path.split('/').filter(Boolean).length >= 2)

function back() {
  const previous = router.options.history.state.back
  if (typeof previous === 'string') {
    router.back()
    return
  }
  const parts = route.path.split('/').filter(Boolean)
  parts.pop()
  navigateTo(`/${parts.join('/')}`)
}
</script>

<template>
  <div>
    <UButton
      v-if="detail"
      color="neutral"
      variant="ghost"
      icon="i-lucide-arrow-left"
      class="mb-4"
      @click="back"
    >
      뒤로
    </UButton>
    <slot />
  </div>
</template>
