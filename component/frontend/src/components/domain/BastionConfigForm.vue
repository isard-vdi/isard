<script setup lang="ts">
import { useForm } from '@tanstack/vue-form'
import { useI18n } from 'vue-i18n'
import { InputField } from '@/components/input-field'
import { reactive } from 'vue'
import { z } from 'zod'
import { Field, FieldContent, FieldError, FieldLabel } from '@/components/ui/field'
import { Switch } from '@/components/ui/switch'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Code } from '@/components/code'
import { Icon, CopyIcon } from '@/components/icon'
import { FeaturedIconOutline } from '@/components/icon/featured-outline'
import { toast } from '@/components/ui/toast'
import { ref, watch } from 'vue'
import { WIREGUARD_INTERFACE_ID } from '@/lib/viewers'

interface BastionHttpHttps {
  enabled?: boolean
  httpPort: number
  httpsPort: number
  proxyProtocol?: boolean
}

interface BastionSsh {
  enabled?: boolean
  sshPort: number
  authorizedKeys: string
}

interface Bastion {
  enabled?: boolean
  http?: BastionHttpHttps
  ssh?: BastionSsh
  customDomains?: string[]
}

interface Props {
  bastion?: Bastion
  showCustomDomains?: boolean
  hardwareInterfaces?: string[]
  onRequestAddInterface?: (ifaceId: string) => boolean | undefined
}

const props = withDefaults(defineProps<Props>(), {
  bastion: () => ({
    enabled: false,
    http: {
      enabled: false,
      httpPort: 80,
      httpsPort: 443,
      proxyProtocol: false
    },
    ssh: {
      enabled: false,
      sshPort: 22,
      authorizedKeys: ''
    },
    customDomains: []
  }),
  showCustomDomains: false,
  hardwareInterfaces: () => [],
  onRequestAddInterface: undefined
})

const emit = defineEmits<{
  'bastion-enabled': [enabled: boolean]
}>()

const { t } = useI18n()

const formSchema = z.object({
  http: z
    .object({
      enabled: z.boolean(),
      httpPort: z.number().min(1).max(65535),
      httpsPort: z.number().min(1).max(65535),
      proxyProtocol: z.boolean().optional()
    })
    .optional(),
  ssh: z
    .object({
      enabled: z.boolean(),
      sshPort: z.number().min(1).max(65535),
      authorizedKeys: z.string()
    })
    .optional(),
  customDomains: z.array(z.string().url('Invalid domain URL')).optional()
})

const defaultValues = reactive(props.bastion)

const form = useForm({
  defaultValues,
  validators: {
    onBlur: formSchema
  }
})

const getFormData = () => {
  const http = form.getFieldValue('http')
  const ssh = form.getFieldValue('ssh')

  const data: Record<string, unknown> = {
    http: http?.enabled ? http : null,
    ssh: ssh?.enabled ? ssh : null
  }

  if (props.showCustomDomains) {
    data.customDomains = form.getFieldValue('customDomains')
  }

  return data
}

const isFormValid = form.useStore((state) => state.isValid)

const isDirty = form.useStore((state) => !state.isDefaultValue)

const bastionEnabled = ref(!!(props.bastion?.http?.enabled || props.bastion?.ssh?.enabled))

const reset = () => {
  bastionEnabled.value = !!(props.bastion?.http?.enabled || props.bastion?.ssh?.enabled)
  form.reset(props.bastion)
}

defineExpose({
  getFormData,
  isValid: isFormValid,
  isDirty,
  reset
})

const bastionModalDnsAlertOpen = ref(false)
const stopBastionHydration = watch(
  () => props.bastion,
  () => {
    reset()
    stopBastionHydration()
  }
)

watch(
  bastionEnabled,
  (enabled) => {
    emit('bastion-enabled', enabled)
    if (!enabled) {
      // When user disables bastion, clear the inner http/ssh enabled flags so
      // getFormData() produces { http: null, ssh: null }.
      form.setFieldValue('http.enabled', false)
      form.setFieldValue('ssh.enabled', false)
    }
  },
  { immediate: true }
)

watch(bastionEnabled, (enabled, wasEnabled) => {
  if (!enabled || wasEnabled) return
  if ((props.hardwareInterfaces ?? []).includes(WIREGUARD_INTERFACE_ID)) return
  if (!props.onRequestAddInterface) return

  const added = props.onRequestAddInterface(WIREGUARD_INTERFACE_ID)

  if (added === true) {
    toast.info(t('components.domain.access.wireguard-added.title'), {
      description: t('components.domain.access.wireguard-added.description-bastion')
    })
  } else if (added === false) {
    bastionEnabled.value = false
    toast.error(t('components.domain.access.wireguard-warning.title'), {
      description: t('components.domain.access.wireguard-warning.no-permission-description-bastion')
    })
  }
})

