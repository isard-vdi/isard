import { toUnicode } from 'punycode/punycode.es6.js'

export const hostToUnicode = (text) => {
  try {
    return toUnicode(text)
  } catch {
    return text
  }
}
