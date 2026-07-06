// Character-class regexes used to count how many characters of each kind a
// password contains, so the UI can check it against the server's password
// policy live (length, uppercase, lowercase, digits, special characters).
//
// The SPECIAL set MUST stay in sync with the backend validator, which is the
// single source of truth:
// component/_common/src/isardvdi_common/helpers/password.py
export const PASSWORD_REGEX = {
  SPECIAL: /[!@#$%^&*()+\-=_[\]{}|;:'",.<>/?]/g,
  DIGITS: /[0-9]/g,
  LOWERCASE: /[a-z]/g,
  UPPERCASE: /[A-Z]/g
} as const
