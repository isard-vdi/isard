import { toUnicode } from 'punycode/punycode.es6.js'

export const hostToUnicode = (text: string): string => {
  try {
    return toUnicode(text)
  } catch {
    return text
  }
}
