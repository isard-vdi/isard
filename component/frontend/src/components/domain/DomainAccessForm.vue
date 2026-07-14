<script setup lang="ts">
import { useForm } from '@tanstack/vue-form'
import { useI18n } from 'vue-i18n'
import { InputField } from '@/components/input-field'
import { computed, ref, reactive, watch } from 'vue'

import { z } from 'zod'
import {
  Field,
  FieldContent,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel
} from '@/components/ui/field'
import { Skeleton } from '@/components/ui/skeleton'
import { useQuery } from '@tanstack/vue-query'
import {
  getTemplateInfoOptions,
  getDesktopInfoOptions
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { Switch } from '@/components/ui/switch'
import { Icon } from '@/components/icon'
import ViewersSelector from '@/components/domain/ViewersSelector.vue'
import BastionConfigForm from '@/components/domain/BastionConfigForm.vue'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { FeaturedIconOutline } from '@/components/icon/featured-outline'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { Button } from '@/components/ui/button'
import { toast } from '@/components/ui/toast'
import {
  hasWireguardRequiringViewer,
  stripWireguardRequiringViewers,
  getWireguardRequiringViewers
} from '@/lib/viewers'

interface Credentials {
  username: string
  password: string
}

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
  http?: BastionHttpHttps
  ssh?: BastionSsh
  customDomains?: string[]
}

interface Props {
  loading?: boolean
  templateId?: string
  desktopId?: string
  // Also allow sending the access values directly through props
  credentials?: Credentials
  fullscreen?: boolean
  showBastionConfig?: boolean // Whether to show the bastion config form
  showCustomDomains?: boolean // Whether to show custom domains in bastion config
  bastion?: Bastion
  viewers?: string[]
  hardwareInterfaces?: string[]
  onRequestAddInterface?: (ifaceId: string) => boolean | undefined
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
  templateId: undefined,
  desktopId: undefined,
  credentials: () => ({
    username: 'isard',
    password: 'pirineus'
  }),
  fullscreen: false,
  showBastionConfig: false,
  showCustomDomains: false,
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
  viewers: () => [],
  hardwareInterfaces: () => [],
  onRequestAddInterface: undefined
})

const emit = defineEmits<{
  'rdp-viewers-enabled': [enabled: boolean]
  'bastion-enabled': [enabled: boolean]
}>()

// Fetch template info when templateId is provided
const {
  isPending: templateLoading,
  error: templateError,
  data: templateData
} = useQuery({
  ...getTemplateInfoOptions({
    path: {
      template_id: props.templateId!
    }
  }),
  enabled: computed(() => !!props.templateId),
  gcTime: 0
})

// Fetch desktop info when desktopId is provided
const {
  isPending: desktopLoading,
  error: desktopError,
  data: desktopData
} = useQuery({
  ...getDesktopInfoOptions({
    path: {
      desktop_id: props.desktopId!
    }
  }),
  enabled: computed(() => !!props.desktopId),
  gcTime: 0
})

// Computed access values from template or desktop data or props

const credentials = computed<Credentials>(() => {
  if (templateData.value?.guest_properties) {
    return {
      username: templateData.value.guest_properties.credentials.username,
      password: templateData.value.guest_properties.credentials.password
    }
  } else if (desktopData.value?.guest_properties) {
    return {
      username: desktopData.value.guest_properties.credentials.username,
      password: desktopData.value.guest_properties.credentials.password
    }
  } else {
    return props.credentials!
  }
})

const fullscreen = computed<boolean>(() => {
  if (templateData.value?.guest_properties) {
    return templateData.value.guest_properties.fullscreen
  } else if (desktopData.value?.guest_properties) {
    return desktopData.value.guest_properties.fullscreen
  } else {
    return props.fullscreen!
  }
})

const viewers = computed<string[]>(() => {
  if (templateData.value?.guest_properties) {
    return Object.entries(templateData.value.guest_properties.viewers ?? {})
      .filter(([, v]) => v !== null)
      .map(([k]) => k)
  } else if (desktopData.value?.guest_properties?.viewers) {
    return Object.entries(desktopData.value.guest_properties.viewers)
      .filter(([, v]) => v !== null)
      .map(([k]) => k)
  } else {
    return props.viewers
  }
})

