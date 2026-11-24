<script setup lang="ts">
useHead({
  meta: [
    { name: 'viewport', content: 'width=device-width, initial-scale=1' }
  ],
  link: [
    { rel: 'icon', href: '/favicon.ico' }
  ],
  htmlAttrs: {
    lang: 'ko'
  }
})
</script>

<template>
  <UApp>
    <UHeader>
      <template #left>
        <NuxtLink
          to="/people"
          class="text-lg font-semibold"
        >
          Glow
        </NuxtLink>
      </template>

      <template #right>
        <nav class="flex gap-1">
          <UButton
            to="/register"
            color="neutral"
            variant="ghost"
          >
            배우 등록
          </UButton>
          <UButton
            to="/people"
            color="neutral"
            variant="ghost"
          >
            배우
          </UButton>
          <UButton
            to="/works"
            color="neutral"
            variant="ghost"
          >
            작품
          </UButton>
          <UButton
            to="/credits"
            color="neutral"
            variant="ghost"
          >
            작가·감독
          </UButton>
          <UButton
            to="/companies"
            color="neutral"
            variant="ghost"
          >
            종합 콘텐츠 스튜디오
          </UButton>
        </nav>
      </template>
    </UHeader>

    <UMain>
      <div class="mx-auto max-w-5xl px-4 py-8">
        <NuxtPage />
      </div>
    </UMain>
  </UApp>
</template>
