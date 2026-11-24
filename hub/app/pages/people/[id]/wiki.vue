<script setup lang="ts">
const route = useRoute()
const id = computed(() => routeId(route.params.id))
const q = computed(() =>
  typeof route.query.q === 'string' ? route.query.q : ''
)
</script>

<template>
  <WikiPick :person-id="id" :query="q" @saved="navigateTo(`/people/${id}`)" />
</template>
