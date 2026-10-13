<template>
  <div class="page page--no-tab">
    <van-nav-bar title="身份设置" left-arrow fixed placeholder @click-left="$router.back()" />

    <div class="brand">
      <van-icon name="flower-o" size="34" color="#0d8050" />
      <h2>药食同源 · 智慧康养</h2>
      <p class="muted">{{ mode === 'login' ? '登录后查看个人问诊历史与体质趋势' : '创建本地身份，开始你的康养记录' }}</p>
    </div>

    <van-tabs v-model:active="mode" color="#0d8050">
      <van-tab title="登录" name="login" />
      <van-tab title="注册" name="register" />
    </van-tabs>

    <div class="card">
      <van-form @submit="onSubmit">
        <van-field
          v-model="phone"
          name="phone"
          label="手机号"
          type="tel"
          maxlength="11"
          placeholder="请输入 11 位手机号"
          :rules="[{ pattern: /^1[3-9]\d{9}$/, message: '手机号格式不正确' }]"
        />
        <van-field
          v-model="code"
          name="code"
          label="验证码"
          maxlength="6"
          placeholder="演示环境填任意 4-6 位"
          :rules="[{ required: true, message: '请填写验证码' }]"
        >
          <template #button>
            <van-button size="small" type="primary" color="#0d8050" @click="sendCode">
              {{ countdown > 0 ? countdown + 's' : '获取验证码' }}
            </van-button>
          </template>
        </van-field>
        <van-field
          v-model="nickname"
          label="昵称"
          :placeholder="mode === 'register' ? '给自己起个名字（必填）' : '选填'"
          :rules="mode === 'register' ? [{ required: true, message: '注册请填写昵称' }] : []"
        />

        <div v-if="mode === 'register'" class="agree">
          <van-checkbox v-model="agreed" shape="square" checked-color="#0d8050" icon-size="14">
            <span class="agree-text">我已阅读并同意<a @click.prevent="showDisclaimer = true">《免责声明》</a></span>
          </van-checkbox>
        </div>

        <div class="actions">
          <van-button
            block
            type="primary"
            color="#0d8050"
            native-type="submit"
            :disabled="mode === 'register' && !agreed"
          >
            {{ mode === 'register' ? '注册并使用' : '登录' }}
          </van-button>
          <van-button block plain @click="onGuest">以游客身份继续</van-button>
        </div>
      </van-form>
    </div>

    <div class="disclaimer-bar">
      说明：后端当前未实现用户认证接口（<code>/api/v1/auth</code> 属后续阶段范围），
      本页只把身份写入浏览器本地存储，用于区分个人历史记录，不涉及密码与真实短信。
    </div>

    <DisclaimerModal v-model="showDisclaimer" @accept="agreed = true" />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { showToast } from 'vant'
import DisclaimerModal from '@/components/DisclaimerModal.vue'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const user = useUserStore()

const mode = ref('login')
const phone = ref(user.phone)
const code = ref('')
const nickname = ref(user.nickname)
const countdown = ref(0)
const agreed = ref(false)
const showDisclaimer = ref(false)

function sendCode() {
  if (!/^1[3-9]\d{9}$/.test(phone.value)) {
    showToast('请先填写正确的手机号')
    return
  }
  showToast('演示环境：验证码已"发送"，可填任意数字')
  countdown.value = 60
  const timer = setInterval(() => {
    if (--countdown.value <= 0) clearInterval(timer)
  }, 1000)
}

function onSubmit() {
  user.login({ phone: phone.value, nickname: nickname.value })
  showToast(mode.value === 'register' ? '注册成功' : '登录成功')
  router.back()
}

function onGuest() {
  user.logout()
  router.back()
}
</script>

<style scoped>
.brand {
  text-align: center;
  padding: 52px 16px 8px;
}
.brand h2 {
  margin: 8px 0 4px;
  font-size: 18px;
}
.agree {
  padding: 10px 16px;
}
.agree-text {
  font-size: 12px;
  color: var(--c-text-sub);
}
.agree-text a {
  color: var(--c-primary);
}
.actions {
  padding: 16px 0 4px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
</style>
