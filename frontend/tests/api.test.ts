import { describe, it, expect, vi, afterEach } from 'vitest'
import { api, ApiError } from '../src/services/api'
afterEach(() => vi.unstubAllGlobals())
describe('cliente de API', () => {
  it('envía cookies y CSRF en escrituras', async () => {
    vi.stubGlobal('document', { cookie: 'csrf_token=verified-token' })
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: 1 })))
    vi.stubGlobal('fetch', fetcher)
    expect(await api('/tasks', { method: 'POST', body: JSON.stringify({ title: 'Informe' }) })).toEqual({ id: 1 })
    const init = fetcher.mock.calls[0]![1]
    expect(init.credentials).toBe('include')
    expect(new Headers(init.headers).get('X-CSRF-Token')).toBe('verified-token')
  })
  it('convierte errores del backend en mensajes legibles', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'Sesión expirada' }), { status: 401 })))
    await expect(api('/auth/me')).rejects.toMatchObject({ message: 'Sesión expirada', status: 401 })
  })
  it('no trata un fallo del servidor como éxito', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('Bad gateway', { status: 502 })))
    await expect(api('/tasks')).rejects.toBeInstanceOf(ApiError)
  })
})
