import { ref } from 'vue'

/**
 * POST 型 SSE 客户端
 *
 * 原生 EventSource 只支持 GET，而问诊流式接口是 POST
 * （`POST /api/v1/consultation/stream`），因此这里用 fetch + ReadableStream
 * 手工解析 SSE 帧。对应开发步骤清单 5.2.5 / 5.6.3（打字机效果）。
 *
 * 后端事件：
 *   node     {"node","label",...}   节点执行进度
 *   meta     {"provider","model"}   LLM 实际来源
 *   delta    {"text"}               结论分段
 *   question {"text"}               追问问题
 *   done     {"consultation_id","phase",...}
 *   error    {"code","message"}
 *
 * 6.2.4 连接管理：
 *   - **空闲超时**：SSE 是长连接，服务端卡住或网络半开时，前端会永远转圈。
 *     这里用"距上次收到数据的间隔"判定（不是总耗时），
 *     因为 LLM 推理本来就慢，但慢也会一帧一帧地吐字。
 *   - **断线重连**：仅在**连接建立前/连接早期的失败**上重试，
 *     绝不重放整个问诊请求 —— 否则用户会看到两次结果，且后端会产生重复记录。
 *     已经收到数据之后断开，一律交给用户显式重试。
 */
export function useSSE(url, options = {}) {
  const {
    onEvent,
    onError,
    onDone,
    idleTimeout = 45000, // 45s 没收到任何一帧即判定超时
    maxRetries = 1, // 仅重试「连接早期」失败
    retryDelay = 800
  } = options

  const running = ref(false)
  const text = ref('')
  const nodes = ref([])
  const errorMsg = ref('')
  const retried = ref(0)

  let controller = null
  let idleTimer = null
  let receivedAny = false // 是否已经收到过数据

  function reset() {
    text.value = ''
    nodes.value = []
    errorMsg.value = ''
    retried.value = 0
    receivedAny = false
  }

  function clearIdle() {
    if (idleTimer) {
      clearTimeout(idleTimer)
      idleTimer = null
    }
  }

  /** 每次收到数据就续期；超时则主动断开并报错 */
  function armIdle() {
    clearIdle()
    if (!idleTimeout) return
    idleTimer = setTimeout(() => {
      const msg = `连接超时（${idleTimeout / 1000}s 未收到数据），请检查网络后重试`
      errorMsg.value = msg
      abort()
      onError?.(new Error(msg))
    }, idleTimeout)
  }

  function abort() {
    clearIdle()
    controller?.abort()
    controller = null
    running.value = false
  }

  function handle(event, payload) {
    if (event === 'delta') {
      text.value += payload?.text ?? ''
    } else if (event === 'node') {
      nodes.value.push(payload)
    } else if (event === 'error') {
      errorMsg.value = payload?.message || '服务端返回错误'
    }
    onEvent?.(event, payload)
  }

  /** 解析一个 SSE 帧并派发 */
  function consumeFrame(frame) {
    if (!frame.trim()) return
    let event = 'message'
    const dataLines = []
    for (const line of frame.split('\n')) {
      if (line.startsWith('event:')) event = line.slice(6).trim()
      else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
    }
    let payload = null
    try {
      payload = JSON.parse(dataLines.join('\n'))
    } catch {
      payload = dataLines.join('\n')
    }
    receivedAny = true
    armIdle() // 收到数据 → 续期
    handle(event, payload)
  }

  async function once(body) {
    controller = new AbortController()
    const resp = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: controller.signal
    })
    if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`)

    armIdle() // 连上了但还没数据，也要开始计时
    const reader = resp.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buf = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      // SSE 以空行分帧（网络分块边界 ≠ 帧边界，所以要用缓冲区拼接）
      let idx
      while ((idx = buf.indexOf('\n\n')) !== -1) {
        const frame = buf.slice(0, idx)
        buf = buf.slice(idx + 2)
        consumeFrame(frame)
      }
    }
    // 流正常结束但既没有 done 帧也没有任何数据 —— 视为异常
    if (!receivedAny) throw new Error('服务端未返回任何数据')
  }

  async function start(body) {
    running.value = true
    errorMsg.value = ''
    try {
      await once(body)
      clearIdle()
      running.value = false
      onDone?.()
    } catch (e) {
      // 只在"还没收到任何数据"时重试：此时重放请求不会产生重复结果
      const canRetry =
        !receivedAny &&
        e.name !== 'AbortError' &&
        !String(e.message || '').startsWith('连接超时') &&
        retried.value < maxRetries

      if (canRetry) {
        retried.value += 1
        await new Promise((r) => setTimeout(r, retryDelay))
        try {
          await once(body)
          clearIdle()
          running.value = false
          onDone?.()
          return
        } catch (e2) {
          e = e2 // eslint-disable-line no-param-reassign
        }
      }

      clearIdle()
      running.value = false
      controller = null
      if (e.name !== 'AbortError') {
        errorMsg.value = errorMsg.value || e.message || '网络异常'
        onError?.(e)
      }
    }
  }

  return { running, text, nodes, errorMsg, retried, start, abort, reset }
}
