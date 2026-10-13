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
 */
export function useSSE(url, { onEvent, onError, onDone } = {}) {
  const running = ref(false)
  const text = ref('')
  const nodes = ref([])
  let controller = null

  function reset() {
    text.value = ''
    nodes.value = []
  }

  function abort() {
    controller?.abort()
    controller = null
    running.value = false
  }

  async function start(body) {
    running.value = true
    reset()
    controller = new AbortController()
    try {
      const resp = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: controller.signal
      })
      if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`)

      const reader = resp.body.getReader()
      const decoder = new TextDecoder('utf-8')
      let buf = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })

        // SSE 以空行分帧
        let idx
        while ((idx = buf.indexOf('\n\n')) !== -1) {
          const frame = buf.slice(0, idx)
          buf = buf.slice(idx + 2)
          if (!frame.trim()) continue
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
          handle(event, payload)
        }
      }
      running.value = false
      onDone?.()
    } catch (e) {
      running.value = false
      if (e.name !== 'AbortError') onError?.(e)
    }
  }

  function handle(event, payload) {
    if (event === 'delta') {
      text.value += payload?.text ?? ''
    } else if (event === 'node') {
      nodes.value.push(payload)
    }
    onEvent?.(event, payload)
  }

  return { running, text, nodes, start, abort, reset }
}
