import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api, ApiError } from '../services/api'
export const useSession = defineStore('session', () => {
  const user = ref<{ id: string; email: string; timezone: string; email_verified_at: string | null } | null>(null)
  const loaded = ref(false)
  async function restore() {
    try { const account = await api('/auth/me'); user.value = account.email_verified_at ? account : null }
    catch (e) { if (!(e instanceof ApiError) || e.status !== 401) throw e; user.value = null }
    finally { loaded.value = true }
  }
  async function authenticate(mode: string, email: string, password: string) {
    const data = await api(`/auth/${mode}`, { method: 'POST', body: JSON.stringify({ email, password }) })
    if (!data.verification_required) { user.value = data.user; loaded.value = true }
    return data
  }
  async function logout() { await api('/auth/logout', { method: 'POST' }); user.value = null }
  return { user, loaded, restore, authenticate, logout }
})
