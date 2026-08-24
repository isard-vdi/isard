import { computed, reactive, toValue, type MaybeRefOrGetter } from 'vue'
import { useForm } from '@tanstack/vue-form'
import { useI18n } from 'vue-i18n'
import * as z from 'zod'

export interface DomainInfoSource {
  name?: string | null
  description?: string | null
}

export interface DomainInfoFormValues {
  name: string
  description: string
}

/** Base fields plus whatever the caller declared through `extraSchema`. */
export type DomainInfoValues = DomainInfoFormValues & Record<string, string>

export interface UseDomainInfoFormOptions {
  /** Seeds name/description and doubles as the dirty baseline. */
  source?: MaybeRefOrGetter<DomainInfoSource | undefined>
  /** Extra fields merged into the values, e.g. `{ os_template: '' }`. */
  extraDefaults?: Record<string, string>
  /** Extra shape merged into the schema, e.g. `{ os_template: z.string().min(1) }`. */
  extraSchema?: z.ZodRawShape
}

export function useDomainInfoForm(options: UseDomainInfoFormOptions = {}) {
  const { t } = useI18n()

  const baseSchema = z.object({
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

  // The extra shape is only known at runtime, so the widened `extend()` result
  // is restated as the value type the form and the validity check both use.
  const schema = baseSchema.extend(options.extraSchema ?? {}) as unknown as z.ZodType<
    DomainInfoValues,
    DomainInfoValues
  >

  // Held by reference in `form.options.defaultValues`, so these computeds stay
  // both the live seed and the live baseline `isDefaultValue` compares against.
  const defaultValues = reactive({
    name: computed(() => toValue(options.source)?.name ?? ''),
    description: computed(() => toValue(options.source)?.description ?? ''),
    ...(options.extraDefaults ?? {})
  }) as DomainInfoValues

  const form = useForm({
    defaultValues,
    validators: { onChange: schema }
  })

  const values = form.useStore((state) => state.values)
  const isDirty = form.useStore((state) => !state.isDefaultValue)
  // Checked against the schema instead of the form store: seeded values are
  // valid but untouched, so the form reports itself valid before its validators
  // ever run.
  const isValid = computed(() => schema.safeParse(values.value).success)

  return { form, values, isDirty, isValid }
}