const bastionDisabled = ref(false)

watch(
  () => props.hardwareInterfaces,
  (newInterfaces, oldInterfaces) => {
    const had = (oldInterfaces ?? []).includes(WIREGUARD_INTERFACE_ID)
    const has = (newInterfaces ?? []).includes(WIREGUARD_INTERFACE_ID)
    if (had && !has && bastionEnabled.value) {
      bastionEnabled.value = false
      bastionDisabled.value = true
      // Show a toast, as the bastion section may be out of view
      toast.warning(t('components.domain.access.bastion-disabled.title'), {
        description: t('components.domain.access.bastion-disabled.description')
      })
    } else if (has) {
      // Don't keep the alert around once wireguard is back
      bastionDisabled.value = false
    }
  }
)

const addCustomDomain = () => {
  const currentDomains = form.getFieldValue('customDomains') || []
  form.setFieldValue('customDomains', [...currentDomains, ''])
}

const removeCustomDomain = (index: number) => {
  const currentDomains = form.getFieldValue('customDomains') || []
  form.setFieldValue(
    'customDomains',
    currentDomains.filter((_, i) => i !== index)
  )
}
</script>

<template>
  <!-- Bastion -->
  <section class="group/hw-section grid gap-4 items-start">
    <div class="flex items-center gap-2">
      <!-- Empty stroke-color clears Icon's inline color so the class below can drive
           currentColor and pick up the focus-within highlight. -->
      <Icon
        name="shield-01"
        size="sm"
        stroke-color=""
        aria-hidden="true"
        class="text-gray-warm-500 transition-colors duration-200 group-focus-within/hw-section:text-brand-700"
      />
      <h4
        class="text-xs font-bold uppercase tracking-wide text-gray-warm-600 transition-colors duration-200 group-focus-within/hw-section:text-brand-700"
      >
        {{ t('components.domain.access.sections.bastion') }}
      </h4>
      <Separator class="flex-1" />
    </div>
    <div class="flex flex-col gap-2.5 md:gap-5">
      <div class="flex gap-3">
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger as-child>
              <FieldLabel>
                {{ t('components.domain.access.bastion.enable') }}
                <Icon name="info-circle" size="xs" class="inline-block" />
              </FieldLabel>
            </TooltipTrigger>
            <TooltipContent
              :title="t('components.domain.access.bastion.enable')"
              :subtitle="t('components.domain.access.bastion.description')"
            />
          </Tooltip>
        </TooltipProvider>
        <FieldContent>
          <Switch
            type="checkbox"
            :aria-label="t('components.domain.access.bastion.enable')"
            :model-value="bastionEnabled"
            @update:model-value="bastionEnabled = $event"
          />
        </FieldContent>
      </div>
      <Alert v-if="bastionDisabled" variant="default" class="border-error-600">
        <FeaturedIconOutline kind="outline" color="error" />
        <AlertTitle>{{ t('components.domain.access.bastion-disabled.title') }}</AlertTitle>
        <AlertDescription>
          {{ t('components.domain.access.bastion-disabled.description') }}
        </AlertDescription>
      </Alert>
    </div>
  </section>
  <template v-if="bastionEnabled">
    <!-- Bastion configuration -->
    <section class="group/hw-section grid gap-4 items-start">
      <div class="flex items-center gap-2">
        <Icon
          name="shield-zap"
          size="sm"
          stroke-color=""
          aria-hidden="true"
          class="text-gray-warm-500 transition-colors duration-200 group-focus-within/hw-section:text-brand-700"
        />
        <h4
          class="text-xs font-bold uppercase tracking-wide text-gray-warm-600 transition-colors duration-200 group-focus-within/hw-section:text-brand-700"
        >
          {{ t('components.domain.access.sections.bastion-configuration') }}
        </h4>
        <Separator class="flex-1" />
      </div>
      <!-- Indented so the two toggles read as sub-options of the heading above;
           pl-6 lines them up with its text (16px icon + 8px gap). Neither block has
           a heading of its own, so the rule between them carries the grouping. -->
      <div class="flex flex-col gap-5 pl-6">
        <!-- HTTP / HTTPS -->
        <form.Field v-slot="{ field: httpEnabledField }" name="http.enabled">
          <div class="flex flex-col gap-2.5 md:gap-5">
            <div class="flex gap-3">
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger as-child>
                    <FieldLabel>
                      {{ t('components.domain.access.bastion.http-https.enable') }}
                      <Icon name="info-circle" size="xs" class="inline-block" />
                    </FieldLabel>
                  </TooltipTrigger>
                  <TooltipContent
                    :title="t('components.domain.access.bastion.http-https.enable')"
                    :subtitle="t('components.domain.access.bastion.http-https.description')"
                  />
                </Tooltip>
              </TooltipProvider>
              <FieldContent>
                <Switch
                  :id="httpEnabledField.name"
                  type="checkbox"
                  :name="httpEnabledField.name"
                  :aria-label="t('components.domain.access.bastion.http-https.enable')"
                  :model-value="httpEnabledField.state.value"
                  @update:model-value="httpEnabledField.handleChange"
                />
              </FieldContent>
            </div>
            <template v-if="httpEnabledField.state.value">
              <div class="grid grid-cols-1 gap-2.5 sm:grid-cols-2 md:gap-5 lg:grid-cols-4">
                <form.Field v-slot="{ field: httpField }" name="http.httpPort">
                  <Field>
                    <FieldLabel :for="httpField.name">
                      {{ t('components.domain.access.bastion.http-https.http-port.label') }}
                    </FieldLabel>
                    <InputField
                      :id="httpField.name"
                      :name="httpField.name"
                      :model-value="httpField.state.value"
                      type="number"
                      min="1"
                      max="65535"
                      @blur="httpField.handleBlur"
                      @update:model-value="(value) => httpField.handleChange(Number(value))"
                    />
                    <FieldError :errors="httpField.state.meta.errors" />
                  </Field>
                </form.Field>
                <form.Field v-slot="{ field: httpsField }" name="http.httpsPort">
                  <Field>
                    <FieldLabel :for="httpsField.name">
                      {{ t('components.domain.access.bastion.http-https.https-port.label') }}
                    </FieldLabel>
                    <InputField
                      :id="httpsField.name"
                      :name="httpsField.name"
                      :model-value="httpsField.state.value"
                      type="number"
                      min="1"
                      max="65535"
                      @blur="httpsField.handleBlur"
                      @update:model-value="(value) => httpsField.handleChange(Number(value))"
                    />
                    <FieldError :errors="httpsField.state.meta.errors" />
                  </Field>
                </form.Field>
              </div>
              <form.Field v-slot="{ field: proxyProtocolField }" name="http.proxyProtocol">
                <div class="flex gap-3">
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger as-child>
                        <FieldLabel>
                          {{
                            t('components.domain.access.bastion.http-https.proxy-protocol.label')
                          }}
                          <Icon name="info-circle" size="xs" class="inline-block" />
                        </FieldLabel>
                      </TooltipTrigger>
                      <TooltipContent
                        :title="
                          t('components.domain.access.bastion.http-https.proxy-protocol.label')
                        "
                        :subtitle="
                          t(
                            'components.domain.access.bastion.http-https.proxy-protocol.description'
                          )
                        "
                      />
                    </Tooltip>
                  </TooltipProvider>
                  <FieldContent>
                    <Switch
                      :id="proxyProtocolField.name"
                      type="checkbox"
                      :name="proxyProtocolField.name"
                      :aria-label="
                        t('components.domain.access.bastion.http-https.proxy-protocol.label')
                      "
                      :model-value="proxyProtocolField.state.value"
                      @update:model-value="proxyProtocolField.handleChange"
                    />
                  </FieldContent>
                </div>
              </form.Field>
              <div v-if="showCustomDomains" class="flex flex-col gap-2">
                <div class="flex items-center justify-between gap-2">
                  <FieldLabel>
                    {{ t('components.domain.access.bastion.http-https.custom-domains.label') }}
                  </FieldLabel>
                  <Button size="sm" hierarchy="secondary" @click="addCustomDomain">
                    <Icon name="plus" size="sm" />
                    {{ t('components.domain.access.bastion.http-https.custom-domains.add') }}
                  </Button>
                </div>
                <form.Field v-slot="{ field: domainsField }" name="customDomains">
                  <div class="space-y-2">
                    <div
                      v-for="(domain, index) in domainsField.state.value"
                      :key="index"
                      class="flex gap-2"
                    >
                      <form.Field v-slot="{ field: domainField }" :name="`customDomains[${index}]`">
                        <div class="flex-1">
                          <InputField
                            :id="domainField.name"
                            :name="domainField.name"
                            :model-value="domainField.state.value"
                            type="text"
                            :placeholder="
                              t(
                                'components.domain.access.bastion.http-https.custom-domains.placeholder'
                              )
                            "
                            @update:model-value="(value) => domainField.handleChange(String(value))"
                          />
                          <FieldError :errors="domainField.state.meta.errors" />
                        </div>
                      </form.Field>
                      <Button size="sm" hierarchy="link-color" @click="removeCustomDomain(index)">
                        <Icon name="delete" stroke-color="error-600" />
                      </Button>
                    </div>
                    <p
                      v-if="!domainsField.state.value || domainsField.state.value.length === 0"
                      class="text-sm text-muted-foreground"
                    >
                      {{ t('components.domain.access.bastion.http-https.custom-domains.empty') }}
                    </p>
                  </div>
                </form.Field>
                <div class="flex flex-col items-start gap-2">
                  <Label
                    class="cursor-pointer gap-1 text-gray-warm-600"
                    @click="bastionModalDnsAlertOpen = !bastionModalDnsAlertOpen"
                    >{{
                      bastionModalDnsAlertOpen
                        ? t(
                            'components.domain.access.bastion.http-https.custom-domains.less-details'
                          )
                        : t(
                            'components.domain.access.bastion.http-https.custom-domains.more-details'
                          )
                    }}
                    <Icon
                      :name="bastionModalDnsAlertOpen ? 'chevron-up' : 'chevron-down'"
                      stroke-color="gray-warm-600"
                    />
                  </Label>
                  <Alert v-if="bastionModalDnsAlertOpen" class="bg-white border-gray-warm-300">
                    <AlertTitle class="font-bold text-gray-warm-700 mb-2">{{
                      t('components.domain.access.bastion.http-https.custom-domains.alert.title')
                    }}</AlertTitle>
                    <i18n-t
                      keypath="components.domain.access.bastion.http-https.custom-domains.alert.description"
                      tag="AlertDescription"
                      class="text-gray-warm-700"
                    >
                      <template #cname-url>
                        <Code>{{ `00000000-0000-0000-0000.000000000000.example.com` }}</Code>
                        <div class="inline-block mx-1">
                          <CopyIcon
                            class="inline-block"
                            :value="`00000000-0000-0000-0000.000000000000.example.com`"
                            size="sm"
                            stroke-color="gray-warm-600"
                          />
                        </div>
                      </template>
                    </i18n-t>
                  </Alert>
                </div>
              </div>
            </template>
          </div>
        </form.Field>
        <Separator />
        <!-- SSH -->
        <form.Field v-slot="{ field: sshEnabledField }" name="ssh.enabled">
          <div class="flex flex-col gap-2.5 md:gap-5">
            <div class="flex gap-3">
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger as-child>
                    <FieldLabel>
                      {{ t('components.domain.access.bastion.ssh.enable') }}
                      <Icon name="info-circle" size="xs" class="inline-block" />
                    </FieldLabel>
                  </TooltipTrigger>
                  <TooltipContent
                    :title="t('components.domain.access.bastion.ssh.enable')"
                    :subtitle="t('components.domain.access.bastion.ssh.description')"
                  />
                </Tooltip>
              </TooltipProvider>
              <FieldContent>
                <Switch
                  :id="sshEnabledField.name"
                  type="checkbox"
                  :name="sshEnabledField.name"
                  :aria-label="t('components.domain.access.bastion.ssh.enable')"
                  :model-value="sshEnabledField.state.value"
                  @update:model-value="sshEnabledField.handleChange"
                />
              </FieldContent>
            </div>
            <div
              v-if="sshEnabledField.state.value"
              class="grid grid-cols-1 gap-2.5 md:grid-cols-[20%_1fr] md:gap-5"
            >
              <form.Field v-slot="{ field: sshPortField }" name="ssh.sshPort">
                <Field>
                  <FieldLabel :for="sshPortField.name">
                    {{ t('components.domain.access.bastion.ssh.port.label') }}
                  </FieldLabel>
                  <InputField
                    :id="sshPortField.name"
                    :name="sshPortField.name"
                    :model-value="sshPortField.state.value"
                    type="number"
                    min="1"
                    max="65535"
                    @blur="sshPortField.handleBlur"
                    @update:model-value="(value) => sshPortField.handleChange(Number(value))"
                  />
                  <FieldError :errors="sshPortField.state.meta.errors" />
                </Field>
              </form.Field>
              <form.Field v-slot="{ field: keysField }" name="ssh.authorizedKeys">
                <Field>
                  <FieldLabel :for="keysField.name">
                    {{ t('components.domain.access.bastion.ssh.authorized-keys.label') }}
                  </FieldLabel>
                  <Textarea
                    :id="keysField.name"
                    class="w-full bg-base-white h-32 text-nowrap"
                    :placeholder="
                      t('components.bastion-info-modal.fields.ssh.authorized-keys.placeholder')
                    "
                    :model-value="keysField.state.value"
                    @blur="keysField.handleBlur"
                    @input="keysField.handleChange($event.target.value)"
                  />
                  <FieldError :errors="keysField.state.meta.errors" />
                </Field>
              </form.Field>
            </div>
          </div>
        </form.Field>
      </div>
    </section>
  </template>
</template>
