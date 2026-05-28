import http from './http'

export interface LoginReq { username: string; password: string }
export interface RegisterReq { username: string; password: string; email?: string }
export interface TokenRes { access_token: string; token_type: string }
export interface UserInfo { user_id: string; username: string; email?: string; role: string; is_active: boolean }

export const authApi = {
  login: (data: LoginReq) => http.post<TokenRes>('/auth/login', data),
  register: (data: RegisterReq) => http.post<UserInfo>('/auth/register', data),
  me: () => http.get<UserInfo>('/auth/me'),
}
