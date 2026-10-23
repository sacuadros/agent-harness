# Playbook SEO

## Índice

1. Orden de diagnóstico
2. Contenido y on-page
3. Datos estructurados
4. AI search
5. Casos específicos
6. Medición

## 1. Orden de diagnóstico

### Descubrimiento e indexación

Verificar, según el alcance:

- respuesta HTTP, redirects y renderizado;
- robots.txt, robots meta y controles de snippets;
- canonical, duplicados y parámetros;
- sitemap y enlaces internos rastreables;
- estado de indexación y URL Inspection;
- JS crítico, recursos bloqueados y contenido visible;
- migraciones, hreflang y paginación cuando apliquen.

No recomendar más contenido hasta descartar que las páginas importantes sean inaccesibles, duplicadas o no indexables.

### Arquitectura

- Agrupar por tareas y entidades reales, no por listas artificiales de keywords.
- Mantener rutas claras desde navegación y hubs hacia páginas valiosas.
- Usar anchor text descriptivo sin sobreoptimización.
- Consolidar páginas que compiten por la misma intención cuando no aporten diferencias útiles.

### Experiencia

Evaluar datos de campo. Objetivos Core Web Vitals en percentil 75:

- LCP <= 2.5 s
- INP <= 200 ms
- CLS <= 0.1

No presentar Core Web Vitals como único factor de experiencia ni corregirlos sin medir la causa real.

## 2. Contenido y on-page

Definir una intención primaria y las necesidades secundarias que la página debe resolver. Analizar la SERP como evidencia del mercado actual, no como plantilla para copiar.

Exigir valor adicional:

- experiencia directa;
- datos, pruebas o ejemplos propios;
- comparación útil;
- síntesis que permita decidir;
- herramientas, plantillas o explicación operacional;
- autoría y fuentes apropiadas al riesgo del tema.

Optimizar:

- title descriptivo y diferenciado;
- H1 y headings que permitan escanear;
- respuesta temprana cuando la intención lo permita;
- imágenes y vídeo útiles, con alternativas accesibles;
- enlaces internos relevantes;
- fecha solo cuando exista una actualización sustancial;
- byline, autor o proceso cuando aumenten confianza.

Evitar keyword stuffing, FAQs de relleno, contenido sin audiencia real, cambios cosméticos de fecha y conteos arbitrarios de palabras.

## 3. Datos estructurados

- Usar primero la documentación de la superficie objetivo; Schema.org define vocabulario, no elegibilidad en Google.
- Elegir el tipo más específico compatible con el contenido visible.
- Incluir propiedades requeridas y solo propiedades recomendadas que sean exactas y mantenibles.
- Validar sintaxis y también calidad; un test válido no garantiza rich result.
- Desplegar primero en una muestra, inspeccionar URLs y medir antes/después.
- Retirar markup de features deprecadas cuando ya no aporte a otros consumidores.

## 4. AI search

Aplicar los mismos fundamentos: accesibilidad para crawlers, contenido útil, evidencia, claridad de entidades, información fresca y fuentes confiables. No afirmar que una estructura, archivo o schema especial garantiza citación.

Para aumentar la posibilidad de ser comprendido y citado:

- responder preguntas concretas sin ocultar el contexto;
- mantener hechos, nombres, fechas y relaciones consistentes;
- aportar información original verificable;
- usar headings, tablas o listas solo cuando mejoren comprensión;
- permitir rastreo según los controles elegidos por el propietario;
- mantener contenido y datos estructurados sincronizados.

Medir por motor cuando existan datos oficiales. Tratar herramientas GEO de terceros como indicadores exploratorios, no como ground truth.

## 5. Casos específicos

### Ecommerce

- Mantener precio, disponibilidad, identificadores, variantes, envío y devoluciones coherentes entre página, schema y feeds.
- Considerar IndexNow para cambios rápidos en motores participantes.
- Evitar páginas de variantes o filtros sin valor independiente.

### Local

- Mantener nombre, dirección, teléfono, horarios y categorías consistentes.
- Gestionar perfiles oficiales, reviews reales y páginas locales con contenido propio.
- No crear páginas geográficas clonadas.

### Internacional

- Elegir URLs estables por idioma/mercado.
- Implementar hreflang recíproco y canonical compatible.
- Localizar intención, oferta y evidencia; no traducir keywords literalmente.

## 6. Medición

Usar Search Console y herramientas oficiales para:

- indexación y errores;
- impresiones, clics, CTR, queries y páginas;
- rich results;
- Core Web Vitals de campo;
- acciones manuales y seguridad.

Conectar visibilidad con resultado: conversión orgánica, leads cualificados, revenue o tarea completada. Segmentar cambios de marca, estacionalidad, migraciones, releases y updates conocidos antes de atribuir causalidad.
