<script setup lang="ts">
import { computed, ref } from 'vue'
import { highlightSegments, type DocumentAnswer } from '../services/documents'

const props = defineProps<{ answer: DocumentAnswer }>()
const expanded = ref<number | null>(null)
const maxScore = computed(() => Math.max(...props.answer.sources.map(source => source.score), 1))
const steps = computed(() => [
  { label: 'Pregunta', detail: 'términos normalizados' },
  { label: 'Recuperación BM25', detail: `${props.answer.total_chunks} fragmentos analizados` },
  { label: 'Contexto', detail: `${props.answer.sources.length} fragmentos enviados` },
  { label: 'Generación', detail: props.answer.sources.length ? 'Groq responde citando páginas' : 'sin contexto, no se consulta al modelo' },
])
</script>

<template>
  <section class="rag-sources" aria-label="Fuentes recuperadas">
    <ol class="rag-pipeline">
      <li v-for="(step, index) in steps" :key="step.label"><span>{{ index + 1 }}</span><div><strong>{{ step.label }}</strong><small>{{ step.detail }}</small></div></li>
    </ol>
    <h3>Fuentes recuperadas</h3>
    <p v-if="!answer.sources.length" class="small">Ningún fragmento contiene los términos de la pregunta.</p>
    <article v-for="(source, index) in answer.sources" :key="source.chunk_index" class="rag-source">
      <header>
        <strong>#{{ index + 1 }} · Página {{ source.page_number }}</strong>
        <span class="rag-meta">Fragmento {{ source.chunk_index + 1 }} · puntuación {{ source.score.toFixed(2) }}</span>
      </header>
      <div class="rag-score" :title="`BM25 ${source.score}`"><span :style="{ width: `${(source.score / maxScore) * 100}%` }"></span></div>
      <div class="rag-terms"><span v-for="term in source.matched_terms" :key="term">{{ term }}</span></div>
      <p :class="{ clamped: expanded !== source.chunk_index }"><template v-for="(segment, position) in highlightSegments(source.content, source.matched_terms)" :key="position"><mark v-if="segment.match">{{ segment.text }}</mark><template v-else>{{ segment.text }}</template></template></p>
      <button class="text-button" @click="expanded = expanded === source.chunk_index ? null : source.chunk_index">{{ expanded === source.chunk_index ? 'Ver menos' : 'Ver fragmento completo' }}</button>
    </article>
  </section>
</template>
