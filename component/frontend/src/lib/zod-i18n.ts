import * as z from 'zod' // v4
import type { Composer } from 'vue-i18n'

export function setupZodI18n(i18n: Composer) {
  const customErrorMap: z.ZodErrorMap = (issue) => {
    let message: string = i18n.t('components.form.validation.invalid-value', {
      field: issue.path?.join('.') || 'field'
    })
    const fieldPath = issue.path?.join('.') || 'field'

    switch (issue.code) {
      case 'invalid_type':
        if (issue.received === 'undefined') {
          message = i18n.t('components.form.validation.required', {
            field: fieldPath
          })
        } else {
          message = i18n.t(`components.form.validation.type.${issue.expected}`, {
            field: fieldPath
          })
        }
        break

      case 'too_big':
        if (issue.type === 'string') {
          message = i18n.t('components.form.validation.max-length', {
            field: fieldPath,
            max: issue.maximum
          })
        } else if (issue.type === 'number') {
          message = i18n.t('components.form.validation.max-value', {
            field: fieldPath,
            max: issue.maximum
          })
        } else if (issue.type === 'array') {
          message = i18n.t('components.form.validation.max-array-length', {
            field: fieldPath,
            max: issue.maximum
          })
        }
        break

      case 'too_small': {
        const issueType =
          (issue as { type?: string; origin?: string }).type ||
          (issue as { type?: string; origin?: string }).origin

        if (issueType === 'string') {
          // Treat min(1) on strings as required field validation
          if (issue.minimum === 1) {
            message = i18n.t('components.form.validation.required', {
              field: fieldPath
            })
          } else {
            message = i18n.t('components.form.validation.min-length', {
              field: fieldPath,
              min: issue.minimum
            })
          }
        } else if (issueType === 'number') {
          message = i18n.t('components.form.validation.min-value', {
            field: fieldPath,
            min: issue.minimum
          })
        } else if (issueType === 'array') {
          // For arrays with min(1), treat as required
          if (issue.minimum === 1) {
            message = i18n.t('components.form.validation.required', {
              field: fieldPath
            })
          } else {
            message = i18n.t('components.form.validation.min-array-length', {
              field: fieldPath,
              min: issue.minimum
            })
          }
        }
        break
      }

      case 'invalid_format':
        if (issue.format === 'email') {
          message = i18n.t('components.form.validation.type.email', {
            field: fieldPath
          })
        } else {
          message = i18n.t('components.form.validation.invalid-format', {
            field: fieldPath
          })
        }
        break

      case 'not_multiple_of':
        message = i18n.t('components.form.validation.multiple-of', {
          field: fieldPath,
          multipleOf: issue.divisor
        })
        break

      case 'unrecognized_keys':
        message = i18n.t('components.form.validation.unrecognized-keys', {
          field: fieldPath,
          keys: issue.keys.join(', ')
        })
        break

      case 'invalid_union':
        message = i18n.t('components.form.validation.invalid-union', {
          field: fieldPath
        })
        break

      case 'invalid_key':
        message = i18n.t('components.form.validation.invalid-key', {
          field: fieldPath
        })
        break

      case 'invalid_element':
        message = i18n.t('components.form.validation.invalid-element', {
          field: fieldPath
        })
        break

      case 'invalid_value':
        message = i18n.t('components.form.validation.invalid-value', {
          field: fieldPath
        })
        break

      case 'custom':
        message =
          issue.message ||
          i18n.t('components.form.validation.invalid-value', {
            field: fieldPath
          })
        break

      default:
        message = i18n.t('components.form.validation.invalid-value', {
          field: fieldPath
        })
    }

    return { message }
  }

  z.setErrorMap(customErrorMap)
}
