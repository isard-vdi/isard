<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import LogoSvg from '@/assets/logo.svg?url'
import LogoCollapsedSvg from '@/assets/logo-collapsed.svg?url'

interface Props {
  variant?: 'full' | 'collapsed'
  categoryId?: string
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'full',
  categoryId: undefined
})

const failed = ref(false)

// The API falls back to the default logo on its own; the bundled asset only
// covers the endpoint being unreachable (or 404 on the collapsed variant).
const src = computed(() => {
  if (failed.value) return props.variant === 'collapsed' ? LogoCollapsedSvg : LogoSvg
  const base = props.variant === 'collapsed' ? '/api/v4/logo-collapsed' : '/api/v4/logo'
  return props.categoryId ? `${base}/category/${props.categoryId}` : base
})

watch(
  () => [props.variant, props.categoryId],
  () => (failed.value = false)
)
</script>

<template>
  <img :src="src" alt="IsardVDI logo" @error="failed = true" />
</template>
