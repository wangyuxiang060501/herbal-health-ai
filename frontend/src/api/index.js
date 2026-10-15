import axios from 'axios'
import { tokens } from './tokens'

/**
 * 统一请求层（开发步骤清单 5.1.5 + 5.4.1 认证接入）
 *
 * 后端统一响应为 { code, message, data }，code === 0 表示成功。
 * 业务异常（急症拦截 40301、安全拦截 40302 等）同样以 HTTP 200 返回，
 * 因此这里不能只看 HTTP 状态码——必须解包业务码。
 *
 * 认证（5.4.1）：
 *   - 请求拦截器自动注入 Authorization: Bearer <access>；
 *   - 收到 401 时用 refresh_token 静默换新并重放原请求（仅一次，
 *     用共享 Promise 合并并发 401，避免风暴）；
 *   - 刷新失败 → 清令牌退回游客模式（用户可见数据随之切到匿名口径）。
 */
const http = axios.create({
  baseURL: '/api/v1',
  timeout: 60000,
  headers: { 'Content-Type': 'application/json' }
})

/** 需要上层自行渲染的业务码：不是"出错"，而是"有话要说" */
export const BIZ_CODE = {
  EMERGENCY_BLOCKED: 40301,
  SAFETY_BLOCKED: 40302,
  LLM_UNAVAILABLE: 50301,
  BUDGET_EXCEEDED: 50302,
  NOT_FOUND: 404
}

/* ------------------------- 认证拦截 ------------------------- */

// 刷新接口本身不再走刷新逻辑（防自环）
const AUTH_PATHS = ['/auth/login', '/auth/register', '/auth/refresh']

http.interceptors.request.use((config) => {
  const token = tokens.access
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

let refreshing = null

async function refreshAccessToken() {
  const rt = tokens.refresh
  if (!rt) return null
  // 用裸 axios 直连，绕过本实例的拦截器
  const { data } = await axios.post('/api/v1/auth/refresh', { refresh_token: rt })
  if (data.code !== 0) return null
  tokens.savePair(data.data)
  return data.data.access_token
}

http.interceptors.response.use(
  (resp) => {
    const body = resp.data
    // 非统一封装（如 SSE 直连）原样透传
    if (!body || typeof body !== 'object' || !('code' in body)) return body
    if (body.code === 0) return body
    const err = new Error(body.message || '请求失败')
    err.code = body.code
    err.data = body.data
    err.isBiz = true
    return Promise.reject(err)
  },
  async (err) => {
    const cfg = err.config || {}
    const path = (cfg.url || '').split('?')[0]
    const isAuthPath = AUTH_PATHS.some((p) => path.includes(p))

    if (err.response?.status === 401 && !isAuthPath && !cfg._retried) {
      try {
        refreshing = refreshing || refreshAccessToken()
        const newAccess = await refreshing
        refreshing = null
        if (newAccess) {
          cfg._retried = true
          cfg.headers.Authorization = `Bearer ${newAccess}`
          return http(cfg)
        }
      } catch {
        refreshing = null
      }
      // 刷新失败：令牌全清，退回游客（登录态由 store.syncProfile / 下次 401 感知）
      tokens.clear()
    }

    if (err.response) {
      const body = err.response.data || {}
      const e = new Error(body.message || `HTTP ${err.response.status}`)
      e.code = body.code ?? err.response.status
      e.data = body.data
      e.isBiz = true
      return Promise.reject(e)
    }
    err.isBiz = false
    return Promise.reject(err)
  }
)

/* ------------------------------ 认证（5.4.1） ------------------------------ */
export const registerApi = (payload) =>
  http.post('/auth/register', payload).then((r) => r.data)
export const loginApi = (payload) =>
  http.post('/auth/login', payload).then((r) => r.data)
export const refreshApi = (refresh_token) =>
  http.post('/auth/refresh', { refresh_token }).then((r) => r.data)
export const getProfile = () => http.get('/auth/profile').then((r) => r.data)

/* ------------------------------ 元数据 ------------------------------ */
export const getDataset = () => http.get('/meta/dataset').then((r) => r.data)
export const getConfig = () => http.get('/meta/config').then((r) => r.data)
export const getLlmStatus = () => http.get('/meta/llm').then((r) => r.data)
export const getConstitutions = () => http.get('/meta/constitutions').then((r) => r.data)
export const getQuestionnaire = () => http.get('/meta/questionnaire').then((r) => r.data)

/* ------------------------------ 药材库 ------------------------------ */
export const listHerbs = (params) => http.get('/herbs', { params }).then((r) => r.data)
export const searchHerbs = (q, limit = 20) =>
  http.get('/herbs/search', { params: { q, limit } }).then((r) => r.data)
export const getHerb = (id) => http.get(`/herbs/${id}`).then((r) => r.data)
export const getCategories = () => http.get('/herbs/categories').then((r) => r.data)
export const getMeridians = () => http.get('/herbs/meridians').then((r) => r.data)

/* ------------------------------ 问诊 ------------------------------ */
export const startConsultation = (payload) =>
  http.post('/consultation/start', payload).then((r) => r.data)
export const answerConsultation = (id, payload) =>
  http.post(`/consultation/${id}/answer`, payload).then((r) => r.data)
export const getConsultation = (id) => http.get(`/consultation/${id}`).then((r) => r.data)
export const getHistory = (limit = 20) =>
  http.get('/consultation/user/history', { params: { limit } }).then((r) => r.data)
export const getTrend = (limit = 20) =>
  http.get('/consultation/user/trend', { params: { limit } }).then((r) => r.data)
export const getGraph = (format = 'json') =>
  http.get('/consultation/graph', { params: { format } }).then((r) => r.data)

/* ------------------------------ 安全 ------------------------------ */
export const probeHerbs = (herbNames, specialGroups = []) =>
  http.post('/safety/probe-herbs', { herb_names: herbNames, special_groups: specialGroups })
    .then((r) => r.data)
export const getSafetyRules = () => http.get('/safety/rules').then((r) => r.data)

/* ------------------------------ 健康检查 ------------------------------ */
export const health = () => axios.get('/health').then((r) => r.data)

export default http
