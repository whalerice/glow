<script setup lang="ts">
import type { SortState } from '~/utils/table'

const props = defineProps<{
  label: string
  id: string
  active: SortState | null
}>()

const emit = defineEmits<{ sort: [id: string] }>()

const icon = computed(() => {
  if (props.active?.id !== props.id) return undefined
  return props.active.desc ? 'i-lucide-arrow-down' : 'i-lucide-arrow-up'
})
</script>

<template>
  <UButton
    color="neutral"
    variant="ghost"
    :label="label"
    :icon="icon"
    class="-mx-2.5"
    @click="emit('sort', id)"
  />
</template>
