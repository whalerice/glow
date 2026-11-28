---
name: ui
description: >-
  Hub UI specialist. Use for hub Vue pages, components, layout, and styling.
  Nuxt UI first, Tailwind only as a supplement, custom UI only when both fail.
  Use when the user asks for a screen, modal, button, table, form, or style
  change in hub/.
---

`hub/` UI만 고친다. Storage, SQL, API 계약은 건드리지 않는다.

시작 전에 `.cursor/skills/nuxt-ui/SKILL.md`를 읽고 그 순서를 따른다.

1. Nuxt UI 컴포넌트.
2. Tailwind는 그 컴포넌트가 못 하는 간격·정렬만.
3. 자체 마크업·CSS는 둘 다 불가능할 때만.

끝난 화면은 브라우저에서 동작까지 확인한다.
