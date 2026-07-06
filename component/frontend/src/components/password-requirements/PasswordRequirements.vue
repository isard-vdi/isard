<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { cva } from 'class-variance-authority'
import Icon from '@/components/icon/Icon.vue'
import { Separator } from '../ui/separator'
import { type GetUserPasswordPolicyResponse } from '@/gen/oas/apiv4'
import { PASSWORD_REGEX } from '@/lib/password'
import type { HTMLAttributes } from 'vue'
import { cn } from '@/lib/utils'

interface Props {
  inputPassword: string
  policies: GetUserPasswordPolicyResponse
  showErrors?: boolean
  class?: HTMLAttributes['class']
}

const props = withDefaults(defineProps<Props>(), {
  showErrors: false
})

// Per-item visual state. A satisfied item is always green; an unmet one only
// turns red once the parent asks for it (showErrors), otherwise stays neutral.
type PolicyItemState = 'pending' | 'satisfied' | 'error'

const policyItemVariants = cva('flex items-center gap-2 transition-colors duration-200', {
  variants: {
    state: {
      pending: 'text-gray-warm-600 bg-gray-warm-100',
      satisfied: 'text-success-900 bg-success-50',
      error: 'text-error-900 bg-error-50'
    }
  },
  defaultVariants: {
    state: 'pending'
  }
})

const STATE_ICON = {
  pending: { name: 'circle', stroke: 'gray-warm-500' },
  satisfied: { name: 'check', stroke: 'success-800' },
  error: { name: 'x-circle', stroke: 'error-600' }
}

const { t } = useI18n()

interface PolicyRequirement {
  text: string
  satisfied: boolean
}

// Requirements that can be verified live against the typed password: they turn
// green (check) as soon as the input meets them.
const passwordRequirements = computed<PolicyRequirement[]>(() => {
  if (!props.policies) return []
  const p = props.policies
  const val = props.inputPassword ?? ''
  const items: PolicyRequirement[] = []
  if (p.length > 0)
    items.push({
      text: t('views.reset-password.policy.length', { num: p.length }),
      satisfied: val.length >= p.length
    })
  if (p.uppercase > 0)
    items.push({
      text: t('views.reset-password.policy.uppercase', { num: p.uppercase }),
      satisfied: (val.match(PASSWORD_REGEX.UPPERCASE)?.length ?? 0) >= p.uppercase
    })
  if (p.lowercase > 0)
    items.push({
      text: t('views.reset-password.policy.lowercase', { num: p.lowercase }),
      satisfied: (val.match(PASSWORD_REGEX.LOWERCASE)?.length ?? 0) >= p.lowercase
    })
  if (p.digits > 0)
    items.push({
      text: t('views.reset-password.policy.digits', { num: p.digits }),
      satisfied: (val.match(PASSWORD_REGEX.DIGITS)?.length ?? 0) >= p.digits
    })
  if (p.special_characters > 0)
    items.push({
      text: t('views.reset-password.policy.special_characters', { num: p.special_characters }),
      satisfied: (val.match(PASSWORD_REGEX.SPECIAL)?.length ?? 0) >= p.special_characters
    })
  return items
})

// View rows for the live checklist: each requirement resolved to its current
// visual state (and matching icon), so the template stays declarative.
const requirementRows = computed(() =>
  passwordRequirements.value.map((item) => {
    const state: PolicyItemState = item.satisfied
      ? 'satisfied'
      : props.showErrors
        ? 'error'
        : 'pending'
    return { text: item.text, state, icon: STATE_ICON[state] }
  })
)

// Informational policies that can't be verified client-side (no username here,
// server-side history check, expiration days). Shown as static text, never checked.
const infoPolicyItems = computed<string[]>(() => {
  if (!props.policies) return []
  const p = props.policies
  const items: string[] = []
  if (p.not_username) items.push(t('views.reset-password.policy.not_username'))
  if (p.old_passwords > 0)
    items.push(t('views.reset-password.policy.old_passwords', { num: p.old_passwords }))
  if (p.expiration > 0)
    items.push(t('views.reset-password.policy.expiration', { num: p.expiration }))
  return items
})
</script>

<template>
  <div
    v-if="passwordRequirements.length > 0 || infoPolicyItems.length > 0"
    id="password-requirements"
    :class="cn(props.class)"
    class="w-full rounded-xl border border-gray-warm-300 bg-base-white p-4 text-sm text-foreground shadow-xs [&_p]:leading-relaxed"
  >
    <h2 class="sr-only">{{ t('views.reset-password.policy.aria-label') }}</h2>
    <ul v-if="requirementRows.length > 0" class="flex flex-col gap-2 list-none" aria-live="polite">
      <li v-for="row in requirementRows" :key="row.text" aria-atomic="true">
        <div :class="`${policyItemVariants({ state: row.state })} p-1 pl-2 rounded-sm`">
          <Icon
            :name="row.icon.name"
            size="xs"
            :stroke-color="row.icon.stroke"
            class="[&_path]:stroke-3"
            aria-hidden="true"
          />
          <span>{{ row.text }}</span>
          <span class="sr-only">{{
            row.state === 'satisfied'
              ? t('views.reset-password.policy.state.met')
              : t('views.reset-password.policy.state.unmet')
          }}</span>
        </div>
      </li>
    </ul>
    <!-- Only divide the two sections when BOTH are present -->
    <Separator
      v-if="passwordRequirements.length > 0 && infoPolicyItems.length > 0"
      class="my-3.5"
    />
    <!-- Static informational policies that can't be verified client-side -->
    <template v-if="infoPolicyItems.length > 0">
      <p class="mb-2 font-medium text-gray-warm-700">
        {{ t('views.reset-password.policy.info-heading') }}
      </p>
      <ul class="flex flex-col gap-3 list-none text-gray-warm-700">
        <li v-for="item in infoPolicyItems" :key="item">
          <div class="flex items-center gap-2">
            <Icon name="dot" size="xs" stroke-color="gray-warm-700" aria-hidden="true" />
            <span>{{ item }}</span>
          </div>
        </li>
      </ul>
    </template>
  </div>
</template>
