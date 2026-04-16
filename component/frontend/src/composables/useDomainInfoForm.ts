import { reactive, type MaybeRefOrGetter, toValue, computed } from 'vue'
import { useForm } from '@tanstack/vue-form'
import * as z from 'zod'

export interface DomainInfoFormValues {
  name: string
  description: string
}

export const domainInfoFormSchema = z.object({
  name: z.string().trim().min(4).max(50),
  description: z.string().trim().max(255)
})

interface UseDomainInfoFormOptions {
  name?: MaybeRefOrGetter<string | undefined>
  description?: MaybeRefOrGetter<string | undefined>
}

export function useDomainInfoForm(options: UseDomainInfoFormOptions = {}) {
  const defaultValues = reactive({
    name: computed(() => toValue(options.name) ?? ''),
    description: computed(() => toValue(options.description) ?? '')
  })

  return useForm({
    defaultValues,
    validators: {
      onChange: domainInfoFormSchema
    }
  })
}
