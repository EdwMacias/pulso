import { afterEach, describe, expect, it, vi } from 'vitest'
import { getWhatsAppStatus, startWhatsAppLink, unlinkWhatsApp } from '../src/services/whatsapp'

afterEach(() => vi.unstubAllGlobals())

describe('servicio de vinculación de WhatsApp', () => {
  it('consulta el estado autenticado', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: 'unlinked' })))
    vi.stubGlobal('fetch', fetcher)

    await expect(getWhatsAppStatus()).resolves.toMatchObject({ status: 'unlinked' })
    expect(fetcher.mock.calls[0]![0]).toBe('/api/v1/whatsapp/status')
  })

  it('crea y elimina el vínculo con CSRF', async () => {
    vi.stubGlobal('document', { cookie: 'csrf_token=verified-token' })
    const fetcher = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({
        status: 'pending', masked_phone: '+57******4567', code: 'AB23CD', expires_at: '2026-09-16T20:10:00Z',
      }), { status: 201 }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetcher)

    await expect(startWhatsAppLink('+573001234567')).resolves.toMatchObject({ code: 'AB23CD' })
    await unlinkWhatsApp()

    expect(fetcher.mock.calls[0]![0]).toBe('/api/v1/whatsapp/link')
    expect(fetcher.mock.calls[0]![1].method).toBe('POST')
    expect(fetcher.mock.calls[0]![1].body).toBe(JSON.stringify({ phone: '+573001234567' }))
    expect(new Headers(fetcher.mock.calls[0]![1].headers).get('X-CSRF-Token')).toBe('verified-token')
    expect(fetcher.mock.calls[1]![1].method).toBe('DELETE')
  })
})
