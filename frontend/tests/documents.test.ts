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
