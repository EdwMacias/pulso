import { api } from './api'

export type DocumentItem = { id: string; original_name: string; size_bytes: number; page_count: number | null; status: 'processing' | 'ready' | 'failed'; error_message: string | null; created_at: string }
export type DocumentAnswer = { answer: string; source_pages: number[] }
export const listDocuments = () => api<DocumentItem[]>('/documents')
export async function uploadDocument(file: File) { const form = new FormData(); form.append('file', file); return api<DocumentItem>('/documents', { method: 'POST', body: form }) }
export const askDocument = (id: string, question: string) => api<DocumentAnswer>(`/documents/${id}/questions`, { method: 'POST', body: JSON.stringify({ question }) })
export const deleteDocument = (id: string) => api<void>(`/documents/${id}`, { method: 'DELETE' })
