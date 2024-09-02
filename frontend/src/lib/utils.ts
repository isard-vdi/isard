import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export const cn = (...inputs: ClassValue[]) => {
  return twMerge(clsx(inputs))
}

export const dateIsToday = (date: Date): boolean => {
  return date.getDate() === new Date().getDate()
}

export const isString = (s: any): s is string => {
  return typeof s === 'string'
}
