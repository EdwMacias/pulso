import { api } from './api'

export type WhatsAppStatus = {
  status: 'unlinked' | 'pending' | 'verified'
  masked_phone: string | null
  expires_at: string | null
  verified_at: string | null
}

export type WhatsAppLinkPending = {
  status: 'pending'
  masked_phone: string
  code: string
  expires_at: string
}

export function getWhatsAppStatus() {
  return api<WhatsAppStatus>('/whatsapp/status')
}

export function startWhatsAppLink(phone: string) {
  return api<WhatsAppLinkPending>('/whatsapp/link', {
    method: 'POST',
    body: JSON.stringify({ phone }),
  })
}

export function unlinkWhatsApp() {
  return api<void>('/whatsapp/link', { method: 'DELETE' })
}
