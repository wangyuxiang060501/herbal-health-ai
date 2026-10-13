// useSSE：POST 型 SSE 帧解析（原生 EventSource 不支持 POST，这里是自实现）
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import { useSSE } from '@/composables/useSSE'

function sseResponse(frames) {
  const enc = new TextEncoder()
  const chunks = frames.map((f) => enc.encode(f))
  let i = 0
  return {
    ok: true,
    status: 200,
    body: {
      getReader: () => ({
        read: async () => (i < chunks.length ? { done: false, value: chunks[i++] } : { done: true })
      })
    }
  }
}

const frame = (event, data) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`

describe('useSSE', () => {
  beforeEach(() => {
    global.fetch = vi.fn()
  })

  it('按空行分帧解析，delta 累积为完整文本', async () => {
    global.fetch.mockResolvedValue(
      sseResponse([frame('delta', { text: '你的体质' }), frame('delta', { text: '倾向于阳虚' })])
    )
    const sse = useSSE('/api/v1/consultation/stream')
    await sse.start({ chief_complaint: '怕冷' })
    expect(sse.text.value).toBe('你的体质倾向于阳虚')
    expect(sse.running.value).toBe(false)
  })

  it('node 事件按序收集，可用于画进度', async () => {
    global.fetch.mockResolvedValue(
      sseResponse([
        frame('node', { node: 'collect_symptoms', label: '症状采集' }),
        frame('node', { node: 'constitution_engine', label: '体质判定' }),
        frame('done', { consultation_id: 'abc', phase: 'completed' })
      ])
    )
    const events = []
    const sse = useSSE('/api/v1/consultation/stream', { onEvent: (e, p) => events.push([e, p]) })
    await sse.start({})
    expect(sse.nodes.value.map((n) => n.node)).toEqual(['collect_symptoms', 'constitution_engine'])
    expect(events.map(([e]) => e)).toEqual(['node', 'node', 'done'])
    expect(events[2][1].phase).toBe('completed')
  })

  it('error 事件（急症拦截）传给上层且带 consultation_id', async () => {
    global.fetch.mockResolvedValue(
      sseResponse([frame('error', { code: 'EMERGENCY_BLOCKED', message: '请立即就医', consultation_id: 'x1' })])
    )
    let errPayload = null
    const sse = useSSE('/api/v1/consultation/stream', {
      onEvent: (e, p) => {
        if (e === 'error') errPayload = p
      }
    })
    await sse.start({})
    expect(errPayload.code).toBe('EMERGENCY_BLOCKED')
    expect(errPayload.consultation_id).toBe('x1')
  })

  it('分块跨帧时不会截断（粘包/半包）', async () => {
    // 故意把一个 SSE 帧切成两半推送
    const full = frame('delta', { text: '怕冷' })
    const enc = new TextEncoder()
    const half = Math.floor(full.length / 2)
    const chunks = [enc.encode(full.slice(0, half)), enc.encode(full.slice(half))]
    let i = 0
    global.fetch.mockResolvedValue({
      ok: true,
      body: {
        getReader: () => ({
          read: async () => (i < chunks.length ? { done: false, value: chunks[i++] } : { done: true })
        })
      }
    })
    const sse = useSSE('/api/v1/consultation/stream')
    await sse.start({})
    expect(sse.text.value).toBe('怕冷')
  })

  it('abort 后停止运行，不抛异常', async () => {
    global.fetch.mockResolvedValue(
      sseResponse([frame('delta', { text: 'a' }), frame('delta', { text: 'b' })])
    )
    const sse = useSSE('/api/v1/consultation/stream')
    const p = sse.start({})
    sse.abort()
    await p
    expect(sse.running.value).toBe(false)
    await nextTick()
  })
})
