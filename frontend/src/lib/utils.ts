import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function dateIsToday(date: Date): boolean {
  return date.getDate() === new Date().getDate()
}
