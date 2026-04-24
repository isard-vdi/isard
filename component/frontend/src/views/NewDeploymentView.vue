<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter, RouterLink } from 'vue-router'
import { useI18n } from 'vue-i18n'

import { isInvalid } from '@/lib/utils'
import { QUOTA_STALE_TIME } from '@/lib/constants'

import { useForm } from '@tanstack/vue-form'
import * as z from 'zod'

import { useQuery, useMutation } from '@tanstack/vue-query'

import type { CreateDesktopRequest, ErrorResponse } from '@/gen/oas/apiv4'
import {
  getTemplateInfoApiV4ItemTemplateTemplateIdGetInfoGet,
  getTemplateDetailsApiV4ItemTemplateTemplateIdGetDetailsGet
} from '@/gen/oas/apiv4'
import {
  createDeploymentApiV4ItemDeploymentPostMutation,
  getUserQuotasApiV4ItemUserGetQuotasGetOptions,
  checkQuotaNewDeploymentApiV4QuotaDeploymentNewGetOptions
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'

import { Button } from '@/components/ui/button'
import { NewDeploymentForm } from '@/components/deployments/new-deployment-form'
import { StepperForm, type StepperFormStep } from '@/components/stepper-form'
import { DomainInfoModal } from '@/components/desktops'

import { NewDeploymentDesktopFormCard } from '@/components/deployments/new-deployment-desktop-from-card'
import { Modal, QuotaExceededModal } from '@/components/modal'
import TemplatesList from '@/components/templates/TemplatesList.vue'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { FieldError } from '@/components/ui/field'
import { FeaturedIconOutline } from '@/components/icon/featured-outline'
import Separator from '@/components/ui/separator/Separator.vue'
import AlertModal from '@/components/modal/AlertModal.vue'
import EditHardwareModal from '@/components/deployments/deployment-edit-hardware/EditHardwareModal.vue'

const router = useRouter()
const { t, d } = useI18n()

const currentStep = ref(1)

const deploymentQuotaQuery = useQuery({
  ...checkQuotaNewDeploymentApiV4QuotaDeploymentNewGetOptions(),
  staleTime: QUOTA_STALE_TIME,
  retry: false
})

const quotaCheckPassed = computed(() => deploymentQuotaQuery.isSuccess.value)

// TODO: get only the needed quotas
const {
  data: userQuotas,
  isPending: userQuotasIsPending,
  isError: userQuotasIsError,
  error: userQuotasError
} = useQuery(getUserQuotasApiV4ItemUserGetQuotasGetOptions())

const {
  mutate: createDeployment,
  mutateAsync: createDeploymentAsync,
  isPending: createDeploymentIsPending,
  isError: createDeploymentIsError,
  error: createDeploymentError,
  data: createDeploymentData,
  variables: createDeploymentVariables
} = useMutation({
  ...createDeploymentApiV4ItemDeploymentPostMutation(),
  onSuccess: (data) => {
    router.push({
      name: 'deployments',
      params: { deploymentId: data.id }
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

const {
  mutate: getTemplateInfo,
  mutateAsync: getTemplateInfoAsync,
  isPending: getTemplateInfoIsPending,
  isError: getTemplateInfoIsError,
  error: getTemplateInfoError,
  data: getTemplateInfoData
} = useMutation({
  mutationFn: async (templateId: string) => {
    const { data } = await getTemplateInfoApiV4ItemTemplateTemplateIdGetInfoGet({
      path: {
        template_id: templateId
      },
      throwOnError: true
    })
    return data
  }
})

// Template Info Modal
const showTemplateInfoModal = ref(false)
const {
  mutate: fetchAndOpenTemplateInfoModal,
  isPending: fetchTemplateDetailsIsPending,
  isError: fetchTemplateDetailsIsError,
  error: fetchTemplateDetailsError,
  data: templateDetails,
  variables: templateDetailsDesktopId,
  reset: resetTemplateDetails
} = useMutation({
  mutationFn: async (templateId: string) => {
    const { data } = await getTemplateDetailsApiV4ItemTemplateTemplateIdGetDetailsGet({
      path: {
        template_id: templateId
      },
      throwOnError: true
    })
    return data
  },
  onSuccess: () => {
    showTemplateInfoModal.value = true
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
        template_id: z.string(),
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
  createOwnerDesktop: z.boolean(),
  permissions: z.object({
    recreate: z.boolean()
  }),
  image: z.object({
    id: z.string(),
    type: z.enum(['stock', 'custom']),
    // url: z.httpUrl()
    url: z.string()
  })
})

// Step-specific schemas for direct validation (independent of touch state)
const step2Schema = formSchema.pick({
  name: true,
  description: true,
  visible: true,
  image: true,
  createOwnerDesktop: true,
  coOwners: true,
  permissions: true
})
const step4Schema = formSchema.pick({ desktops: true })

// hardcoded random image from stock images
const deploymentImageId = (Math.floor(Math.random() * 48) + 1).toString()

const form = useForm({
  defaultValues: {
    name: '',
    description: '',
    visible: true,

    desktops: [] as (CreateDesktopRequest & { _id: any })[],

    image: {
      id: deploymentImageId,
      type: 'stock',
      url: `/assets/img/desktops/stock/${deploymentImageId}.jpg`
    },

    createOwnerDesktop: false,
    permissions: {
      recreate: false
    },
    coOwners: [] as string[]
  },
  validators: {
    onChange: formSchema
  },
  onSubmit: ({ value }) => {
    createDeploymentAsync({
      body: {
        name: value.name,
        description: value.description,
        image: value.image,
        visible: value.visible,

        // desktops without the temporary id
        desktops: value.desktops.map(({ _id, ...desktop }) => desktop),

        create_owner_desktop: true,
        co_owners: [],

        user_permissions: [...(value.permissions.recreate ? ['recreate'] : [])] as 'recreate'[],

        allowed: {
          users: ['local-default-admin-admin'],
          groups: false
        },

        resources: []
      }
    })
  }
})

// Reactively get field metadata from the form to track errors per step
const formFieldMeta = form.useStore((state) => state.fieldMeta)
const formValues = form.useStore((state) => state.values)

// Define which form fields belong to each step
const step1Fields = ['name', 'description', 'visible']
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

// Check if the current step's fields pass validation (independent of touch state)
function isStepFieldsValid(step: number): boolean {
  const values = formValues.value
  switch (step) {
    case 1:
      return step2Schema.safeParse(values).success
    case 2:
      return step4Schema.safeParse(values).success
    default:
      return true
  }
}

const steps = computed<StepperFormStep[]>(() => {
  const fieldMeta = formFieldMeta.value
  return [
    {
      step: 1,
      title: t('views.new-deployment.steps.configuration.title'),
      destructive: hasFieldErrors(fieldMeta, step1Fields)
    },
    {
      step: 2,
      title: t('views.new-deployment.steps.select-desktops.title'),
      destructive: hasFieldErrors(fieldMeta, step2Fields)
    }
  ]
})

async function addDesktop(templateId: string) {
  const {
    id,
    hardware: {
      interfaces: templateInterfaces,
      isos: templateIsos,
      floppies: templateFloppies,

      ...templateHardware
    },
    ...templateData
  } = await getTemplateInfoAsync(templateId)

  const currentDesktops = form.getFieldValue('desktops') || []
  const newDesktops = [
    ...currentDesktops,
    {
      ...templateData,
      hardware: {
        ...templateHardware,
        interfaces: templateInterfaces.map((iface) =>
          typeof iface === 'string' ? iface : iface.id
        ),
        isos: templateIsos?.map((iso) => (typeof iso === 'string' ? iso : iso.id)),
        floppies: templateFloppies?.map((floppy) =>
          typeof floppy === 'string' ? floppy : floppy.id
        )
      },

      _id: `${Date.now()}-${Math.random()}`,
      template_id: templateId,
      name: ''
    }
  ]
  form.setFieldValue('desktops', newDesktops)
}

const deleteDesktop = (index: number) => {
  const currentDesktops = form.getFieldValue('desktops') || []
  const newDesktops = [...currentDesktops.slice(0, index), ...currentDesktops.slice(index + 1)]
  form.setFieldValue('desktops', newDesktops)

  deleteDesktopConfirmationModalData.value = null
}

async function updateDesktopTemplate(templateId: string, index: number) {
  const {
    id,
    hardware: { interfaces: templateInterfaces, ...templateHardware },
    ...templateData
  } = await getTemplateInfoAsync(templateId)

  const currentDesktops = form.getFieldValue('desktops') || []
  const newDesktops = [
    ...currentDesktops.slice(0, index),
    {
      ...templateData,
      hardware: {
        ...templateHardware,
        interfaces: templateInterfaces.map((iface) =>
          typeof iface === 'string' ? iface : iface.id
        )
      },

      _id: currentDesktops[index]._id,
      template_id: templateId,
      name: currentDesktops[index].name
    },
    ...currentDesktops.slice(index + 1)
  ]
  form.setFieldValue('desktops', newDesktops)
}

interface SelectTemplateModalData {
  type: 'add' | 'replace'
  action: (templateId: string) => void
  desktopName?: string
}
const selectTemplateModalData = ref<SelectTemplateModalData | null>(null)

const deleteDesktopConfirmationModalData = ref<{
  index: number
  name: string
} | null>(null)

const updateHardwareModalData = ref<{
  index: number
  data: CreateDesktopRequest | any
  restrictedFieldsDetails?: any
} | null>(null)

const updateHardware = (index: number, accessSettings: any, hardwareSettings: any) => {
  const currentDesktops = form.getFieldValue('desktops') || []

  // convert from camelCase to snake_case
  const { bootOrder, diskBus, reservables, interfaces, ...restHardwareSettings } = hardwareSettings

  const updatedDesktop = {
    ...currentDesktops[index],
    ...{ guest_properties: { ...currentDesktops[index].guest_properties, ...accessSettings } },
    ...{
      hardware: {
        ...currentDesktops[index].hardware,
        ...restHardwareSettings,
        interfaces: interfaces.map((iface: any) => (typeof iface === 'string' ? iface : iface.id)),
        disk_bus: diskBus,
        boot_order: bootOrder
      }
    },
    reservables
  }

  const newDesktops = [
    ...currentDesktops.slice(0, index),
    updatedDesktop,
    ...currentDesktops.slice(index + 1)
  ]
  form.setFieldValue('desktops', newDesktops)

  updateHardwareModalData.value = null
}
</script>

<template>
  <!-- Quota Exceeded Modal -->
  <QuotaExceededModal
    :open="deploymentQuotaQuery.isError.value"
    :title="t('components.deployments.quota-exceeded-modal.title')"
    :description="t('components.deployments.quota-exceeded-modal.description')"
    :cancel-label="t('components.deployments.quota-exceeded-modal.cancel')"
    :cancel-to="{ name: 'desktops' /* TODO: 'deployments' */ }"
  />

  <template v-if="quotaCheckPassed">
    <!-- select template modal -->
    <Modal
      v-if="selectTemplateModalData !== null"
      :open="selectTemplateModalData !== null"
      size="7xl"
      :title="
        t(
          `components.deployments.form-select-template-modal.${selectTemplateModalData.type}.title`,
          {
            'desktop-name': selectTemplateModalData.desktopName
          }
        )
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

      <DomainInfoModal
        :open="showTemplateInfoModal"
        :domain-id="templateDetailsDesktopId"
        :name="templateDetails?.name || ''"
        :description="templateDetails?.description"
        :vcpu="templateDetails?.vcpu"
        :ram="templateDetails?.memory"
        :boot-order="templateDetails?.boot_order.map((bo) => bo.name)"
        :disk-bus="templateDetails?.disk_bus"
        :vga="templateDetails?.videos.map((vga) => vga.name)"
        :viewers="templateDetails?.viewers"
        :isos="templateDetails?.isos?.map((iso) => iso.name)"
        :reservables="templateDetails?.reservables?.vgpus"
        :kind="'template'"
        @close="
          () => {
            showTemplateInfoModal = false
            resetTemplateDetails()
          }
        "
      />

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
        @show-info-modal="fetchAndOpenTemplateInfoModal"
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
      :restricted-fields-details="updateHardwareModalData?.restrictedFieldsDetails"
      @close="updateHardwareModalData = null"
      @submit="
        ({ accessSettings, hardwareSettings }) => {
          updateHardware(updateHardwareModalData!.index, accessSettings, hardwareSettings)
        }
      "
    />

    <div
      class="flex flex-col md:flex-row items-start justify-center max-w-480 w-full mx-auto mb-8 gap-4"
    >
      <div class="flex flex-row items-center gap-4 w-full">
        <Button
          :as="RouterLink"
          :to="{ name: 'deployments' }"
          hierarchy="link-color"
          icon="arrow-left"
        >
          {{ t('views.new-deployment.header.cancel') }}
        </Button>
      </div>

      <div class="shrink-0 _w-160 w-80">
        <StepperForm
          v-model="currentStep"
          :steps="steps"
          :disable-future-steps="!isStepFieldsValid(currentStep)"
        />
      </div>

      <div class="flex flex-row items-center justify-end gap-4 w-full">
        <Button
          hierarchy="link-color"
          :disabled="currentStep <= 1"
          @click="
            () => {
              if (currentStep > 1) {
                currentStep -= 1
              }
            }
          "
        >
          {{ t('views.new-deployment.header.previous') }}
        </Button>

        <form.Subscribe v-slot="{ isValid, isSubmitting, isTouched }">
          <Button
            v-if="currentStep === steps.length"
            class="min-w-32"
            type="submit"
            :disabled="!isValid || !isTouched || isSubmitting || createDeploymentIsPending"
            :icon="isSubmitting || createDeploymentIsPending ? 'loading-02' : ''"
            icon-class="motion-safe:animate-[spin_2s_linear_infinite]"
            @click="form.handleSubmit"
            >{{ t('views.new-deployment.header.create-deployment') }}</Button
          >
          <Button
            v-else
            class="min-w-32"
            :disabled="!isStepFieldsValid(currentStep)"
            @click="
              () => {
                if (currentStep < steps.length) {
                  currentStep += 1
                }
              }
            "
            >{{ t('views.new-deployment.header.next') }}</Button
          >
        </form.Subscribe>
      </div>
    </div>
    <main class="max-w-320 w-full mx-auto flex flex-col gap-[24px]">
      <!-- TODO: try to deduplicate `createDeploymentError as ErrorResponse` -->
      <Alert
        v-if="(createDeploymentError as ErrorResponse)?.description_code"
        variant="destructive"
        class="max-w-256 w-full mx-auto"
      >
        <FeaturedIconOutline kind="outline" color="error" />

        <AlertTitle class="font-bold text-gray-warm-700 mb-2">{{
          t(
            `api.new-deployment.errors.${(createDeploymentError as ErrorResponse).description_code}.title`,
            t('api.new-deployment.errors.generic.title')
          )
        }}</AlertTitle>

        <AlertDescription>
          <i18n-t
            v-if="
              ['new_desktop_name_exists', 'duplicated_name'].includes(
                (createDeploymentError as ErrorResponse).description_code
              )
            "
            :keypath="`api.new-deployment.errors.${(createDeploymentError as ErrorResponse).description_code}.description`"
            class="whitespace-pre-wrap"
          >
            <template #desktop_name>
              <strong>{{ (createDeploymentError as ErrorResponse)?.params?.name }}</strong>
            </template>
            <template #deployment_name>
              <strong>{{ createDeploymentVariables?.body.name }}</strong>
            </template>
          </i18n-t>
          <template v-else>
            {{
              t(
                `api.new-deployment.errors.${(createDeploymentError as ErrorResponse).description_code}.description`,
                t('api.new-deployment.errors.generic.description')
              )
            }}
          </template>

          <ul
            v-if="(createDeploymentError as ErrorResponse)?.params?.users"
            class="list-disc list-inside"
          >
            <li v-for="user in (createDeploymentError as ErrorResponse)?.params?.users" :key="user">
              {{ user }}
            </li>
          </ul>
        </AlertDescription>
      </Alert>

      <template v-if="currentStep === 1">
        <NewDeploymentForm
          :form="form"
          @submit="isStepFieldsValid(currentStep) ? (currentStep += 1) : null"
        />
      </template>
      <template v-else-if="currentStep === 2">
        <div class="flex flex-col gap-10">
          <form.Subscribe v-slot="{ values }">
            <template v-for="(desktop, index) in values.desktops" :key="desktop._id">
              <NewDeploymentDesktopFormCard
                :index="index"
                :form="form"
                :open="true"
                :auto-focus="true"
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
                  (restrictedFieldsDetails) => {
                    updateHardwareModalData = {
                      index,
                      data: values.desktops[index],
                      restrictedFieldsDetails
                    }
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
</template>
