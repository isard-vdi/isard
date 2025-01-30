import { type JwtPayload, jwtDecode } from 'jwt-decode'
import { useCookies as vueuseCookies } from '@vueuse/integrations/useCookies'
import type { CookieSetOptions } from 'universal-cookie'
import { type RegisterUserError } from '@/gen/oas/api'
import { type LoginError as AuthLoginError } from '@/gen/oas/authentication'

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
  Register = 'register'
}

export interface TypeClaims extends JwtPayload {
  key_id: string
  type: TokenType
}

export interface LoginClaims extends TypeClaims {
  session_id: string
  data: {
    provider: string
    id: string
    role_id: string
    category_id: string
    group_id: string
    name: string
  }
}

export const isLoginClaims = (claims: TypeClaims): claims is LoginClaims => {
  return claims.type === TokenType.Login
}

export interface CategorySelectClaims extends TypeClaims {
  categories: Array<{
    id: string
    name: string
    photo: string
  }>
  user: ProviderUserData
}

export const isCategorySelectClaims = (claims: TypeClaims): claims is CategorySelectClaims => {
  return claims.type === TokenType.CategorySelect
}

export interface RegisterClaims extends TypeClaims {
  category_id: string
  provider: string
}

export const isRegisterClaims = (claims: TypeClaims): claims is RegisterClaims => {
  return claims.type === TokenType.Register
}

const authorizationTokenName = 'authorization'
const sessionTokenName = 'isardvdi_session'

export const useCookies = () => vueuseCookies([authorizationTokenName, sessionTokenName])

export const parseToken = (bearer: string): RegisterClaims | CategorySelectClaims | TypeClaims => {
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

    default:
      return jwt
  }
}

export const getBearer = (cookies: ReturnType<typeof useCookies>): string | undefined => {
  return (
    cookies.get<string | undefined>(authorizationTokenName) ||
    cookies.get<string | undefined>(sessionTokenName)
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

export const removeToken = (cookies: ReturnType<typeof useCookies>) => {
  cookies.remove(authorizationTokenName, cookieOpts)
  cookies.remove(sessionTokenName, cookieOpts)
}

// TODO: Type this!
type LoginError = AuthLoginError['error'] | 'unknown' | 'missing_category'
type RegisterError =
  | RegisterUserError['error']
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
  skipTokenCheck: boolean = false // for register
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
