import { type JwtPayload, jwtDecode } from 'jwt-decode'
import { useCookies as vueuseCookies } from '@vueuse/integrations/useCookies'
import type { CookieSetOptions } from 'universal-cookie'
import type { ErrorResponse } from '@/gen/oas/apiv4'
import { type LoginError as AuthLoginError } from '@/gen/oas/authentication'

export type Role = 'admin' | 'manager' | 'advanced' | 'user'

/** Roles the API lets through on its `@is_not_user` endpoints. */
export const NOT_USER_ROLES: readonly Role[] = ['admin', 'manager', 'advanced']

export const isNotUser = (role: string | undefined): boolean =>
  NOT_USER_ROLES.includes(role as Role)

/** The login providers the `/login/:provider?/:category?` route understands. */
export enum Provider {
  Form = 'form',
  SAML = 'saml',
  Google = 'google'
}

export const isProvider = (provider: string): provider is Provider =>
  Object.values(Provider).includes(provider as Provider)

interface ProviderUserData {
  provider: string
  category: string
  uid: string

  role?: string
  group?: string
  username?: string
  name?: string
  email?: string
  photo?: string
}

export enum TokenType {
  Login = 'login',
  CategorySelect = 'category-select',
  Register = 'register',
  ReRegister = 're-register',
  DisclaimerAcknowledgeRequired = 'disclaimer-acknowledgement-required',
  EmailVerificationRequired = 'email-verification-required',
  EmailVerification = 'email-verification',
  PasswordResetRequired = 'password-reset-required',
  PasswordReset = 'password-reset',
  UserMigrationRequired = 'user-migration-required',
  UserMigration = 'user-migration'
}

export interface TypeClaims extends JwtPayload {
  key_id: string
  type: TokenType
}

export interface LoginClaims extends TypeClaims {
  session_id: string
  data: LoginClaimsData
}

export interface LoginClaimsData {
  provider: string
  user_id: string
  role_id: Role
  category_id: string
  group_id: string
  name: string
}

export const isLoginClaims = (claims: TypeClaims): claims is LoginClaims => {
  return claims.type === TokenType.Login
}

export interface CategorySelectClaims extends TypeClaims {
  categories: {
    id: string
    name: string
    photo: string
  }[]
  user: ProviderUserData
}

export const isCategorySelectClaims = (claims: TypeClaims): claims is CategorySelectClaims => {
  return claims.type === TokenType.CategorySelect
}

export interface PasswordResetRequiredClaims extends TypeClaims {
  user_id: string
}

export const isPasswordResetRequiredClaims = (
  claims: TypeClaims
): claims is PasswordResetRequiredClaims => {
  return claims.type === TokenType.PasswordResetRequired
}

export interface PasswordResetClaims extends TypeClaims {
  user_id: string
}

export const isPasswordResetClaims = (claims: TypeClaims): claims is PasswordResetClaims => {
  return claims.type === TokenType.PasswordReset
}

export interface RegisterClaims extends TypeClaims {
  category_id: string
  provider: string
}

export const isRegisterClaims = (claims: TypeClaims): claims is RegisterClaims => {
  return claims.type === TokenType.Register
}

export interface ReRegisterClaims extends TypeClaims {
  category_id: string
  provider: string
}

export const isReRegisterClaims = (claims: TypeClaims): claims is ReRegisterClaims => {
  return claims.type === TokenType.ReRegister
}

export interface DisclaimerAcknowledgementRequiredClaims extends TypeClaims {
  user_id: string
}

export const isDisclaimerAcknowledgementRequiredClaims = (
  claims: TypeClaims
): claims is DisclaimerAcknowledgementRequiredClaims => {
  return claims.type === TokenType.DisclaimerAcknowledgeRequired
}

const authorizationTokenName = 'authorization'
export const sessionTokenName = 'isardvdi_session'

export const useCookies = () => vueuseCookies([authorizationTokenName, sessionTokenName])

export const parseToken = (
  bearer: string
):
  | RegisterClaims
  | ReRegisterClaims
  | CategorySelectClaims
  | DisclaimerAcknowledgementRequiredClaims
  | TypeClaims
  | PasswordResetRequiredClaims
  | PasswordResetClaims => {
  const jwt = jwtDecode(bearer) as TypeClaims
  switch (jwt.type) {
    case undefined:
      jwt.type = TokenType.Login
      return jwt

    case TokenType.Login:
      return jwt

    case TokenType.CategorySelect:
      return jwt as CategorySelectClaims

    case TokenType.Register:
      return jwt as RegisterClaims

    case TokenType.ReRegister:
      return jwt as ReRegisterClaims

    case TokenType.DisclaimerAcknowledgeRequired:
      return jwt as DisclaimerAcknowledgementRequiredClaims

    case TokenType.PasswordResetRequired:
      return jwt as PasswordResetRequiredClaims

    case TokenType.PasswordReset:
      return jwt as PasswordResetClaims

    default:
      return jwt
  }
}

export const getBearer = (cookies: ReturnType<typeof useCookies>): string | undefined => {
  return (
    cookies.get<string | undefined>(sessionTokenName) ||
    cookies.get<string | undefined>(authorizationTokenName)
  )
}

