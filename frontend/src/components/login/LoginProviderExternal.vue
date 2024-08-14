<script setup lang="ts">
import { computed } from 'vue'
import { Button } from '@/components/ui/button'
import { Provider } from '@/components/login'

interface Props {
  provider: Provider
  icon?: string
  text?: string
}

const defaultText: Record<Provider, string> = {
  [Provider.SAML]: 'Iniciar sessió amb SAML',
  [Provider.Google]: 'Iniciar sessió amb Google'
}

const defaultIcon: Record<Provider, string | undefined> = {
  [Provider.SAML]: undefined,
  [Provider.Google]: 'google'
}

const props = defineProps<Props>()
const text = computed(() => props.text || defaultText[props.provider])
const icon = computed(() => props.icon || defaultIcon[props.provider])
</script>

<template>
  <Button class="w-full" hierarchy="secondary-gray" size="lg" :icon="icon">{{ text }}</Button>
</template>
