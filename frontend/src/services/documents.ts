import { api } from './api'

export type DocumentItem = { id: string; original_name: string; size_bytes: number; page_count: number | null; status: 'processing' | 'ready' | 'failed'; error_message: string | null; created_at: string }
export type DocumentSource = { chunk_index: number; page_number: number; score: number; matched_terms: string[]; content: string }
export type DocumentAnswer = { answer: string; source_pages: number[]; sources: DocumentSource[]; total_chunks: number; retrieval: string }
export type TextSegment = { text: string; match: boolean }

// Replica la normalización del backend (retrieval.tokenize) para resaltar los términos que puntuaron.
export function normalizeTerm(word: string) {
  const plain = word.normalize('NFD').replace(/\p{Mn}/gu, '').toLowerCase()
  return plain.length > 4 && plain.endsWith('s') ? plain.slice(0, -1) : plain
}

export function highlightSegments(content: string, terms: string[]): TextSegment[] {
  const wanted = new Set(terms)
  return content.split(/([\p{L}\p{N}]+)/u).filter(Boolean).map(text => ({ text, match: wanted.has(normalizeTerm(text)) }))
}
export const listDocuments = () => api<DocumentItem[]>('/documents')
export async function uploadDocument(file: File) { const form = new FormData(); form.append('file', file); return api<DocumentItem>('/documents', { method: 'POST', body: form }) }
export const askDocument = (id: string, question: string) => api<DocumentAnswer>(`/documents/${id}/questions`, { method: 'POST', body: JSON.stringify({ question }) })
export const deleteDocument = (id: string) => api<void>(`/documents/${id}`, { method: 'DELETE' })

export type InvoiceKind = 'cobro' | 'pago'
export type TaskSuggestion = {
  title: string; description: string | null; priority: 'low' | 'medium' | 'high'; remind_at: string | null
  page: number | null; evidence: string | null; kind: 'general' | InvoiceKind
  invoice_number: string | null; issuer: string | null; customer: string | null; amount: string | null; due_date: string | null
}
export const suggestDocumentTasks = (id: string) => api<{ suggestions: TaskSuggestion[] }>(`/documents/${id}/task-suggestions`, { method: 'POST' })
export const addDocumentTasks = (id: string, tasks: TaskSuggestion[]) => api<{ created_tasks: number; created_reminders: number }>(`/documents/${id}/tasks`, { method: 'POST', body: JSON.stringify({ tasks }) })

// Al cambiar entre cobro y pago cambia el verbo y la contraparte: cobro al cliente, pago al emisor.
export function invoiceTitle(suggestion: TaskSuggestion, kind: InvoiceKind) {
  const counterparty = kind === 'cobro' ? suggestion.customer : suggestion.issuer
  return [kind === 'cobro' ? 'Cobrar factura' : 'Pagar factura', suggestion.invoice_number, counterparty && `a ${counterparty}`].filter(Boolean).join(' ')
}
