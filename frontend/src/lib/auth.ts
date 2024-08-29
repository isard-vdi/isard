import { type JwtPayload, jwtDecode } from 'jwt-decode'
import { useCookies as vueuseCookies } from '@vueuse/integrations/useCookies'

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
  CategorySelect = 'category-select'
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

const authorizationTokenName = 'authorization'
const sessionTokenName = 'isardvdi_session'

export const useCookies = () => vueuseCookies([authorizationTokenName, sessionTokenName])

export const parseToken = (bearer: string): CategorySelectClaims | TypeClaims => {
  console.warn('parsing token')
  const jwt = jwtDecode(bearer) as TypeClaims
  console.warn('parsed token', jwt)
  switch (jwt.type) {
    case undefined:
      jwt.type = TokenType.Login
      return jwt

    case TokenType.Login:
      return jwt

    case TokenType.CategorySelect:
      return jwt as CategorySelectClaims

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

export const setToken = (cookies: ReturnType<typeof useCookies>, bearer: string) => {
  cookies.set(sessionTokenName, bearer)
}

export const removeToken = (cookies: ReturnType<typeof useCookies>) => {
  cookies.remove(authorizationTokenName)
  cookies.remove(sessionTokenName)
}
