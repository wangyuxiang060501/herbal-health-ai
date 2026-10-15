/**
 * 令牌持久化（独立小模块，避免 store ↔ api 循环依赖）
 *
 * 键名与 stores/user.js 共用；stores/user.js 只做「登录时写入 / 登出时清除」，
 * api/index.js 拦截器只做「读出来注入请求头 / 401 时刷新」。
 */
const K_ACCESS = 'u_access'
const K_REFRESH = 'u_refresh'
const K_UID = 'u_uid'

export const tokens = {
  get access() { return localStorage.getItem(K_ACCESS) || '' },
  get refresh() { return localStorage.getItem(K_REFRESH) || '' },
  get uid() { return Number(localStorage.getItem(K_UID) || 0) || null },
  save({ access_token, refresh_token, user }) {
    localStorage.setItem(K_ACCESS, access_token)
    localStorage.setItem(K_REFRESH, refresh_token)
    localStorage.setItem(K_UID, String(user.id))
  },
  savePair({ access_token, refresh_token }) {
    if (access_token) localStorage.setItem(K_ACCESS, access_token)
    if (refresh_token) localStorage.setItem(K_REFRESH, refresh_token)
  },
  clear() {
    localStorage.removeItem(K_ACCESS)
    localStorage.removeItem(K_REFRESH)
    localStorage.removeItem(K_UID)
  }
}
