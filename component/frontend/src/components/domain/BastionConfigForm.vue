<script setup lang="ts">
import { useForm } from '@tanstack/vue-form'
import { useI18n } from 'vue-i18n'
import { InputField } from '@/components/input-field'
import { reactive } from 'vue'
import { z } from 'zod'
import { FieldContent, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Switch } from '@/components/ui/switch'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Code } from '@/components/code'
import { Icon, CopyIcon } from '@/components/icon'
import { ref } from 'vue'

interface BastionHttpHttps {
  enabled?: boolean
  httpPort: number
  httpsPort: number
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
}

const props = withDefaults(defineProps<Props>(), {
  bastion: () => ({
    enabled: false,
    http: {
      enabled: false,
      httpPort: 80,
      httpsPort: 443
    },
    ssh: {
      enabled: false,
      sshPort: 22,
      authorizedKeys: ''
    },
    customDomains: []
  }),
  showCustomDomains: false
})

const { t } = useI18n()

const formSchema = z.object({
  http: z
    .object({
      enabled: z.boolean(),
      httpPort: z.number().min(1).max(65535),
      httpsPort: z.number().min(1).max(65535)
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

defineExpose({
  getFormData
})

const bastionEnabled = ref(false)
const bastionModalDnsAlertOpen = ref(false)

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
  <section
    class="grid grid-cols-2 items-start border-b border-gray-300 pb-7 md:grid-cols-[280px_1FR]"
  >
    <div class="flex flex-row-reverse items-center gap-2.5 justify-end">
      <h4 class="text-lg font-semibold text-gray-warm-900">
        {{ t('components.domain.access.sections.bastion') }}
      </h4>
      <Icon name="shield-01" />
    </div>
    <div class="flex gap-2.5">
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger as-child>
            <FieldLabel>
              {{ t('components.domain.access.bastion.label') }}
              <Icon name="info-circle" size="xs" class="inline-block" />
            </FieldLabel>
          </TooltipTrigger>
          <TooltipContent
            :title="t('components.domain.access.bastion.label')"
            :subtitle="t('components.domain.access.bastion.description')"
          />
        </Tooltip>
      </TooltipProvider>
      <Switch
        type="checkbox"
        :model-value="bastionEnabled"
        @update:model-value="bastionEnabled = $event"
      />
    </div>
  </section>
  <FieldGroup>
    <form.Subscribe>
      <template v-if="bastionEnabled">
        <!-- HTTP/HTTPS Section -->
        <section
          class="grid gap-1.5 items-start border-b border-gray-300 pb-7 md:grid-cols-[280px_1FR] md:gap-0"
        >
          <div class="flex flex-row-reverse justify-end items-center gap-2.5">
            <h4 class="text-lg font-semibold text-gray-warm-900">
              {{ t('components.domain.access.sections.bastion-configuration') }}
            </h4>
            <Icon name="shield-zap" />
          </div>
          <div class="flex flex-col gap-3.5">
            <section class="border-b border-gray-300 pb-5">
              <form.Field v-slot="{ field: httpEnabledField }" name="http.enabled">
                <div class="mb-4 flex items-center gap-5">
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger as-child>
                        <FieldLabel>
                          {{ t('components.domain.access.bastion.http-https.label') }}
                          <Icon name="info-circle" size="xs" class="inline-block" />
                        </FieldLabel>
                      </TooltipTrigger>
                      <TooltipContent
                        :title="t('components.domain.access.bastion.http-https.label')"
                        :subtitle="t('components.domain.access.bastion.http-https.description')"
                      />
                    </Tooltip>
                  </TooltipProvider>
                  <Switch
                    :id="httpEnabledField.name"
                    type="checkbox"
                    :name="httpEnabledField.name"
                    :model-value="httpEnabledField.state.value"
                    @update:model-value="httpEnabledField.handleChange"
                  />
                </div>
              </form.Field>
              <template v-if="form.getFieldValue('http.enabled')">
                <div class="grid grid-cols-2 gap-4">
                  <div>
                    <form.Field v-slot="{ field: httpField }" name="http.httpPort">
                      <FieldLabel class="mb-2">
                        {{ t('components.domain.access.bastion.http-https.http-port.label') }}
                      </FieldLabel>
                      <FieldContent>
                        <InputField
                          :id="httpField.name"
                          :name="httpField.name"
                          :model-value="httpField.state.value"
                          type="number"
                          min="1"
                          max="65535"
                          @update:model-value="(value) => httpField.handleChange(Number(value))"
                        />
                      </FieldContent>
                      <FieldError :errors="httpField.state.meta.errors" />
                    </form.Field>
                  </div>
                  <div>
                    <form.Field v-slot="{ field: httpsField }" name="http.httpsPort">
                      <FieldLabel class="mb-2">
                        {{ t('components.domain.access.bastion.http-https.https-port.label') }}
                      </FieldLabel>
                      <FieldContent>
                        <InputField
                          :id="httpsField.name"
                          :name="httpsField.name"
                          :model-value="httpsField.state.value"
                          type="number"
                          min="1"
                          max="65535"
                          @update:model-value="(value) => httpsField.handleChange(Number(value))"
                        />
                      </FieldContent>
                      <FieldError :errors="httpsField.state.meta.errors" />
                    </form.Field>
                  </div>
                </div>
                <div v-if="showCustomDomains">
                  <div class="flex items-center justify-between">
                    <h3 class="text-sm font-medium">
                      {{ t('components.domain.access.bastion.http-https.custom-domains.label') }}
                    </h3>
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
                        <form.Field
                          v-slot="{ field: domainField }"
                          :name="`customDomains[${index}]`"
                        >
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
                              @update:model-value="
                                (value) => domainField.handleChange(String(value))
                              "
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
                      class="cursor-pointer gap-1 ml-2 text-gray-warm-600"
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
            </section>
            <!-- SSH Section -->
            <section>
              <form.Field v-slot="{ field: sshEnabledField }" name="ssh.enabled">
                <div class="flex items-center gap-5 mb-4">
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger as-child>
                        <FieldLabel>
                          {{ t('components.domain.access.bastion.ssh.label') }}
                          <Icon name="info-circle" size="xs" class="inline-block" />
                        </FieldLabel>
                      </TooltipTrigger>
                      <TooltipContent
                        :title="t('components.domain.access.bastion.ssh.label')"
                        :subtitle="t('components.domain.access.bastion.ssh.description')"
                      />
                    </Tooltip>
                  </TooltipProvider>
                  <Switch
                    :id="sshEnabledField.name"
                    type="checkbox"
                    :name="sshEnabledField.name"
                    :model-value="sshEnabledField.state.value"
                    @update:model-value="sshEnabledField.handleChange"
                  />
                </div>
              </form.Field>
              <template v-if="form.getFieldValue('ssh.enabled')">
                <div class="space-y-4 grid grid-cols-1 gap-4 md:grid-cols-[20%_1fr]">
                  <div>
                    <form.Field v-slot="{ field: sshPortField }" name="ssh.sshPort">
                      <FieldLabel class="mb-2">
                        {{ t('components.domain.access.bastion.ssh.port.label') }}
                      </FieldLabel>
                      <FieldContent>
                        <InputField
                          :id="sshPortField.name"
                          :name="sshPortField.name"
                          :model-value="sshPortField.state.value"
                          type="number"
                          min="1"
                          max="65535"
                          @update:model-value="(value) => sshPortField.handleChange(Number(value))"
                        />
                      </FieldContent>
                      <FieldError :errors="sshPortField.state.meta.errors" />
                    </form.Field>
                  </div>
                  <div>
                    <form.Field v-slot="{ field: keysField }" name="ssh.authorizedKeys">
                      <FieldLabel class="mb-2">
                        {{ t('components.domain.access.bastion.ssh.authorized-keys.label') }}
                      </FieldLabel>
                      <FieldContent>
                        <Textarea
                          class="w-full bg-base-white h-32 text-nowrap mb-1"
                          :placeholder="
                            t(
                              'components.bastion-info-modal.fields.ssh.authorized-keys.placeholder'
                            )
                          "
                          :model-value="keysField.state.value"
                          @blur="keysField.handleBlur"
                          @input="keysField.handleChange($event.target.value)"
                        />
                      </FieldContent>
                      <FieldError :errors="keysField.state.meta.errors" />
                    </form.Field>
                  </div>
                </div>
              </template>
            </section>
          </div>
        </section>
      </template>
    </form.Subscribe>
  </FieldGroup>
</template>
