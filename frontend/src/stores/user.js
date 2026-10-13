import { defineStore } from 'pinia'

/**
 * 用户身份（本地态）
 *
 * 后端尚未实现认证接口（清单 5.4.1 依赖的 /api/v1/auth 属 P5 范围），
 * 这里用 localStorage 做"游客身份"，保证历史/趋势等接口可联调，
 * 后端补上认证后只需替换 login() 实现。
 */
export const useUserStore = defineStore('user', {
  state: () => ({
    phone: localStorage.getItem('u_phone') || '',
    nickname: localStorage.getItem('u_nickname') || '',
    disclaimerAccepted: localStorage.getItem('disclaimer_accepted') === '1'
  }),
  getters: {
    isLogin: (s) => !!s.phone,
    displayName: (s) => s.nickname || (s.phone ? s.phone.slice(0, 3) + '****' + s.phone.slice(-4) : '游客')
  },
  actions: {
    login({ phone, nickname }) {
      this.phone = phone
      this.nickname = nickname || ''
      localStorage.setItem('u_phone', phone)
      localStorage.setItem('u_nickname', this.nickname)
    },
    logout() {
      this.phone = ''
      this.nickname = ''
      localStorage.removeItem('u_phone')
      localStorage.removeItem('u_nickname')
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
