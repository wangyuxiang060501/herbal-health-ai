import { defineStore } from 'pinia'
import { loginApi, registerApi, getProfile } from '@/api'
import { tokens } from '@/api/tokens'

/**
 * 用户身份（清单 5.4.1 联调版）
 *
 * 后端 /api/v1/auth 已上线（注册/登录/JWT 令牌对）：
 *   - access_token（2h）走 Authorization 头，由 api/index.js 拦截器自动注入；
 *   - refresh_token（14d）仅在 401 时由拦截器静默换新，本层不感知；
 *   - 令牌持久化在 localStorage，存取逻辑收敛在 api/tokens.js（避免循环依赖）。
 *
 * 兼容：仍保留「游客模式」（logout 后即游客），匿名问诊记录
 * 与登录用户的记录在后端按 user_id 天然隔离，互不可见。
 */

export const useUserStore = defineStore('user', {
  state: () => ({
    phone: localStorage.getItem(K_PHONE) || '',
    nickname: localStorage.getItem(K_NICK) || '',
    userId: Number(localStorage.getItem(K_UID) || 0) || null,
    disclaimerAccepted: localStorage.getItem('disclaimer_accepted') === '1'
  }),
  getters: {
    isLogin: (s) => !!s.userId,
    displayName: (s) => s.nickname || (s.phone ? s.phone.slice(0, 3) + '****' + s.phone.slice(-4) : '游客')
  },
  actions: {
    /** 手机号 + 密码登录（真实接口） */
    async login({ phone, password }) {
      const data = await loginApi({ phone, password })
      tokens.save(data)
      this._apply(data.user, phone)
      return data.user
    },
    /** 注册即登录 */
    async register({ phone, password, nickname }) {
      const data = await registerApi({ phone, password, nickname })
      tokens.save(data)
      this._apply(data.user, phone)
      return data.user
    },
    /** 拉取资料（刷新页面后校验令牌是否仍有效，可选用） */
    async syncProfile() {
      if (!tokens.access) return null
      try {
        const data = await getProfile()
        this._apply(data, this.phone)
        return data
      } catch {
        // 令牌失效且刷新失败（拦截器已清 token）→ 退回游客
        this.logout()
        return null
      }
    },
    _apply(user, phone) {
      this.userId = user.id
      this.phone = phone || user.phone
      this.nickname = user.nickname || ''
      localStorage.setItem(K_PHONE, this.phone)
      localStorage.setItem(K_NICK, this.nickname)
    },
    /** 退出登录 → 游客模式（清令牌，不影响历史记录的隔离性） */
    logout() {
      this.phone = ''
      this.nickname = ''
      this.userId = null
      tokens.clear()
      localStorage.removeItem(K_PHONE)
      localStorage.removeItem(K_NICK)
    },
    acceptDisclaimer() {
      this.disclaimerAccepted = true
      localStorage.setItem('disclaimer_accepted', '1')
    },
    resetDisclaimer() {
      this.disclaimerAccepted = false
      localStorage.removeItem('disclaimer_accepted')
    }
  }
})
