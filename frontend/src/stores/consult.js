import { defineStore } from 'pinia'

/** 问诊会话：问卷答案草稿 + 最近一次结果（跨页面传递用） */
export const useConsultStore = defineStore('consult', {
  state: () => ({
    /** { "阳虚质_1": 5, ... } */
    answers: JSON.parse(sessionStorage.getItem('c_answers') || '{}'),
    chiefComplaint: sessionStorage.getItem('c_chief') || '',
    lastConsultationId: sessionStorage.getItem('c_last_id') || '',
    lastResult: JSON.parse(sessionStorage.getItem('c_last_result') || 'null')
  }),
  getters: {
    answeredCount: (s) => Object.keys(s.answers).length
  },
  actions: {
    setAnswer(qid, score) {
      this.answers = { ...this.answers, [qid]: score }
      sessionStorage.setItem('c_answers', JSON.stringify(this.answers))
    },
    setChief(text) {
      this.chiefComplaint = text
      sessionStorage.setItem('c_chief', text)
    },
    setResult(id, result) {
      this.lastConsultationId = id
      this.lastResult = result
      sessionStorage.setItem('c_last_id', id)
      sessionStorage.setItem('c_last_result', JSON.stringify(result))
    },
    clear() {
      this.answers = {}
      this.chiefComplaint = ''
      sessionStorage.removeItem('c_answers')
      sessionStorage.removeItem('c_chief')
    }
  }
})
