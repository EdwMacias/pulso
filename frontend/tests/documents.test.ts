import { describe, it, expect } from 'vitest'
import { highlightSegments, normalizeTerm } from '../src/services/documents'
describe('resaltado de fuentes RAG', () => {
  it('normaliza igual que el backend', () => {
    expect(normalizeTerm('Contraseñas')).toBe('contrasena')
    expect(normalizeTerm('días')).toBe('dias')
  })
  it('marca solo los términos recuperados, sin importar acentos', () => {
    const segments = highlightSegments('Las Vacaciones son de quince días.', ['vacacione', 'dias'])
    expect(segments.filter(s => s.match).map(s => s.text)).toEqual(['Vacaciones', 'días'])
    expect(segments.map(s => s.text).join('')).toBe('Las Vacaciones son de quince días.')
  })
})
describe('facturas a crédito', () => {
  const base = { title: 'Pagar factura FV-1 a Acme', description: null, priority: 'high' as const, remind_at: null, page: 1, evidence: null, kind: 'pago' as const, invoice_number: 'FV-1', issuer: 'Acme', customer: 'Mi Tienda', amount: 'COP 100', due_date: '2030-01-01' }
  it('cobra al cliente y paga al emisor', async () => {
    const { invoiceTitle } = await import('../src/services/documents')
    expect(invoiceTitle(base, 'cobro')).toBe('Cobrar factura FV-1 a Mi Tienda')
    expect(invoiceTitle(base, 'pago')).toBe('Pagar factura FV-1 a Acme')
    expect(invoiceTitle({ ...base, invoice_number: null, customer: null }, 'cobro')).toBe('Cobrar factura')
  })
})
