<script setup lang="ts">
import { computed, reactive, ref, toRaw, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { useForm } from '@tanstack/vue-form'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import * as z from 'zod'

import type { CreateDesktopRequest, CreateDictResponse, ErrorResponse } from '@/gen/oas/apiv4'
import type { DeploymentEditRequest } from '@/gen/oas/apiv4/'
import {
  editDeploymentMutation,
  getDeploymentAllowedQueryKey,
  getDeploymentInfoOptions,
  getUserQuotasOptions,
  getTemplateInfoOptions
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'

import { isInvalid } from '@/lib/utils'
import {
  toDomainHardware,
  toGuestProperties,
  toReservables,
  type AccessFormData,
  type HardwareFormData
} from '@/lib/domainPayload'

import EditHardwareModal from '@/components/deployments/deployment-edit-hardware/EditHardwareModal.vue'
import { NewDeploymentDesktopFormCard } from '@/components/deployments/new-deployment-desktop-from-card'
import {
  DeploymentFormSkeleton,
  missingFieldLabels,
  NewDeploymentForm
} from '@/components/deployments/new-deployment-form'
import { FormHeader, type FormHeaderTooltip } from '@/components/form-header'
import { Icon } from '@/components/icon'
import { FeaturedIconOutline } from '@/components/icon/featured-outline'
import { Modal } from '@/components/modal'
import AlertModal from '@/components/modal/AlertModal.vue'
import { type StepperFormStep } from '@/components/stepper-form'
import TemplatesList from '@/components/templates/TemplatesList.vue'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { FieldError } from '@/components/ui/field'
import Separator from '@/components/ui/separator/Separator.vue'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'

// --------------------------------------------------------------

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const queryClient = useQueryClient()

const {
  data: userQuotas,
  isPending: userQuotasIsPending,
  isError: userQuotasIsError
} = useQuery(getUserQuotasOptions())

const {
  data: deploymentInfo,
  isPending: deploymentInfoIsPending,
  error: deploymentInfoError
} = useQuery({
  ...getDeploymentInfoOptions({
    path: {
      deployment_id: route.params.deploymentId as string
    }
  }),
  retry: (failureCount, error) =>
    (error as ErrorResponse)?.error !== 'not_found' && failureCount < 3
})

watch(
  deploymentInfoError,
  (error) => {
    if ((error as ErrorResponse | null)?.error !== 'not_found') return
    router.push({ name: 'error', params: { code: '404' } })
  },
  { immediate: true }
)

const { mutateAsync: getTemplateInfoAsync } = useMutation({
  mutationFn: async (templateId: string) => {
    const data = await queryClient.fetchQuery(
      getTemplateInfoOptions({
        path: {
          template_id: templateId
        },
        throwOnError: true
      })
    )
    return data
  }
})

const formHeaderRef = ref<InstanceType<typeof FormHeader> | null>(null)

const {
  mutateAsync: editDeploymentAsync,
  isPending: editDeploymentIsPending,
  error: editDeploymentError,
  variables: editDeploymentVariables
} = useMutation({
  ...editDeploymentMutation(),

  onSuccess: (_data, variables) => {
    queryClient.removeQueries({
      queryKey: getDeploymentAllowedQueryKey({
        path: { deployment_id: variables.path.deployment_id }
      })
    })
    formHeaderRef.value?.allowLeave()
    router.push({
      name: 'deployments'
      // TODO: single deployment view
      // params: { deploymentId: data.id }
    })
  },
  onError: (error) => {
    const errorResponse = error as ErrorResponse

    // Handle field errors
    switch (errorResponse.description_code) {
      case 'duplicated_name':
        form.getFieldInfo('name').instance?.setErrorMap({
          onSubmit: t('components.deployments.form-sections.info.fields.name.errors.exists')
        })
        currentStep.value = 1
        break

      case 'new_desktop_name_exists': {
        const desktops = form.getFieldValue('desktops') || []

        desktops.forEach((desktop, index) => {
          if (desktop.name === errorResponse.params?.name) {
            form.getFieldInfo(`desktops[${index}].name`)?.instance?.setErrorMap({
              onSubmit: t(
                'components.deployments.form-desktop-card.sections.preview.fields.name.errors.exists'
              )
            })
          }
        })
        currentStep.value = 2
        break
      }

      default:
        break
    }
  }
})

const formSchema = z.object({
  name: z
    .string()
    .trim()
    .min(1, t('components.form.validation.required'))
    .min(4, t('components.form.validation.min-length', { min: 4 }))
    .max(50, t('components.form.validation.max-length', { max: 50 })),
  description: z
    .string()
    .trim()
    .max(255, t('components.form.validation.max-length', { max: 255 })),
  visible: z.boolean(),
  desktops: z
    .array(
      z.object({
        // template_id: z.string(),
        name: z
          .string()
          .trim()
          .min(1, t('components.form.validation.required'))
          .min(4, t('components.form.validation.min-length', { min: 4 }))
          .max(50, t('components.form.validation.max-length', { max: 50 })),
        description: z
          .string()
          .trim()
          .max(255, t('components.form.validation.max-length', { max: 255 }))
      })
    )
    .min(1, t('views.new-deployment.steps.select-desktops.errors.no-desktops'))
    .superRefine((items, ctx) => {
      const nameCount = items.reduce<Record<string, number[]>>((acc, item, index) => {
        const trimmed = item.name.trim().toLowerCase()
        if (!acc[trimmed]) acc[trimmed] = []
        acc[trimmed].push(index)
        return acc
      }, {})

      for (const indices of Object.values(nameCount)) {
        if (indices.length > 1) {
          for (const index of indices) {
            ctx.addIssue({
              code: 'custom',
              message: t('components.form.validation.unique'),
              path: [index, 'name']
            })
          }
        }
      }
    }),
  coOwners: z.array(z.string()),
  alloweds: z
    .object({
      groups: z.union([z.boolean(), z.array(z.string())]).default(false),
      users: z.union([z.boolean(), z.array(z.string())]).default(false)
    })
    .refine(
      ({ groups, users }) =>
        (Array.isArray(groups) && groups.length > 0) || (Array.isArray(users) && users.length > 0),
      { message: t('components.deployments.form-sections.alloweds.required') }
    ),
  permissions: z.object({
    recreate: z.boolean()
  }),
  image: z.object({
    id: z.string(),
    type: z.enum(['stock', 'custom']),
    url: z.string()
  })
})

const toMediaResources = (media?: (string | { id: string; name?: string | null })[] | null) =>
  media?.map((m) =>
    typeof m === 'string' ? { id: m, name: m } : { id: m.id, name: m.name ?? m.id }
  )

const toInterfaceIds = (interfaces?: (string | { id: string })[] | null) =>
  interfaces?.map((iface) => (typeof iface === 'string' ? iface : iface.id))

const toFormDesktop = (desktop: CreateDictResponse) => ({
  ...desktop,
  hardware: {
    ...desktop.hardware,
    interfaces: toInterfaceIds(desktop.hardware?.interfaces)
  }
})

const savedDesktops = computed(
  () =>
    new Map(
      (deploymentInfo.value?.create_dict ?? []).map((desktop) => [
        desktop.tag_desktop_id,
        toFormDesktop(desktop)
      ])
    )
)

const desktopOriginals = ref(new Map<string, any>())

const form = useForm({
  defaultValues: reactive({
    name: computed(() => deploymentInfo.value?.name || ''),
    description: computed(() => deploymentInfo.value?.description || ''),
    visible: computed(() => deploymentInfo.value?.tag_visible ?? true),

    desktops: computed(() => deploymentInfo.value?.create_dict.map(toFormDesktop) || []),

    image: computed(
      () =>
        deploymentInfo.value?.image || {
          id: '1',
          type: 'stock',
          url: `/assets/img/desktops/stock/1.jpg`
        }
    ),

    permissions: computed(() => ({
      recreate: deploymentInfo.value?.user_permissions?.includes('recreate') || false
    })),
    coOwners: computed(() => deploymentInfo.value?.co_owners || []),
    alloweds: computed(() => deploymentInfo.value?.allowed || { users: false, groups: false })
  }),
  validators: {
    onChange: formSchema
  },
  onSubmit: ({ value }) => {
    const submitBody: DeploymentEditRequest = {
      name: value.name,
      description: value.description,
      image: value.image,
      visible: value.visible,

      // co_owners: value.coOwners,

      user_permissions: [...(value.permissions.recreate ? ['recreate'] : [])] as 'recreate'[],

      allowed: {
        users: value.alloweds.users,
        groups: value.alloweds.groups
      },

      resources: []
    }

    // iterate between the desktops and separate them into create, update and delete lists
    submitBody.desktops_to_delete = deploymentInfo.value?.create_dict
      .filter((d) => !value.desktops.some((sd) => sd.tag_desktop_id === d.tag_desktop_id))
      .map((d) => d.tag_desktop_id)

    submitBody.desktops_to_create = value.desktops
      .filter(
        (d) =>
          !deploymentInfo.value?.create_dict.some((od) => od.tag_desktop_id === d.tag_desktop_id)
      )
      .map((d) => {
        const { tag_desktop_id, ...desktopData } = d
        return {
          ...desktopData,
          hardware: {
            ...desktopData.hardware,
            interfaces: desktopData.hardware?.interfaces?.map((iface: string | { id: string }) =>
              typeof iface === 'string' ? iface : iface.id
            ),
            isos: toMediaResources(desktopData.hardware?.isos),
            floppies: toMediaResources(desktopData.hardware?.floppies)
          }
        } as CreateDesktopRequest
      })

    // TODO: avoid sending unchanged desktops and fields
    submitBody.desktops_to_edit = value.desktops
      .filter((d) =>
        deploymentInfo.value?.create_dict.some((od) => od.tag_desktop_id === d.tag_desktop_id)
      )
      .map((d) => ({
        ...d,
        hardware: {
          ...d.hardware,
          interfaces: d.hardware?.interfaces?.map((iface: string | { id: string }) =>
            typeof iface === 'string' ? iface : iface.id
          ),
          isos: toMediaResources(d.hardware?.isos),
          floppies: toMediaResources(d.hardware?.floppies)
        }
      }))

    editDeploymentAsync({
      path: {
        deployment_id: route.params.deploymentId as string
      },
      body: submitBody
    })
  }
})

// Reactively get field metadata from the form to track errors per step
const formFieldMeta = form.useStore((state) => state.fieldMeta)
const formValues = form.useStore((state) => state.values)
const formIsValid = form.useStore((state) => state.isValid)
const formIsSubmitting = form.useStore((state) => state.isSubmitting)
const formIsTouched = form.useStore((state) => !state.isDefaultValue)

const saveButtonTooltip = computed<FormHeaderTooltip | undefined>(() => {
  if (formIsValid.value || deploymentInfoIsPending.value) return undefined

  const fields = missingFieldLabels(formSchema.safeParse(formValues.value).error?.issues ?? [], t)
  if (!fields.length) return undefined

  return {
    title: t('components.deployments.missing-fields.title'),
    description: fields.join(', ')
  }
})

async function desktopFromTemplate(templateId: string, name: string) {
  const {
    id: _,
    hardware: {
      interfaces: templateInterfaces,
      isos: templateIsos,
      floppies: templateFloppies,
      ...templateHardware
    },
    ...templateData
  } = await getTemplateInfoAsync(templateId)

  return {
    ...templateData,
    hardware: {
      ...templateHardware,
      interfaces: toInterfaceIds(templateInterfaces),
      isos: toMediaResources(templateIsos),
      floppies: toMediaResources(templateFloppies)
    },

    tag_desktop_id: `${Date.now()}-${Math.random()}`,
    template_id: templateId,
    name
  }
}

const rememberOriginal = (desktop: { tag_desktop_id: string }) => {
  desktopOriginals.value.set(desktop.tag_desktop_id, structuredClone(toRaw(desktop)))
}

async function addDesktop(templateId: string) {
  const desktop = await desktopFromTemplate(templateId, '')
  rememberOriginal(desktop)

  const currentDesktops = form.getFieldValue('desktops') || []
  form.setFieldValue('desktops', [...currentDesktops, desktop])
}

async function updateDesktopTemplate(templateId: string, index: number) {
  const currentDesktops = form.getFieldValue('desktops') || []
  const desktop = await desktopFromTemplate(templateId, currentDesktops[index].name)
  rememberOriginal(desktop)

  form.setFieldValue('desktops', [
    ...currentDesktops.slice(0, index),
    desktop,
    ...currentDesktops.slice(index + 1)
  ])
}

interface SelectTemplateModalData {
  type: 'add' | 'replace'
  action: (templateId: string) => void
  desktopName?: string
}
const selectTemplateModalData = ref<SelectTemplateModalData | null>(null)

const updateHardware = (
  index: number,
  access: AccessFormData | undefined,
  hardware: HardwareFormData | undefined
) => {
  const currentDesktops = form.getFieldValue('desktops') || []

  const restoredViewers = access?.viewers ?? {}

  const updatedDesktop = {
    ...currentDesktops[index],
    removed_viewers: (currentDesktops[index].removed_viewers ?? []).filter(
      (viewer: string) => !(viewer in restoredViewers)
    ),
    guest_properties: {
      ...currentDesktops[index].guest_properties,
      ...toGuestProperties(access)
    },
    hardware: {
      ...currentDesktops[index].hardware,
      ...toDomainHardware(hardware)
    },
    reservables: toReservables(hardware)
  }

  const newDesktops = [
    ...currentDesktops.slice(0, index),
    updatedDesktop,
    ...currentDesktops.slice(index + 1)
  ]
  form.setFieldValue('desktops', newDesktops)

  updateHardwareModalData.value = null
}

const updateHardwareModalData = ref<{
  index: number
  data: any
  original: any
} | null>(null)

const openHardwareModal = (index: number, desktop: { tag_desktop_id: string }) => {
  const id = desktop.tag_desktop_id
  updateHardwareModalData.value = {
    index,
    data: desktop,
    original: desktopOriginals.value.get(id) ?? savedDesktops.value.get(id) ?? null
  }
}

const deleteDesktop = (index: number) => {
  const currentDesktops = form.getFieldValue('desktops') || []
  desktopOriginals.value.delete(currentDesktops[index].tag_desktop_id)

  const newDesktops = [...currentDesktops.slice(0, index), ...currentDesktops.slice(index + 1)]
  form.setFieldValue('desktops', newDesktops)

  deleteDesktopConfirmationModalData.value = null
}

const deleteDesktopConfirmationModalData = ref<{
  index: number
  name: string
} | null>(null)

const steps = computed<(StepperFormStep & { icon: string })[]>(() => {
  const fieldMeta = formFieldMeta.value
  return [
    {
      step: 1,
      title: t('views.new-deployment.steps.configuration.title'),
      icon: 'settings-01',
      destructive: hasFieldErrors(fieldMeta, step1Fields)
    },
    {
      step: 2,
      title: t('views.new-deployment.steps.select-desktops.title'),
      icon: 'monitor-02',
      destructive: hasFieldErrors(fieldMeta, step2Fields)
    }
  ]
})

const currentStep = ref(1)

const step1Fields = ['name', 'description', 'visible', 'alloweds']
const step2Fields = ['desktops']

// Helper to check if any field in a list has errors (touched + invalid)
function hasFieldErrors(
  fieldMeta: Record<string, { isTouched: boolean; errors: any[] } | undefined>,
  fieldPrefixes: string[]
): boolean {
  return Object.entries(fieldMeta).some(([fieldName, meta]) => {
    const matchesStep = fieldPrefixes.some(
      (prefix) =>
        fieldName === prefix ||
        fieldName.startsWith(`${prefix}[`) ||
        fieldName.startsWith(`${prefix}.`)
    )
    return matchesStep && meta?.isTouched && meta?.errors && meta.errors.length > 0
  })
}
</script>

<template>
  <!-- select template modal -->
  <Modal
    v-if="selectTemplateModalData !== null"
    :open="selectTemplateModalData !== null"
    size="7xl"
    :title="
      t(`components.deployments.form-select-template-modal.${selectTemplateModalData.type}.title`, {
        'desktop-name': selectTemplateModalData.desktopName
      })
    "
    :description="
      t(
        `components.deployments.form-select-template-modal.${selectTemplateModalData.type}.description`,
        {
          'desktop-name': selectTemplateModalData.desktopName
        }
      )
    "
    @close="selectTemplateModalData = null"
  >
    <Alert
      v-if="selectTemplateModalData.type === 'replace'"
      variant="destructive"
      class="max-w-256 w-full mx-auto mb-6"
    >
      <FeaturedIconOutline kind="outline" color="error" />

      <AlertTitle class="font-bold text-gray-warm-700 mb-2">{{
        t('components.deployments.form-select-template-modal.replace.alert.title')
      }}</AlertTitle>
      <AlertDescription>{{
        t('components.deployments.form-select-template-modal.replace.alert.description')
      }}</AlertDescription>
    </Alert>

    <TemplatesList
      active-template-tab="user"
      selectable
      :page-size="5"
      :pagination-page-sizes="[5, 10, 20, 30, 40, 50]"
      @row-click="
        (template) => {
          selectTemplateModalData!.action(template.id)
          selectTemplateModalData = null
        }
      "
    />

    <template #footer>
      <Button hierarchy="link-gray" class="mr-auto" @click="selectTemplateModalData = null">
        {{ t('components.deployments.form-select-template-modal.cancel') }}
      </Button>
    </template>
  </Modal>

  <!-- Delete Desktop Confirmation Modal -->
  <AlertModal
    :open="deleteDesktopConfirmationModalData !== null"
    level="danger"
    size="lg"
    :title="
      t('components.deployments.form-delete-desktop-modal.title', {
        'desktop-name': deleteDesktopConfirmationModalData?.name
      })
    "
    :description="t('components.deployments.form-delete-desktop-modal.description')"
    @close="deleteDesktopConfirmationModalData = null"
  >
    <template #footer>
      <Button hierarchy="link-gray" @click="deleteDesktopConfirmationModalData = null">
        {{ t('components.deployments.form-delete-desktop-modal.cancel') }}
      </Button>
      <Button
        hierarchy="destructive"
        @click="deleteDesktop(deleteDesktopConfirmationModalData!.index)"
      >
        {{ t('components.deployments.form-delete-desktop-modal.confirm') }}
      </Button>
    </template>
  </AlertModal>

  <!-- hardware modal -->
  <EditHardwareModal
    v-if="updateHardwareModalData !== null"
    :open="updateHardwareModalData !== null"
    :data="updateHardwareModalData?.data"
    :original="updateHardwareModalData?.original"
    @close="updateHardwareModalData = null"
    @submit="
      ({ access, hardware }) => {
        updateHardware(updateHardwareModalData!.index, access, hardware)
      }
    "
  />

  <FormHeader
    ref="formHeaderRef"
    :cancel-to="{ name: 'deployments' }"
    :cancel-label="t('components.form-header.cancel-edit')"
    :confirm-cancel="formIsTouched"
    :next-label="t('views.edit-deployment.header.save')"
    :next-disabled="!formIsValid || deploymentInfoIsPending"
    :next-pending="formIsSubmitting || editDeploymentIsPending"
    :next-tooltip="saveButtonTooltip"
    @next="form.handleSubmit"
  >
    <template #stepper>
      <div class="shrink-0">
        <ToggleGroup
          v-model="currentStep"
          :spacing="1"
          type="single"
          size="default"
          class="bg-base-white border border-1-5 border-gray-warm-300 p-1 rounded-lg"
        >
          <!-- TODO: using tabs would be better here -->
          <ToggleGroupItem
            v-for="step in steps"
            :key="step.step"
            :value="step.step"
            variant="gray-warm"
            :class="{
              'ring-sm ring-error-200! data-[state=off]:text-error-600!': step.destructive
            }"
          >
            <Icon :name="step.icon" size="sm" stroke-color="currentColor" aria-hidden="true" />
            {{ step.title }}
          </ToggleGroupItem>
        </ToggleGroup>
      </div>
    </template>
  </FormHeader>

  <main
    v-if="deploymentInfoIsPending || deploymentInfoError"
    class="max-w-320 w-full mx-auto flex flex-col"
  >
    <DeploymentFormSkeleton />
  </main>

  <main v-else class="max-w-320 w-full mx-auto flex flex-col gap-6">
    <!-- TODO: try to deduplicate `createDeploymentError as ErrorResponse` -->
    <Alert
      v-if="(editDeploymentError as ErrorResponse)?.description_code"
      variant="destructive"
      class="max-w-256 w-full mx-auto"
    >
      <FeaturedIconOutline kind="outline" color="error" />

      <AlertTitle class="font-bold text-gray-warm-700 mb-2">{{
        t(
          `api.edit-deployment.errors.${(editDeploymentError as ErrorResponse).description_code}.title`,
          t('api.edit-deployment.errors.generic.title')
        )
      }}</AlertTitle>

      <AlertDescription>
        <i18n-t
          v-if="
            ['new_desktop_name_exists', 'duplicated_name'].includes(
              (editDeploymentError as ErrorResponse).description_code
            )
          "
          :keypath="`api.edit-deployment.errors.${(editDeploymentError as ErrorResponse).description_code}.description`"
          class="whitespace-pre-wrap"
        >
          <template #desktop_name>
            <strong>{{ (editDeploymentError as ErrorResponse)?.params?.name }}</strong>
          </template>
          <template #deployment_name>
            <strong>{{ editDeploymentVariables?.body.name }}</strong>
          </template>
        </i18n-t>
        <template v-else>
          {{
            t(
              `api.edit-deployment.errors.${(editDeploymentError as ErrorResponse).description_code}.description`,
              t('api.edit-deployment.errors.generic.description')
            )
          }}
        </template>

        <ul
          v-if="(editDeploymentError as ErrorResponse)?.params?.users"
          class="list-disc list-inside"
        >
          <li v-for="user in (editDeploymentError as ErrorResponse)?.params?.users" :key="user">
            {{ user }}
          </li>
        </ul>
      </AlertDescription>
    </Alert>

    <template v-if="currentStep === 1">
      <NewDeploymentForm
        :form="form"
        :show-create-owner-desktop="false"
        :deployment-id="route.params.deploymentId as string"
        @submit="form.handleSubmit"
      />
    </template>
    <template v-else-if="currentStep === 2">
      <div class="flex flex-col gap-10">
        <form.Subscribe v-slot="{ values }">
          <template v-for="(desktop, index) in values.desktops" :key="desktop.tag_desktop_id">
            <NewDeploymentDesktopFormCard
              :index="index"
              :form="form"
              :open="true"
              :auto-focus="!desktop.name || index === 0"
              @change-template="
                selectTemplateModalData = {
                  type: 'replace',
                  // TODO: update the typing of action to only be a function
                  action: (templateId: string) => updateDesktopTemplate(templateId, index),
                  desktopName: desktop.name || (index + 1).toString()
                }
              "
              @delete-desktop="
                () => {
                  // deleteDesktop(index)
                  deleteDesktopConfirmationModalData = {
                    index,
                    name: values.desktops[index].name || (index + 1).toString()
                  }
                }
              "
              @update-hardware="
                () => {
                  openHardwareModal(index, values.desktops[index])
                }
              "
            />

            <Separator v-if="index < values.desktops.length - 1" />
          </template>

          <form.Field v-slot="{ field }" name="desktops">
            <div class="flex flex-col items-center justify-center gap-2">
              <div class="flex flex-row items-center justify-center gap-6 shrink-0 w-full">
                <Separator />
                <Button
                  hierarchy="secondary-gray"
                  icon="plus"
                  :disabled="
                    userQuotasIsPending ||
                    userQuotasIsError ||
                    (userQuotas?.quota &&
                      userQuotas.quota.deployment_desktops <= values.desktops.length)
                  "
                  :class="{
                    'border-error-300! ring-error-200!': isInvalid(field)
                  }"
                  @click="
                    selectTemplateModalData = {
                      type: 'add',
                      action: addDesktop
                    }
                  "
                  >{{
                    t(
                      `views.new-deployment.steps.select-desktops.add-desktop${userQuotas?.quota ? '-max' : ''}`,
                      {
                        current: values.desktops.length,
                        max: userQuotas?.quota ? userQuotas.quota.deployment_desktops : ''
                      }
                    )
                  }}</Button
                >
                <Separator />
              </div>

              <FieldError v-if="isInvalid(field)" :errors="field.state.meta.errors.flat()" />
            </div>
          </form.Field>
        </form.Subscribe>
      </div>
    </template>
  </main>
</template>
