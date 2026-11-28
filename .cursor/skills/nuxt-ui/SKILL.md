---
name: nuxt-ui
description: >-
  Builds Glow hub UI with Nuxt UI first and Tailwind CSS only as a supplement.
  Custom markup or CSS only when neither can do the job. Use when editing hub
  Vue, layout, styling, modals, tables, forms, or when the user mentions Nuxt
  UI, Tailwind, UI, 화면, 모달, 버튼, 스타일.
---

# Hub UI

기본값이 Nuxt UI 사용. Tailwind CSS는 보조. Nuxt UI와 Tailwind CSS로 해결이 안될 경우만 자체적으로 만든다.

대상: `hub/` Vue, CSS, `nuxt.config.ts`의 `ui` / `icon`. Storage·API는 이 스킬 밖.

## 순서

1. `@nuxt/ui` 컴포넌트. 이미 쓰는 것: `UApp`, `UDashboardGroup`, `UDashboardSidebar`, `UDashboardPanel`, `UDashboardNavbar`, `UNavigationMenu`, `UColorModeButton`, `UButton`, `UInput`, `USelect`, `UCheckbox`, `UTable`, `UModal`, `UAlert`, `UBadge`, `UPagination`, `UIcon`, `UCarousel`. prop, slot, `color`, `variant`, `size`로 맞춘다.
2. 컴포넌트가 간격·정렬만 못 하면 Tailwind 유틸. 컴포넌트 `class`에 붙인다. 감싸는 `div`는 그 클래스로도 안 될 때만.
3. 1과 2가 불가능할 때만 마크업이나 CSS. 한 화면이면 그 Vue에 둔다. `hub/app/assets/css/main.css`에 클래스를 추가하지 않는다. 색·둥글기는 `--ui-*` 토큰으로 이미 있다.

자체 구현 전에 막힌 컴포넌트와 이유를 한 줄로 남긴다.

## 제약

- `nuxt.config.ts`의 UI ESLint: `no-unknown-classes`, `no-conflicting-classes`, `no-palette-colors`가 error. `text-red-500`, `bg-blue-400` 같은 팔레트 유틸 금지. 색은 Nuxt UI `color` 또는 `text-muted`, `bg-elevated` 같은 시맨틱 토큰.
- 새 `i-lucide-*`는 `nuxt.config.ts` `icon.clientBundle.icons`에 같은 문자열을 추가한다.
- 폰트는 `Roboto`, `Pretendard`. `ui.fonts`는 false.
- 화면이 바뀌면 브라우저에서 그 흐름을 눌러 확인한다.
