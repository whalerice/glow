<script setup lang="ts">
const mdlId = ref('')
const message = ref('')
const pending = ref(false)

async function submit() {
  message.value = ''
  pending.value = true
  try {
    const result = await $fetch<{ person_id: number }>('/api/people', {
      method: 'POST',
      body: { mdl_id: mdlId.value }
    })
    await navigateTo(`/people/${result.person_id}`)
  } catch (error) {
    message.value = errorText(error)
  } finally {
    pending.value = false
  }
}
</script>

<template>
  <section class="rounded-lg border border-default bg-default p-6">
    <h1 class="text-xl font-semibold">
      배우 등록
    </h1>
    <p class="mt-2 text-sm text-muted">
      MyDramaList 숫자 id
    </p>
    <UAlert
      v-if="message"
      color="error"
      variant="subtle"
      :title="message"
      class="mt-4"
    />
    <form
      class="mt-4 flex gap-2"
      @submit.prevent="submit"
    >
      <UInput
        v-model="mdlId"
        name="mdl_id"
        class="w-full"
        placeholder="70935"
      />
      <UButton
        type="submit"
        :loading="pending"
      >
        저장
      </UButton>
    </form>
  </section>
</template>
