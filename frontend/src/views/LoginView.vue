<template>
  <div class="page page--no-tab">
    <van-nav-bar title="身份设置" left-arrow fixed placeholder @click-left="$router.back()" />

    <div class="brand">
      <van-icon name="flower-o" size="34" color="#0d8050" />
      <h2>药食同源 · 智慧康养</h2>
      <p class="muted">{{ mode === 'login' ? '登录后查看个人问诊历史与体质趋势' : '注册账号，开始你的康养记录' }}</p>
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
          v-model="password"
          name="password"
          label="密码"
          type="password"
          maxlength="64"
          :placeholder="mode === 'register' ? '设置密码（至少 6 位）' : '请输入密码'"
          :rules="[
            { required: true, message: '请填写密码' },
            { validator: (v) => mode !== 'register' || v.length >= 6, message: '密码至少 6 位' }
          ]"
        />
        <van-field
          v-if="mode === 'register'"
          v-model="nickname"
          label="昵称"
          placeholder="给自己起个名字（选填）"
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
            :loading="busy"
            :disabled="mode === 'register' && !agreed"
          >
            {{ mode === 'register' ? '注册并登录' : '登录' }}
          </van-button>
          <van-button block plain @click="onGuest">以游客身份继续</van-button>
        </div>
      </van-form>
    </div>

    <div class="disclaimer-bar">
      说明：账号仅用于区分个人问诊历史与体质趋势（数据按账号隔离）。
      本系统不提供医疗诊断，问诊结果仅供参考，急症请立即就医。
    </div>

    <DisclaimerModal v-model="showDisclaimer" @accept="agreed = true" />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { showToast, showFailToast } from 'vant'
import DisclaimerModal from '@/components/DisclaimerModal.vue'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const user = useUserStore()

const mode = ref('login')
const phone = ref(user.phone)
const password = ref('')
const nickname = ref('')
const agreed = ref(false)
const showDisclaimer = ref(false)
const busy = ref(false)

async function onSubmit() {
  if (busy.value) return
  busy.value = true
  try {
    if (mode.value === 'register') {
      await user.register({ phone: phone.value, password: password.value, nickname: nickname.value })
      showToast('注册成功')
    } else {
      await user.login({ phone: phone.value, password: password.value })
      showToast('登录成功')
    }
    router.back()
  } catch (e) {
    showFailToast(e.message || '操作失败，请重试')
  } finally {
    busy.value = false
  }
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
