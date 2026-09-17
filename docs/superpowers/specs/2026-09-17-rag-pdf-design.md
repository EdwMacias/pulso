# RAG para documentos PDF

## Objetivo

Incorporar una sección privada de documentos donde cada usuario autenticado pueda
subir un PDF con texto seleccionable y formular preguntas sobre su contenido.
Las respuestas se generarán con Groq y citarán las páginas de los fragmentos que
sirvieron como contexto.

## Alcance

- Pantalla Vue `Documentos`: listado, carga de un PDF, estado, eliminación y
  conversación por documento.
- API autenticada para crear, listar, consultar, preguntar y eliminar
  documentos.
- Extracción local del texto del PDF, división en fragmentos acotados por
  página y búsqueda textual local.
- Generación remota de la respuesta con el modelo Groq ya configurado.
- Aislamiento estricto por `user_id` para documentos, fragmentos y archivos.

No se implementarán embeddings ni una base de datos vectorial en este primer
incremento. Tampoco se admitirán OCR, PDFs escaneados o procesamiento asíncrono.

## Arquitectura y flujo

1. El navegador envía un PDF mediante `multipart/form-data` al backend.
2. El backend valida tipo, extensión, tamaño y número de páginas, guarda el
   archivo con un nombre no predecible en un directorio privado configurable y
   crea un documento en estado `processing`.
3. `pypdf` extrae el texto de cada página. El backend lo normaliza y lo divide
   en fragmentos de longitud limitada, conservando página y orden.
4. Si se obtienen fragmentos, se guardan y el documento pasa a `ready`; si no,
   pasa a `failed`, se elimina el archivo y se registra un error apto para el
   usuario.
5. Ante una pregunta, el backend verifica que el documento pertenece al
   usuario, selecciona los fragmentos con más términos de la pregunta y los
   incluye como contexto delimitado en la solicitud a Groq.
6. La respuesta retorna texto y páginas fuente, sin exponer rutas internas ni
   contenido de otros documentos.

## Persistencia

`documents` guardará: propietario, nombre original, ruta interna, tamaño,
cantidad de páginas, estado, mensaje de error y marcas de tiempo.

`document_chunks` guardará: documento, índice, número de página y texto. Un
índice compuesto por documento y orden permitirá recuperar los fragmentos de
forma determinista.

`DOCUMENT_STORAGE_PATH`, `DOCUMENT_MAX_UPLOAD_BYTES`,
`DOCUMENT_MAX_PAGES`, `DOCUMENT_MAX_CONTEXT_CHUNKS` y
`DOCUMENT_MAX_CONTEXT_CHARS` serán configuración del backend con valores
conservadores. El directorio de archivos no se publicará como estático.

## API

- `GET /api/v1/documents`: lista resumida de documentos del usuario.
- `POST /api/v1/documents`: recibe el archivo PDF y devuelve el documento
  procesado o el error de validación.
- `GET /api/v1/documents/{id}`: detalle del documento propio.
- `POST /api/v1/documents/{id}/questions`: recibe una pregunta y devuelve la
  respuesta de Groq y sus páginas fuente.
- `DELETE /api/v1/documents/{id}`: elimina filas y archivo privado del
  documento propio.

Las rutas mutables conservan el mecanismo CSRF actual. Los identificadores de
otro usuario se responderán como no encontrados.

## Interfaz

La navegación incorporará `Documentos`. La vista mostrará el selector de PDF,
las restricciones, la lista de documentos y el detalle del elemento
seleccionado. Solo los documentos `ready` habilitan preguntas. Estados de
procesamiento, error de extracción y ausencia de Groq se comunicarán sin
revelar detalles internos.

## Errores y seguridad

- Rechazar tipos que no sean PDF, tamaños y páginas por encima de los límites,
  archivos corruptos y PDFs sin texto extraíble.
- Tratar el contenido recuperado como datos no confiables: el prompt indicará a
  Groq que responda a la pregunta del usuario y no siga instrucciones presentes
  en el PDF.
- Limitar contexto y longitud de pregunta para evitar consumo excesivo y
  entradas descontroladas.
- Nunca enviar el archivo completo ni almacenarlo en una ruta pública.

## Pruebas y validación

Las pruebas de backend cubrirán validación, extracción y fragmentación,
aislamiento por usuario, selección de contexto, errores de configuración Groq y
borrado físico. Las pruebas unitarias de frontend cubrirán carga, estados y
presentación de fuentes. Al finalizar se ejecutarán pytest, Vitest y la
compilación de producción de Vue.
