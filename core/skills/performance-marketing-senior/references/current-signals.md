# Señales actuales

Última revisión: 2026-07-15

Verificar en vivo antes de decisiones de alto impacto.

### 2026-08-17 — Cambios próximos en target-based bidding de Google Ads

- Estado: próximo
- Plataforma/mercado: Google Ads; Search, Shopping, Performance Max, Demand Gen y Travel
- Fuente: https://support.google.com/google-ads/answer/17125145
- Hecho: Google anunció cambios para optimizar más consistentemente hacia targets, incluidos casos limited by budget.
- Impacto: revisar targets y campañas limited by budget antes del despliegue; Google no cambiará automáticamente budgets o targets.
- Acción: TUNE
- Revisar después de: 2026-08-17

### 2026-07 — TikTok despliega Smart+ con control graduable

- Estado: despliegue
- Plataforma/mercado: TikTok Ads Manager, disponibilidad por cuenta/mercado
- Fuente: https://ads.tiktok.com/help/
- Hecho: TikTok comunica una experiencia Smart+ actualizada con opciones de automatización total, parcial o control manual.
- Impacto: verificar controles disponibles en la cuenta; no migrar campañas solo por disponibilidad.
- Acción: PILOT

### 2026-06 — Google cambia etiquetas de Smart Bidding

- Estado: despliegue
- Plataforma/mercado: Google Ads Search
- Fuente: https://support.google.com/google-ads/answer/7065882
- Hecho: Maximize conversions con target CPA pasa a mostrarse como Target CPA y Maximize conversion value con target ROAS como Target ROAS; el comportamiento subyacente no cambia por el renombre.
- Impacto: actualizar documentación y evitar tratar el cambio visual como una nueva estrategia.
- Acción: TUNE

### 2026-06-15 — Enhanced conversions for leads migra a Data Manager API

- Estado: activo
- Plataforma/mercado: Google Ads
- Fuente: https://support.google.com/google-ads/answer/15713840
- Hecho: uploads de offline conversions y enhanced conversions for leads se migraron hacia Data Manager API, con restricciones para Google Ads API legacy.
- Impacto: auditar integraciones legacy y diagnósticos antes de asumir continuidad.
- Acción: TUNE

### 2026-03 — Meta refuerza medición por incrementalidad

- Estado: activo
- Plataforma/mercado: Meta Ads
- Fuente: https://about.fb.com/ltam/news/2026/03/simplificando-la-medicion-de-anuncios-para-un-mundo-social-first/
- Hecho: Meta presenta Conversion Lift como referencia para responder al impacto causal de anuncios.
- Impacto: no equiparar atribución reportada con incrementalidad; usar lift cuando sea elegible.
- Acción: KEEP

### Vigente — APIs de conversiones complementan tags, no el consentimiento

- Estado: activo
- Plataforma/mercado: Meta, TikTok y LinkedIn
- Fuentes: https://www.facebook.com/business/help/AboutConversionsAPI | https://ads.tiktok.com/help/article/events-api | https://www.linkedin.com/help/lms/answer/a9917045
- Hecho: las plataformas recomiendan conexiones servidor/CRM junto con pixel/tag y deduplicación para resiliencia y medición.
- Impacto: implementar minimización, consentimiento y deduplicación; no usar server-side para evadir restricciones.
- Acción: KEEP

### Vigente — Consent Mode v2 añade parámetros publicitarios

- Estado: activo
- Plataforma/mercado: Google Tag Platform
- Fuente: https://developers.google.com/tag-platform/security/guides/consent
- Hecho: Consent Mode v2 incluye `ad_user_data` y `ad_personalization` además de storage controls.
- Impacto: adaptar comportamiento a la elección real y región; Consent Mode no sustituye una CMP o base legal cuando sean necesarias.
- Acción: KEEP
