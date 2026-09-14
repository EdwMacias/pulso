# Progreso de implementación

Plan de referencia: `plan.md`.

## Primer incremento

- API: autenticación, aislamiento, tareas, recordatorios persistentes, analítica básica y chat Groq configurable.
- Web: Vue 3 con login, agenda, creación de tareas y avisos, chat, actividad y configuración.
- Operación local: SQLite para iniciar sin servicios adicionales; PostgreSQL mediante Docker Compose.
- Validación: pruebas de API, cliente HTTP, compilación TypeScript y flujo E2E real.

## Decisiones

- No existe repositorio Git; se trabaja en la carpeta nueva solicitada sin crear worktrees ni commits.
- No se han proporcionado credenciales: las pruebas externas de WhatsApp, Groq y TTS quedan pendientes. La interfaz no debe simular conexiones o entregas.
- El scheduler inicial entrega notificaciones internas persistidas. Transporte WhatsApp, outbox distribuida y Redis/Celery pertenecen al siguiente incremento.
- El acceso sin verificación de correo solo se permite en modo de desarrollo explícito. Los tokens de correo de desarrollo se guardan en una outbox privada local.
- Superdesign requiere autenticación externa. Se continúa con una interfaz funcional local siguiendo el diseño ya aprobado.

## Contratos compartidos

| Productor | Consumidor | Contrato |
| --- | --- | --- |
| API auth | Vue sesión | Cookie de sesión + cookie `csrf_token`; cabecera `X-CSRF-Token` para escrituras |
| API tareas | Agenda | Arrays JSON y campos `id`, `title`, `priority`, `status` |
| API recordatorios | Formularios | Fecha ISO con offset, zona IANA, recurrencia `none/daily/weekly` |
| Estado integraciones | Ajustes/chat | Mostrar `configured` y `available` por separado |

Estado: en desarrollo; consultar README para capacidades verificadas al terminar.
