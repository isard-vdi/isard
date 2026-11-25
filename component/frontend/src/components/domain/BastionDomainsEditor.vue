<script setup lang="ts">
import { computed, reactive, ref, useId } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMutation } from '@tanstack/vue-query'

import { verifyDesktopBastionDomainMutation } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Code } from '@/components/code'
import { CopyIcon, Icon } from '@/components/icon'
import { FeaturedIconOutline } from '@/components/icon/featured-outline'
import { FieldError } from '@/components/ui/field'
import { InputGroup, InputGroupAddon, InputGroupInput } from '@/components/ui/input-group'
import { Label } from '@/components/ui/label'
import { Spinner } from '@/components/ui/spinner'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { describeApiError } from '@/lib/api-errors'
import { MAX_BASTION_DOMAINS, domainsOverLimit } from '@/lib/bastionDomains'

type DomainStatus = 'saved' | 'verified' | 'verifying' | 'failed' | 'pending'

interface Verification {
  state: 'verified' | 'verifying' | 'failed'
  error?: string
}

interface Props {
  desktopId: string
  savedDomains: string[]
  /** Missing while the desktop has no bastion target, so there is no CNAME to verify against. */
  targetId?: string
  bastionDomain?: string | null
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  targetId: undefined,
  bastionDomain: undefined,
  disabled: false
})

const domains = defineModel<string[]>({ required: true })

const { t, te } = useI18n()

const labelId = useId()
const showDnsHelp = ref(false)

const cnameTarget = computed(() =>
  props.targetId && props.bastionDomain ? `${props.targetId}.${props.bastionDomain}` : ''
)

const { mutateAsync: verify } = useMutation(verifyDesktopBastionDomainMutation())

// Keyed by domain name, so editing or removing a row can't move a status to another one.
const verifications = reactive(new Map<string, Verification>())

const domainStatus = (value: string): DomainStatus => {
  const domain = value.trim()
  if (props.savedDomains.includes(domain)) return 'saved'
  return verifications.get(domain)?.state ?? 'pending'
}

const rows = computed(() =>
  domains.value.map((value) => {
    const status = domainStatus(value)
    return {
      value,
      status,
      error: status === 'failed' ? verifications.get(value.trim())?.error : undefined,
      canVerify: !!props.targetId && !!value.trim() && (status === 'pending' || status === 'failed')
    }
  })
)

const statusIcons = {
  saved: { name: 'check-circle', color: 'success-600' },
  verified: { name: 'check-circle', color: 'info-600' },
  failed: { name: 'alert-circle', color: 'error-600' },
  pending: { name: 'alert-circle', color: 'warning-600' }
} as const

const verifyDomain = async (value: string) => {
  const domain = value.trim()
  verifications.set(domain, { state: 'verifying' })
  try {
    await verify({ path: { desktop_id: props.desktopId }, body: { domain } })
    verifications.set(domain, { state: 'verified' })
  } catch (error) {
    verifications.set(domain, {
      state: 'failed',
      error: describeApiError(error, { t, te }, 'bastion-domains')
    })
  }
}

const canAdd = computed(() => !props.disabled && domains.value.length < MAX_BASTION_DOMAINS)
const excess = computed(() => domainsOverLimit(domains.value, props.savedDomains))

const addDomain = () => {
  if (canAdd.value) domains.value = [...domains.value, '']
}

const updateDomain = (index: number, value: string) => {
  domains.value = domains.value.map((domain, i) => (i === index ? value : domain))
}

const removeDomain = (index: number) => {
  domains.value = domains.value.filter((_, i) => i !== index)
}
</script>

