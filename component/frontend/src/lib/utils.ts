import type { Ref } from 'vue'

import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'
import type { Updater } from '@tanstack/vue-table'
import { i18n } from '@/lib/i18n'

const locale = i18n.global.locale.value
const t = i18n.global.t

/**
 * Combine and merge class names.
 * @param inputs - The class names to combine.
 * @returns The merged class names.
 */
export const cn = (...inputs: ClassValue[]) => {
  return twMerge(clsx(inputs))
}

/**
 * Check if a given date is today.
 * @param date - The date to check.
 * @returns boolean indicating whether the date is today.
 */
export const dateIsToday = (date: Date): boolean => {
  return date.getDate() === new Date().getDate()
}

/**
 * Type guard to check if a value is a string.
 * @param s - The value to check.
 * @returns boolean indicating whether the value is a string.
 */
export const isString = (s: unknown): s is string => {
  return typeof s === 'string'
}

/**
 *
 * This generic function is used to update a list of entities (objects) based on the operation specified.
 * It can add, update, or delete an entity from the list.
 * The function takes in a list of entities, the operation to perform, and the payload containing the entity data.
 * And returns the list updated.
 *
 * @param list The list of entities to be updated.
 * @param operation The operation to perform: 'add', 'update', or 'delete'.
 * @param payload The entity data used for the operation.
 * @returns The updated list of entities.
 */
export function patchEntityList<T extends { id: string }>(
  list: T[] | undefined,
  operation: 'add' | 'update' | 'delete',
  payload: Partial<T> & { id: string }
): T[] {
  if (!list) return []

  switch (operation) {
    case 'add':
      return [...(list || []), payload as T]
    case 'update':
      return list.map((item) => (item.id === payload.id ? { ...item, ...payload } : item))
    case 'delete':
      return list.filter((item) => item.id !== payload.id)
    default:
      console.error('Unknown operation:', operation)
      return list
  }
}

export function copyToClipboard(text: string): void {
  navigator.clipboard.writeText(text).then(
    () => {
      // console.log(`"${text}" copied to clipboard successfully!`)
    },
    (err) => {
      console.error('Could not copy text: ', err)
    }
  )
}

export function valueUpdater<T extends Updater<unknown>>(updaterOrValue: T, ref: Ref) {
  ref.value = typeof updaterOrValue === 'function' ? updaterOrValue(ref.value) : updaterOrValue
}

// Capitalize the first letter
export const startCase = (str: string): string => str.charAt(0).toUpperCase() + str.slice(1)

export function isInvalid(field: { state: { meta: { isTouched: any; isValid: any } } }) {
  return field.state.meta.isTouched && !field.state.meta.isValid
}

export const formatHoursToHumanReadable = (input: number | { time?: number }, locale = 'en-US') => {
  const hours = typeof input === 'number' ? input : input?.time

  if (!hours || !Number.isFinite(hours)) return '...'

  const isDay = hours >= 24
  const value = Math.round(isDay ? hours / 24 : hours)

  return new Intl.NumberFormat(locale, {
    style: 'unit',
    unit: isDay ? 'day' : 'hour',
    unitDisplay: 'long'
  }).format(value)
}

export const formatBytes = (bytes: number): string => {
  if (!bytes) return `0 ${t('common.units.mb')}`
  const gb = bytes / (1024 * 1024 * 1024)
  if (gb >= 1) {
    return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 2 }).format(gb)} ${t('common.units.gb')}`
  }
  const mb = bytes / (1024 * 1024)
  return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 2 }).format(mb)} ${t('common.units.mb')}`
}

export const formatRelativeTime = (timestamp: number | string, locale = 'en-US'): string => {
  try {
    const date = new Date(typeof timestamp === 'number' ? timestamp * 1000 : timestamp)
    const diffSecs = Math.floor((Date.now() - date.getTime()) / 1000)

    const units: { unit: Intl.RelativeTimeFormatUnit; ms: number }[] = [
      { unit: 'day', ms: 86400 },
      { unit: 'hour', ms: 3600 },
      { unit: 'minute', ms: 60 },
      { unit: 'second', ms: 1 }
    ]

    const rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' })
    const match = units.find((u) => diffSecs >= u.ms) || units[units.length - 1]

    return rtf.format(-Math.floor(diffSecs / match.ms), match.unit)
  } catch {
    return '...'
  }
}