const bastion = computed<Bastion>(() => {
  if (templateData.value?.bastion_target) {
    const bt = templateData.value.bastion_target
    return {
      enabled: bt.http?.enabled || bt.ssh?.enabled || false,
      http: {
        enabled: bt.http?.enabled || false,
        httpPort: bt.http?.http_port || 80,
        httpsPort: bt.http?.https_port || 443,
        proxyProtocol: bt.http?.proxy_protocol || false
      },
      ssh: {
        enabled: bt.ssh?.enabled || false,
        sshPort: bt.ssh?.port || 22,
        authorizedKeys: bt.ssh?.authorized_keys?.join('\n') || ''
      },
      // TODO: full multi-domain UI. Reads the domains array; the create/edit
      // send path still needs to map customDomains -> the API `domains` field.
      customDomains: bt.domains || []
    }
  } else if (desktopData.value?.bastion_target) {
    const bt = desktopData.value.bastion_target
    return {
      enabled: bt.http?.enabled || bt.ssh?.enabled || false,
      http: {
        enabled: bt.http?.enabled || false,
        httpPort: bt.http?.http_port || 80,
        httpsPort: bt.http?.https_port || 443,
        proxyProtocol: bt.http?.proxy_protocol || false
      },
      ssh: {
        enabled: bt.ssh?.enabled || false,
        sshPort: bt.ssh?.port || 22,
        authorizedKeys: bt.ssh?.authorized_keys?.join('\n') || ''
      },
      // TODO: full multi-domain UI. Reads the domains array; the create/edit
      // send path still needs to map customDomains -> the API `domains` field.
      customDomains: bt.domains || []
    }
  } else {
    return props.bastion!
  }
})

const { t } = useI18n()

const formSchema = z.object({
  credentials: z.object({
    username: z.string().optional(),
    password: z.string().optional()
  }),
  fullscreen: z.boolean(),
  viewers: z.array(z.string()).min(1)
})

const defaultValues = reactive({
  credentials,
  fullscreen,
  viewers
})

const form = useForm({
  defaultValues,
  validators: {
    onChange: formSchema
  }
})

// --- Bastion coordination ---

const bastionEnabled = ref(false)

function handleBastionEnabled(enabled: boolean) {
  bastionEnabled.value = enabled
  emit('bastion-enabled', enabled)
}
// Sync form fields when source data changes (e.g. stale cache replaced by fresh fetch)
watch([templateData, desktopData], () => {
  form.setFieldValue('credentials', credentials.value)
  form.setFieldValue('fullscreen', fullscreen.value)
  form.setFieldValue('viewers', viewers.value)
})
// --- Viewer / wireguard coordination ---

const selectedViewers = form.useStore((state) => state.values.viewers)

const hasRdpViewer = computed(() => hasWireguardRequiringViewer(selectedViewers.value ?? []))

const removedViewers = ref<string[]>([])

watch(
  () => (templateData.value ?? desktopData.value)?.limited_hardware,
  (lh) => {
    const dropped = (lh as { viewers?: { old_value?: string[] } } | undefined)?.viewers?.old_value
    if (dropped?.length) removedViewers.value = dropped
  },
  { immediate: true }
)

const viewerLabelKeys: Record<string, string> = {
  browser_rdp: 'components.viewers-selector.browser-viewers.rdp-browser',
  browser_vnc: 'components.viewers-selector.browser-viewers.vnc-browser',
  file_rdpgw: 'components.viewers-selector.file-viewers.rdp',
  file_spice: 'components.viewers-selector.file-viewers.spice',
  file_rdpvpn: 'components.viewers-selector.file-viewers.rdp-vpn'
}

const removedViewerLabels = computed<string[]>(() =>
  removedViewers.value.map((viewer) =>
    viewerLabelKeys[viewer] ? t(viewerLabelKeys[viewer]) : viewer
  )
)

watch(
  hasRdpViewer,
  (enabled) => {
    emit('rdp-viewers-enabled', enabled)
  },
  { immediate: true }
)

