# Medición y tracking

## Índice

1. Modelo de eventos
2. Implementación
3. Consentimiento y privacidad
4. Reconciliación
5. Atribución e incrementalidad

## 1. Modelo de eventos

Empezar por la decisión de negocio. Definir:

- evento primario usado para optimizar;
- eventos diagnósticos del funnel;
- valor, moneda, transaction/order/lead ID;
- fuente de verdad;
- momento en que el evento se considera válido;
- reglas de cancelación, devolución, duplicado o spam.

Para leads, devolver desde CRM etapas como cualificado, oportunidad y venta cuando volumen, consentimiento y plataforma lo permitan.

## 2. Implementación

Verificar:

- tag/pixel cargado en páginas correctas;
- evento una sola vez por acción;
- IDs estables y deduplicación cliente/servidor;
- value y currency correctos;
- parámetros requeridos y match keys minimizados;
- UTMs y click IDs preservados;
- cross-domain y referrals;
- CRM/offline uploads;
- diagnósticos y latencia;
- entorno de prueba separado de producción.

Usar Pixel/Tag + CAPI/Events API cuando aporte resiliencia y cumpla política. Server-side no significa enviar todo: compartir solo lo necesario.

## 3. Consentimiento y privacidad

- Ajustar tags y SDKs a la elección real del usuario.
- Implementar Consent Mode, CMP, ATT o controles equivalentes según plataforma, mercado y producto.
- No usar identificadores alternativos para evadir una negativa.
- Documentar base legal, retención, responsables y vendors con revisión jurídica cuando aplique.
- Hashing no anonimiza por sí solo ni convierte cualquier envío en permitido.
- Mantener privacy labels, disclosures y políticas sincronizadas con la implementación.

## 4. Reconciliación

Comparar por periodos maduros:

- backend/CRM;
- analytics;
- plataforma publicitaria;
- procesador de pagos o tienda.

Documentar diferencias esperadas por zona horaria, ventanas, view-through, modelado, identidad, devoluciones, cross-device, ad blockers y retrasos.

No forzar igualdad exacta ni sumar conversiones reportadas por plataformas como si fueran usuarios únicos.

## 5. Atribución e incrementalidad

Distinguir:

- **observación:** evento registrado;
- **atribución:** regla/modelo asigna crédito;
- **modelado:** estima eventos o crédito no observable;
- **incrementalidad:** estima qué ocurrió por la publicidad frente al contrafactual.

Usar:

- atribución para operación diaria y journey;
- experimentos A/B para cambios de campaña;
- conversion/brand/search lift para causalidad dentro de plataforma;
- geo experiments cuando correspondan;
- MMM para contribución agregada multicanal y largo plazo, con datos suficientes;
- post-purchase surveys como señal complementaria.

Calibrar modelos con experimentos cuando sea posible. No desplegar Meridian, Robyn o un MMM porque “suena senior”; hacerlo solo con suficiente historia, variación, calidad de datos y capacidad analítica.