export const getToken = (
  cookies: ReturnType<typeof useCookies>
): ReturnType<typeof parseToken> | undefined => {
  const bearer = getBearer(cookies)
  if (!bearer) {
    return undefined
  }

  return parseToken(bearer)
}

const cookieOpts: CookieSetOptions = {
  path: '/',
  sameSite: 'strict'
}

export const setToken = (cookies: ReturnType<typeof useCookies>, bearer: string) => {
  cookies.set(sessionTokenName, bearer, cookieOpts)
}

// The `authorization` cookie is set server-side with these attributes
// (authentication/transport/http/http.go). Removing or re-creating it must use
// the same set, or the browser treats it as a different cookie.
const authorizationCookieOpts: CookieSetOptions = { ...cookieOpts, secure: true }

export const removeToken = (cookies: ReturnType<typeof useCookies>) => {
  cookies.remove(authorizationTokenName, authorizationCookieOpts)
  cookies.remove(sessionTokenName, cookieOpts)
}

const stashedTokenKey = 'isardvdi_intermediate_token'

export interface StashedToken {
  url: string
  hiddenAt: number
  session?: string
  authorization?: string
}

const currentUrl = () => location.pathname + location.search

export const stashToken = (cookies: ReturnType<typeof useCookies>) => {
  const session = cookies.get<string | undefined>(sessionTokenName)
  const authorization = cookies.get<string | undefined>(authorizationTokenName)
  if (!session && !authorization) {
    return
  }

  try {
    sessionStorage.setItem(
      stashedTokenKey,
      JSON.stringify({
        url: currentUrl(),
        hiddenAt: performance.timeOrigin + performance.now(),
        session,
        authorization
      })
    )
  } catch {
    // Storage is unavailable in private mode or with blocked site data
  }
}

const isOptionalString = (value: unknown) => value === undefined || typeof value === 'string'

export const takeStashedToken = (): StashedToken | undefined => {
  try {
    const raw = sessionStorage.getItem(stashedTokenKey)
    sessionStorage.removeItem(stashedTokenKey)
    const stashed = raw ? JSON.parse(raw) : undefined
    if (
      typeof stashed?.url !== 'string' ||
      typeof stashed.hiddenAt !== 'number' ||
      !isOptionalString(stashed.session) ||
      !isOptionalString(stashed.authorization) ||
      !(stashed.session || stashed.authorization)
    ) {
      return undefined
    }
    return {
      url: stashed.url,
      hiddenAt: stashed.hiddenAt,
      session: stashed.session,
      authorization: stashed.authorization
    }
  } catch {
    return undefined
  }
}

const unexpiredUntil = (bearer: string): Date | undefined | null => {
  try {
    const { exp } = parseToken(bearer)
    if (!exp) {
      return undefined
    }
    return exp * 1000 > Date.now() ? new Date(exp * 1000) : null
  } catch {
    return null
  }
}

export const restoreStashedCookies = (
  cookies: ReturnType<typeof useCookies>,
  { session, authorization }: StashedToken
): boolean => {
  let restored = false

  const authorizationExpiry = authorization ? unexpiredUntil(authorization) : null
  if (authorization && authorizationExpiry !== null) {
    cookies.set(authorizationTokenName, authorization, {
      ...authorizationCookieOpts,
      expires: authorizationExpiry
    })
    restored = true
  }

  if (session && unexpiredUntil(session) !== null) {
    setToken(cookies, session)
    restored = true
  }

  return restored
}

export const discardStashedToken = () => {
  try {
    sessionStorage.removeItem(stashedTokenKey)
  } catch {
    // Storage is unavailable in private mode or with blocked site data
  }
}

// A reload starts before the old page is hidden; the grace absorbs coarse timers.
const reloadGraceMs = 10_000

export const isReloadOf = ({ url, hiddenAt }: Pick<StashedToken, 'url' | 'hiddenAt'>): boolean => {
  const entry = performance.getEntriesByType?.('navigation')[0] as
    | PerformanceNavigationTiming
    | undefined
  return (
    (entry?.type === 'reload' || entry?.type === 'navigate') &&
    currentUrl() === url &&
    performance.timeOrigin <= hiddenAt + reloadGraceMs
  )
}

// TODO: Type this!
type LoginError = AuthLoginError['error'] | 'unknown' | 'missing_category'
type RegisterError =
  | ErrorResponse['error']
  | AuthLoginError['error']
  | 'unknown'
  | 'missing_category'

interface LoginRegisterReturn {
  error?: LoginError | RegisterError
  errorParams?: Date
}

export const checkLoginRegister = (
  error: { error?: string | null }, // TODO: check this type
  response: Response,
  skipTokenCheck = false // for register
): LoginRegisterReturn | undefined => {
  if (error !== undefined) {
    if (response.status === 429) {
      if (response.headers.get('retry-after') === null) {
        return { error: 'rate_limit' }
      }
      return {
        error: 'rate_limit_date',
        errorParams: new Date(response.headers.get('retry-after'))
      }
    }

    if (error.error) {
      return { error: error.error }
    }

    return { error: 'unknown' }
  }

  if (skipTokenCheck) {
    return
  }

  const authorization = response.headers.get('authorization')
  if (authorization === null) {
    return { error: 'unknown' }
  }

  const bearer = authorization.replace(/^Bearer /g, '')
  if (bearer.length === authorization.length) {
    return { error: 'unknown' }
  }
}