watch(
  () => props.hardwareInterfaces,
  (newInterfaces, oldInterfaces) => {
    const had = (oldInterfaces ?? []).includes('wireguard')
    const has = (newInterfaces ?? []).includes('wireguard')
    if (had && !has && hasRdpViewer.value) {
      const current = (form.getFieldValue('viewers') as string[] | undefined) ?? []
      removedViewers.value = getWireguardRequiringViewers(current)
      form.setFieldValue('viewers', stripWireguardRequiringViewers(current))
      // Show a toast, as the alert may be out of view
      toast.warning(t('components.domain.access.viewers-removed.title'), {
        description: t('components.domain.access.viewers-removed.toast-description', {
          viewers: removedViewerLabels.value.join(', ')
        })
      })
    } else if (has) {
      // Don't remove viewers if wireguard is present
      removedViewers.value = []
    }
  }
)

watch(hasRdpViewer, (next, prev) => {
  if (!next || prev) return
  if ((props.hardwareInterfaces ?? []).includes('wireguard')) return
  if (!props.onRequestAddInterface) return

  const added = props.onRequestAddInterface('wireguard')

  if (added === true) {
    toast.info(t('components.domain.access.wireguard-added.title'), {
      description: t('components.domain.access.wireguard-added.description')
    })
  } else if (added === false) {
    const current = (form.getFieldValue('viewers') as string[] | undefined) ?? []
    form.setFieldValue('viewers', stripWireguardRequiringViewers(current))
    toast.error(t('components.domain.access.wireguard-warning.title'), {
      description: t('components.domain.access.wireguard-warning.no-permission-description')
    })
  }
})

// --- Credentials conditional visibility ---

const showCredentials = computed(() => {
  // Match Vue 2 behavior: credentials only meaningful for RDP viewers or bastion
  return hasRdpViewer.value || (props.showBastionConfig && bastionEnabled.value)
})

const bastionFormRef = ref<InstanceType<typeof BastionConfigForm>>()

const getFormData = () => {
  const viewersArray = form.getFieldValue('viewers') as string[]
  // Convert viewers array to object format required by API
  const viewersObject = viewersArray.reduce(
    (acc, viewer) => {
      acc[viewer] = { options: null }
      return acc
    },
    {} as Record<string, { options: Record<string, any> | null }>
  )

  const data: any = {
    credentials: form.getFieldValue('credentials'),
    fullscreen: form.getFieldValue('fullscreen'),
    viewers: viewersObject
  }
  if (props.showBastionConfig) {
    data.bastion = bastionFormRef.value?.getFormData()
  }
  return data
}

const isFormValid = form.useStore((state) => state.isValid)

// The bastion sub-form (ports, ssh keys, etc.) has its own tanstack-form
// instance and validity, separate from this component's own form — combine
// both so a Save button gated on `isValid` also blocks on an invalid
// bastion port/key instead of letting it slip through.
const isValid = computed(() => {
  if (!props.showBastionConfig) return isFormValid.value
  return isFormValid.value && (bastionFormRef.value?.isValid ?? true)
})

defineExpose({
  getFormData,
  isValid
})