<template>
  <div role="group" :aria-labelledby="labelId" class="flex flex-col gap-2">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <Label :id="labelId" as="span" class="flex items-center gap-2 text-sm text-gray-warm-700">
        <Icon
          name="link-01"
          size="sm"
          stroke-color=""
          aria-hidden="true"
          class="text-gray-warm-500"
        />
        {{ t('components.domain.access.bastion.http-https.custom-domains.label') }}
        <span class="rounded-md bg-gray-warm-100 px-2 py-0.5 text-xs text-gray-warm-700">
          {{
            t('components.domain.access.bastion.http-https.custom-domains.count', {
              count: domains.length,
              max: MAX_BASTION_DOMAINS
            })
          }}
        </span>
      </Label>
      <Button
        type="button"
        size="sm"
        hierarchy="secondary-gray"
        icon="plus"
        :disabled="!canAdd"
        @click="addDomain"
      >
        {{ t('components.domain.access.bastion.http-https.custom-domains.add') }}
      </Button>
    </div>

    <Alert v-if="disabled" variant="warning">
      <FeaturedIconOutline kind="outline" color="warning" />
      <AlertTitle class="font-semibold text-gray-warm-700">
        {{ t('components.domain.access.bastion.http-https.custom-domains.disabled.title') }}
      </AlertTitle>
      <AlertDescription>
        {{ t('components.domain.access.bastion.http-https.custom-domains.disabled.description') }}
      </AlertDescription>
    </Alert>

    <template v-else>
      <p v-if="!rows.length" class="text-sm text-gray-warm-600">
        {{ t('components.domain.access.bastion.http-https.custom-domains.empty') }}
      </p>

      <div v-for="(row, index) in rows" :key="index" class="flex flex-col gap-1">
        <div class="flex items-center gap-2">
          <InputGroup :destructive="row.status === 'failed'">
            <InputGroupAddon>
              <Tooltip>
                <TooltipTrigger as-child>
                  <span
                    role="img"
                    :aria-label="
                      t(
                        `components.domain.access.bastion.http-https.custom-domains.status.${row.status}`
                      )
                    "
                    class="inline-flex"
                  >
                    <Spinner v-if="row.status === 'verifying'" size="sm" />
                    <Icon
                      v-else
                      :name="statusIcons[row.status].name"
                      size="sm"
                      :stroke-color="statusIcons[row.status].color"
                    />
                  </span>
                </TooltipTrigger>
                <TooltipContent
                  :title="
                    t(
                      `components.domain.access.bastion.http-https.custom-domains.status.${row.status}`
                    )
                  "
                />
              </Tooltip>
            </InputGroupAddon>
            <InputGroupInput
              type="text"
              :aria-label="
                t('components.domain.access.bastion.http-https.custom-domains.input-label', {
                  position: index + 1
                })
              "
              :placeholder="
                t('components.domain.access.bastion.http-https.custom-domains.placeholder')
              "
              :model-value="row.value"
              @update:model-value="(value) => updateDomain(index, String(value))"
            />
          </InputGroup>
          <Tooltip v-if="row.canVerify">
            <TooltipTrigger as-child>
              <Button
                type="button"
                size="sm"
                hierarchy="secondary-gray"
                icon="shield-tick"
                @click="verifyDomain(row.value)"
              />
            </TooltipTrigger>
            <TooltipContent
              :title="t('components.domain.access.bastion.http-https.custom-domains.verify')"
            />
          </Tooltip>
          <Tooltip>
            <TooltipTrigger as-child>
              <Button
                type="button"
                size="sm"
                hierarchy="secondary-destructive"
                icon="trash-04"
                @click="removeDomain(index)"
              />
            </TooltipTrigger>
            <TooltipContent
              :title="t('components.domain.access.bastion.http-https.custom-domains.remove')"
            />
          </Tooltip>
        </div>
        <FieldError v-if="row.error" :errors="[row.error]" />
      </div>

      <FieldError
        v-if="excess"
        icon="alert-circle"
        :errors="[
          t(
            'components.domain.access.bastion.http-https.custom-domains.over-limit-error',
            { count: excess, max: MAX_BASTION_DOMAINS },
            excess
          )
        ]"
      />
      <p v-else-if="domains.length > MAX_BASTION_DOMAINS" class="text-sm text-gray-warm-600">
        {{
          t('components.domain.access.bastion.http-https.custom-domains.over-limit', {
            count: domains.length,
            max: MAX_BASTION_DOMAINS
          })
        }}
      </p>
      <p v-else-if="!canAdd" class="text-sm text-gray-warm-600">
        {{
          t('components.domain.access.bastion.http-https.custom-domains.limit-reached', {
            max: MAX_BASTION_DOMAINS
          })
        }}
      </p>

      <template v-if="cnameTarget">
        <Button
          type="button"
          size="sm"
          hierarchy="link-gray"
          class="w-fit p-0"
          :aria-expanded="showDnsHelp"
          @click="showDnsHelp = !showDnsHelp"
        >
          {{
            showDnsHelp
              ? t('components.domain.access.bastion.http-https.custom-domains.less-details')
              : t('components.domain.access.bastion.http-https.custom-domains.more-details')
          }}
          <Icon
            :name="showDnsHelp ? 'chevron-up' : 'chevron-down'"
            size="sm"
            stroke-color="gray-warm-600"
          />
        </Button>
        <Alert v-if="showDnsHelp">
          <AlertTitle class="font-semibold text-gray-warm-700 mb-1">
            {{ t('components.domain.access.bastion.http-https.custom-domains.alert.title') }}
          </AlertTitle>
          <AlertDescription class="text-gray-warm-700">
            <i18n-t
              keypath="components.domain.access.bastion.http-https.custom-domains.alert.description"
              tag="span"
            >
              <template #cname-url>
                <Code class="break-all">{{ cnameTarget }}</Code>
                <span class="inline-block mx-1">
                  <CopyIcon
                    class="inline-block"
                    :value="cnameTarget"
                    size="sm"
                    stroke-color="gray-warm-600"
                  />
                </span>
              </template>
            </i18n-t>
          </AlertDescription>
        </Alert>
      </template>
    </template>
  </div>
</template>
