<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { ListChecks } from 'lucide-vue-next'
import { ApiError } from '../services/api'
import { addDocumentTasks, invoiceTitle, suggestDocumentTasks, type InvoiceKind, type TaskSuggestion } from '../services/documents'

const props = defineProps<{ documentId: string; autoload?: boolean }>()
const emit = defineEmits<{ created: [message: string] }>()
type Row = TaskSuggestion & { selected: boolean; withReminder: boolean }
const rows = ref<Row[] | null>(null), loading = ref(false), saving = ref(false), error = ref('')

const priorityLabel = { high: 'Alta', medium: 'Media', low: 'Baja' }
const formatDate = (value: string) => new Intl.DateTimeFormat('es', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
const isFuture = (value: string | null) => !!value && new Date(value).getTime() > Date.now()

async function extract() {
  loading.value = true; error.value = ''; rows.value = null
  try {
    const { suggestions } = await suggestDocumentTasks(props.documentId)
    rows.value = suggestions.map(item => ({ ...item, selected: true, withReminder: isFuture(item.remind_at) }))
  } catch (cause) {
    error.value = cause instanceof ApiError && cause.status === 503 ? 'Groq no está configurado o no respondió.' : 'No se pudieron extraer tareas.'
  } finally { loading.value = false }
}

function setKind(row: Row, kind: InvoiceKind) { row.kind = kind; row.title = invoiceTitle(row, kind) }

async function save() {
  const chosen = rows.value?.filter(row => row.selected && row.title.trim()) ?? []
  if (!chosen.length) return
  saving.value = true; error.value = ''
  try {
    const tasks = chosen.map(({ selected, withReminder, ...task }) => ({ ...task, title: task.title.trim(), remind_at: withReminder ? task.remind_at : null }))
    const result = await addDocumentTasks(props.documentId, tasks)
    rows.value = null
    emit('created', `${result.created_tasks} tareas agregadas${result.created_reminders ? ` con ${result.created_reminders} recordatorios` : ''}.`)
  } catch { error.value = 'No se pudieron agregar las tareas.' } finally { saving.value = false }
}

watch(() => props.documentId, () => { rows.value = null; error.value = '' })
onMounted(() => { if (props.autoload) extract() })
</script>

<template>
  <section class="task-suggestions">
    <div class="section-header">
      <h3><ListChecks :size="16" /> Tareas del documento</h3>
      <button class="text-button" :disabled="loading" @click="extract">{{ loading ? 'Analizando…' : rows ? 'Volver a extraer' : 'Extraer tareas' }}</button>
    </div>
    <p v-if="!rows && !loading && !error" class="small">Pulso puede detectar pendientes (vuelos, facturas, citas, plazos) y proponerlos como tareas. Nada se guarda sin tu confirmación.</p>
    <p v-if="error" class="small danger">{{ error }}</p>
    <p v-if="rows && !rows.length" class="small">No se encontraron tareas pendientes en este documento.</p>
    <template v-if="rows?.length">
      <article v-for="(row, index) in rows" :key="index" class="suggestion" :class="{ off: !row.selected }">
        <input v-model="row.selected" type="checkbox" :aria-label="`Incluir ${row.title}`">
        <div>
          <input v-model="row.title" class="suggestion-title" maxlength="200" aria-label="Título de la tarea">
          <div v-if="row.kind !== 'general'" class="invoice-toggle" role="group" aria-label="Tipo de factura">
            <button :class="{ selected: row.kind === 'cobro' }" @click="setKind(row, 'cobro')">Cobro · yo vendí</button>
            <button :class="{ selected: row.kind === 'pago' }" @click="setKind(row, 'pago')">Pago · yo compré</button>
            <span v-if="row.amount">{{ row.amount }}</span><span v-if="row.due_date">vence {{ row.due_date }}</span>
          </div>
          <p v-if="row.description" class="small">{{ row.description }}</p>
          <div class="suggestion-meta">
            <span class="priority" :class="row.priority">{{ priorityLabel[row.priority] }}</span>
            <label v-if="isFuture(row.remind_at)"><input v-model="row.withReminder" type="checkbox"> Recordar {{ formatDate(row.remind_at!) }}</label>
            <span v-else-if="row.remind_at">Fecha pasada: sin recordatorio</span>
            <span v-if="row.page">Página {{ row.page }}</span>
          </div>
          <blockquote v-if="row.evidence">«{{ row.evidence }}»</blockquote>
        </div>
      </article>
      <button class="primary" :disabled="saving || !rows.some(row => row.selected)" @click="save">{{ saving ? 'Agregando…' : `Agregar ${rows.filter(row => row.selected).length} seleccionadas` }}</button>
    </template>
  </section>
</template>