const showPassword = ref(false)
</script>
<template>
  <template
    v-if="
      (props.templateId && templateLoading) || (props.desktopId && desktopLoading) || props.loading
    "
  >
    <div class="flex flex-col gap-2">
      <Skeleton class="h-10 w-32" />
      <Skeleton class="h-10 w-32" />
    </div>
  </template>
  <template v-else>
    <FieldGroup>
      <section
        v-if="showCredentials"
        class="grid gap-1.5 items-start border-b border-gray-300 pb-7 md:grid-cols-[280px_1FR] md:gap-0"
      >
        <div class="flex flex-row-reverse justify-end items-center gap-2.5">
          <h4 class="text-lg font-semibold text-gray-warm-900">
            {{ t('components.domain.access.sections.credentials') }}
          </h4>
          <Icon name="key-01" />
        </div>
        <div class="grid grid-cols-1 gap-2.5 md:gap-5 md:w-auto md:grid-cols-2">
          <form.Field v-slot="{ field }" name="credentials.username">
            <div class="flex flex-col gap-2">
              <FieldLabel>{{
                t('components.domain.access.credentials.username.label')
              }}</FieldLabel>
              <FieldContent>
                <InputField
                  :id="field.name"
                  :name="field.name"
                  :model-value="field.state.value"
                  type="text"
                  :placeholder="t('components.domain.access.credentials.username.placeholder')"
                  @update:model-value="(value) => field.handleChange(String(value))"
                />
              </FieldContent>
              <FieldError :errors="field.state.meta.errors" />
            </div>
          </form.Field>
          <form.Field v-slot="{ field }" name="credentials.password">
            <div class="flex flex-col gap-2">
              <FieldLabel>{{
                t('components.domain.access.credentials.password.label')
              }}</FieldLabel>
              <FieldContent>
                <div class="relative">
                  <InputField
                    :id="field.name"
                    :name="field.name"
                    :model-value="field.state.value"
                    :type="showPassword ? 'text' : 'password'"
                    :placeholder="t('components.domain.access.credentials.password.placeholder')"
                    @update:model-value="(value) => field.handleChange(String(value))"
                  />
                  <Button
                    hierarchy="link-color"
                    class="absolute right-3 top-1/2 -translate-y-1/2"
                    @click="showPassword = !showPassword"
                  >
                    <Icon :name="showPassword ? 'eye-off' : 'eye'" />
                  </Button>
                </div>
                <FieldDescription class="text-brand-600">
                  {{ t('components.domain.access.credentials.password.help') }}
                </FieldDescription>
              </FieldContent>
              <FieldError :errors="field.state.meta.errors" />
            </div>
          </form.Field>
        </div>
      </section>
      <section
        class="grid gap-1.5 items-start border-b border-gray-300 pb-7 md:m-0 md:grid-cols-[280px_1FR] md:gap-0"
      >
        <div class="flex flex-row-reverse items-center gap-2.5 justify-end">
          <h4 class="text-lg font-semibold text-gray-warm-900">
            {{ t('components.domain.access.sections.viewers') }}
          </h4>
          <Icon name="monitor" />
        </div>
        <div class="flex flex-col gap-2.5 md:gap-5 md:w-auto">
          <form.Field v-slot="{ field }" name="fullscreen">
            <div class="flex gap-3">
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger as-child>
                    <FieldLabel>
                      {{ t('components.domain.access.fullscreen.label') }}
                      <Icon name="info-circle" size="xs" class="inline-block" />
                    </FieldLabel>
                  </TooltipTrigger>
                  <TooltipContent
                    :title="t('components.domain.access.fullscreen.label')"
                    :subtitle="t('components.domain.access.fullscreen.description')"
                  />
                </Tooltip>
              </TooltipProvider>
              <FieldContent>
                <Switch
                  :id="field.name"
                  type="checkbox"
                  :name="field.name"
                  :model-value="field.state.value"
                  @update:model-value="field.handleChange"
                />
              </FieldContent>
            </div>
            <FieldError :errors="field.state.meta.errors" />
          </form.Field>
          <form.Field v-slot="{ field }" name="viewers">
            <FieldContent>
              <ViewersSelector
                :model-value="field.state.value"
                @update:model-value="(value) => field.handleChange(value)"
              />
            </FieldContent>
            <FieldError :errors="field.state.meta.errors" />
          </form.Field>
          <Alert v-if="removedViewerLabels.length" variant="default" class="border-error-600">
            <FeaturedIconOutline kind="outline" color="error" />
            <AlertTitle>{{ t('components.domain.access.viewers-removed.title') }}</AlertTitle>
            <AlertDescription>
              {{ t('components.domain.access.viewers-removed.description') }}
              <ul class="mt-3 space-y-1">
                <li
                  v-for="label in removedViewerLabels"
                  :key="label"
                  class="text-sm font-semibold text-error-600"
                >
                  {{ label }}
                </li>
              </ul>
            </AlertDescription>
          </Alert>
        </div>
      </section>
      <BastionConfigForm
        v-if="showBastionConfig"
        ref="bastionFormRef"
        :bastion="bastion"
        :show-custom-domains="showCustomDomains"
        :hardware-interfaces="props.hardwareInterfaces"
        :on-request-add-interface="props.onRequestAddInterface"
        @bastion-enabled="handleBastionEnabled"
      />
    </FieldGroup>
  </template>
</template>
