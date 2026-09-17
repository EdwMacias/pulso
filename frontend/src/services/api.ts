export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message) }
}
export async function api<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  if (options.method && !['GET', 'HEAD'].includes(options.method)) {
    const token = typeof document === 'undefined' ? '' : document.cookie.split('; ').find(c => c.startsWith('csrf_token='))?.slice(11)
    if (token) headers.set('X-CSRF-Token', decodeURIComponent(token))
  }
  let response: Response
  try { response = await fetch(`/api/v1${path}`, { ...options, headers, credentials: 'include' }) }
  catch { throw new ApiError('No se pudo conectar con el servidor. Inténtalo de nuevo.', 0) }
  const data = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = data?.detail
    const message = typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map((e: any) => e.msg).join('. ') : 'No se pudo completar la solicitud.'
    if (response.status === 401 && typeof window !== 'undefined') window.dispatchEvent(new Event('session-expired'))
    throw new ApiError(message, response.status)
  }
  return data as T
}
