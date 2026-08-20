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

export function useDomainInfoForm() {
  return useForm({
    defaultValues: { name: '', description: '' } as DomainInfoFormValues,
    validators: {
      onChange: domainInfoFormSchema
    }
  })
}
