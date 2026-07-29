import { ref } from 'vue'

function localToday() {
  const now = new Date()
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function isValidRecordDate(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(String(value || ''))) return false
  const [year, month, day] = String(value).split('-').map(Number)
  const parsed = new Date(year, month - 1, day)
  return (
    parsed.getFullYear() === year &&
    parsed.getMonth() === month - 1 &&
    parsed.getDate() === day
  )
}

const stored = typeof localStorage !== 'undefined' ? localStorage.getItem('stock-helper-record-date') : ''
export const currentRecordDate = ref(isValidRecordDate(stored) ? stored : localToday())

export function getCurrentRecordDate() {
  return currentRecordDate.value
}

export function setCurrentRecordDate(value) {
  if (!isValidRecordDate(value)) return false
  currentRecordDate.value = value
  if (typeof localStorage !== 'undefined') {
    localStorage.setItem('stock-helper-record-date', value)
  }
  return true
}

export function formatRecordDate(value) {
  if (!isValidRecordDate(value)) return value || ''
  const [year, month, day] = value.split('-').map(Number)
  const parsed = new Date(year, month - 1, day)
  const weekdays = ['星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六']
  return `${year}年${month}月${day}日 ${weekdays[parsed.getDay()]}`
}

export function shiftRecordDate(value, days) {
  const base = isValidRecordDate(value) ? value : localToday()
  const [year, month, day] = base.split('-').map(Number)
  const parsed = new Date(year, month - 1, day)
  parsed.setDate(parsed.getDate() + days)
  const resultYear = parsed.getFullYear()
  const resultMonth = String(parsed.getMonth() + 1).padStart(2, '0')
  const resultDay = String(parsed.getDate()).padStart(2, '0')
  return `${resultYear}-${resultMonth}-${resultDay}`
}
