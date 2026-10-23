# Economía y presupuesto

## Índice

1. Datos mínimos
2. Cálculos
3. Presupuesto de aprendizaje
4. Forecasts
5. Escala

## 1. Datos mínimos

Recoger antes de recomendar inversión:

- ingreso neto por venta o contrato;
- descuentos, impuestos y devoluciones;
- COGS y costes variables de entrega, pago, soporte y fulfillment;
- margen de contribución;
- repetición, churn y horizonte usado para LTV;
- tasa lead -> cualificado -> oportunidad -> venta;
- ciclo de venta y retraso de revenue;
- capacidad de inventario, ventas, onboarding y soporte;
- restricción de caja y payback aceptable.

No usar revenue bruto como beneficio disponible para adquisición.

## 2. Cálculos

### Ecommerce o transacción

```text
margen_contribucion = ingreso_neto - costes_variables_sin_ads
tasa_margen = margen_contribucion / ingreso_neto
roas_equilibrio = 1 / tasa_margen
cac_maximo = margen_contribucion_acumulado_en_horizonte - beneficio_objetivo
```

Incluir repetición solo cuando exista evidencia por cohorte. Ajustar por devoluciones, fraude, descuentos y coste de capital cuando sean materiales.

### Leads

```text
cpl_maximo = cac_maximo * tasa_lead_a_cliente
cpql_maximo = cac_maximo * tasa_cualificado_a_cliente
```

Usar tasas recientes y segmentadas por fuente cuando existan. Una campaña con CPL bajo puede destruir valor si entrega leads no contactables o no cualificados.

### SaaS o suscripción

Calcular CAC, margen bruto, payback y LTV por cohorte. No usar `ARPU / churn` sin declarar sus supuestos; falla con churn variable, expansión, contracción o cohortes inmaduras.

## 3. Presupuesto de aprendizaje

Definir el presupuesto desde:

- coste esperado del evento de optimización;
- cantidad de eventos necesaria para una decisión útil;
- duración mínima para cubrir variación semanal y ciclo de conversión;
- número de hipótesis realmente aisladas;
- pérdida máxima aceptable.

No aplicar multiplicadores universales. Consultar requisitos actuales de la plataforma y adaptar a volumen, mercado y riesgo.

Separar:

- presupuesto de aprendizaje;
- presupuesto operativo;
- reserva para pruebas;
- presupuesto de escala.

## 4. Forecasts

Entregar escenarios, no una cifra falsa:

- conservador;
- base;
- favorable.

Para cada escenario mostrar supuestos de CPM/CPC, CVR, CPA, ticket, margen, retraso y calidad. Incluir sensibilidad: qué variable cambia más el resultado.

No presentar el forecast como promesa. Comparar luego forecast vs. real y recalibrar.

## 5. Escala

Escalar solo si:

- tracking y negocio concuerdan dentro de una discrepancia explicada;
- CAC/payback cumplen el límite;
- calidad posterior a la conversión se mantiene;
- inventario y operaciones soportan volumen;
- no se agotó el ángulo creativo;
- el efecto no depende únicamente de atribución de marca o retargeting.

Preferir cambios reversibles y graduales. Vigilar marginal CAC/ROAS, no solo el promedio histórico.
