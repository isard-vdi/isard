import {
  computed,
  inject,
  provide,
  shallowRef,
  toValue,
  type ComputedRef,
  type InjectionKey,
  type MaybeRefOrGetter,
  type Ref
} from 'vue'
import type * as z from 'zod'

type FormSchema = z.ZodType | undefined

export const FORM_SCHEMA_INJECTION_KEY = Symbol('formSchema') as InjectionKey<Ref<FormSchema>>

const NO_FORM_SCHEMA = shallowRef<FormSchema>(undefined)

/**
 * Publishes a form's validation schema to the `<FieldLabel>`s beneath it, so
 * each one marks itself required without repeating what the schema says.
 *
 * Call it once, in the same setup as the form's `useForm(...)`:
 *
 *   const formSchema = z.object({ ... })
 *   provideFormSchema(formSchema)
 *   const form = useForm({ defaultValues, validators: { onChange: formSchema } })
 *
 * Pass a getter when the schema is rebuilt reactively:
 *
 *   provideFormSchema(() => formSchema.value)
 */
export function provideFormSchema(schema: MaybeRefOrGetter<FormSchema>): ComputedRef<FormSchema> {
  const resolved = computed(() => toValue(schema))
  provide(FORM_SCHEMA_INJECTION_KEY, resolved)
  return resolved
}

/** The nearest enclosing form schema, or a ref holding `undefined`. */
export function useFormSchema(): Ref<FormSchema> {
  return inject(FORM_SCHEMA_INJECTION_KEY, NO_FORM_SCHEMA)
}
