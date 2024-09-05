import { test as base } from '@playwright/test'

export const fixture = {
  randomString: async ({ page }, use) => {
    const generate = () => {
      return Math.random().toString(36).slice(2)
    }

    const generateLong = () => {
      return generate() + ' ' + generate()
    }

    await use({ generate, generateLong })
  }
}

export const test = base.extend(fixture)
