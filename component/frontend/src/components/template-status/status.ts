import { TemplateStatusEnum } from '@/gen/oas/apiv4'

export type TemplateStatus = 'failed' | 'hidden'

// Legacy rows come back without the field and are visible.
export const isTemplateVisible = (template: { enabled?: boolean }) => template.enabled !== false

export const isTemplateFailed = (template: Record<string, unknown>) =>
  template.status === TemplateStatusEnum.FAILED

// Only owned templates carry a visibility flag, so `owned` gates the hidden status.
export const templateStatus = (
  template: Record<string, unknown>,
  owned: boolean
): TemplateStatus | undefined => {
  if (isTemplateFailed(template)) return 'failed'
  if (owned && !isTemplateVisible(template as { enabled?: boolean })) return 'hidden'
  return undefined
}

const ROW_CELL_CLASS: Record<TemplateStatus, string> = {
  failed: 'bg-error-25 border-error-300',
  hidden: 'bg-gray-warm-100 border-gray-warm-400 border-dashed'
}

export const templateRowCellClass = (status: TemplateStatus | undefined) =>
  status ? ROW_CELL_CLASS[status] : undefined
