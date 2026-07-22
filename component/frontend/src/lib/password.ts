// The SPECIAL set MUST stay in sync with the backend validator, which is the
// single source of truth:
// component/_common/src/isardvdi_common/helpers/password.py
export const PASSWORD_REGEX = {
  SPECIAL: /[!@#$%^&*()+\-=_[\]{};:'",.<>?]/g,
  DIGITS: /[0-9]/g,
  LOWERCASE: /[a-z]/g,
  UPPERCASE: /[A-Z]/g
} as const
