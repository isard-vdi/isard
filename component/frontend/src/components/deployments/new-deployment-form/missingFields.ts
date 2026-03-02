import type { Composer } from 'vue-i18n'

interface Issue {
  path: PropertyKey[]
}

const FIELD_LABEL_KEYS: Record<string, string> = {
  name: 'components.deployments.form-sections.info.fields.name.label',
  description: 'components.deployments.form-sections.info.fields.description.label',
  visible: 'components.deployments.form-sections.visibility.fields.visible.label',
  alloweds: 'components.deployments.form-sections.alloweds.title',
  image: 'components.deployments.form-sections.preview.title',
  desktops: 'views.new-deployment.steps.select-desktops.title'
}

const DESKTOP_FIELD_LABEL_KEYS: Record<string, string> = {
  name: 'components.deployments.form-desktop-card.sections.preview.fields.name.label',
  description: 'components.deployments.form-desktop-card.sections.preview.fields.description.label'
}

/**
 * Labels of the fields that block submission, deduplicated and in issue order.
 */
export function missingFieldLabels(issues: readonly Issue[], t: Composer['t']): string[] {
  const labels = new Set<string>()

  for (const { path } of issues) {
    const [root, index, field] = path

    if (root === 'desktops' && typeof index === 'number') {
      const labelKey = DESKTOP_FIELD_LABEL_KEYS[String(field)]
      labels.add(
        t('components.deployments.missing-fields.desktop', {
          index: index + 1,
          field: labelKey ? t(labelKey) : String(field)
        })
      )
      continue
    }

    const labelKey = FIELD_LABEL_KEYS[String(root)]
    labels.add(labelKey ? t(labelKey) : String(root))
  }

  return [...labels]
}
