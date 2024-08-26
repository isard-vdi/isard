<script setup lang="ts">
import { computed, type ComputedRef } from 'vue'
import { Button } from '@/components/ui/button'
import { Provider } from '@/components/login'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

interface Props {
  provider: Provider
  icon?: string
  text?: string
}

const defaultText: Record<Provider, ComputedRef<String>> = {
  [Provider.SAML]: computed(() => t('components.login.login-provider-external.default-text.saml')),
  [Provider.Google]: computed(() =>
    t('components.login.login-provider-external.default-text.google')
  )
}

const defaultIcon: Record<Provider, string | undefined> = {
  [Provider.SAML]: undefined,
  [Provider.Google]: 'google'
}

const onClick = () => {
  emit('submit', props.provider)
}

const props = defineProps<Props>()
const emit = defineEmits<{
  submit: [provider: Provider]
}>()

const text = computed(() => props.text || defaultText[props.provider])
const icon = computed(() => props.icon || defaultIcon[props.provider])
</script>

<template>
  <Button class="w-full" hierarchy="secondary-gray" size="lg" :icon="icon" @click="onClick">{{
    text
  }}</Button>
</template>
