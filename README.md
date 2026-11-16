# radiografia-proceso
# Radiografía del Proceso de Compras

Proyecto compuesto por dos aplicaciones internas construidas bajo reglas de gobernanza y protección de datos.

## 1. Gobernanza y Protección de Datos (`protector-final.html`)
Aplicación HTML local 100 % offline para anonimizar archivos CSV antes de cualquier análisis:
- **Conservar:** `caso`, `paso`, `rol`, `fecha_hora`, `centro_costo`, `monto_usd`
- **Seudonimizar:** `responsable`, `solicitante` (34 personas convertidas a códigos `Persona_001`...`Persona_034`)
- **Enmascarar:** `proveedor` → `[PROVEEDOR]`
- **Eliminar:** `cedula_solicitante`, `correo_solicitante`, `telefono_solicitante`, `nit_proveedor`
- **Limpiar texto:** `comentario` (1.569 comentarios sanitizados; **0 fugas** de `@`, cédulas, teléfonos o nombres propios)

## 2. Hallazgos de Dr. Proceso (`app.py`)
Análisis ejecutado sobre `movimientos_compras_2026_protegido.csv`:
- **Volumen:** 2.040 solicitudes únicas y 14.672 movimientos.
- **Caminos reales:** 6 secuencias distintas; el flujo ideal sin devoluciones representa solo el **28.38 %** (579 solicitudes).
- **Retrabajo / Devoluciones:** **50.00 %** de las solicitudes (1.020 casos) tuvieron al menos una devolución (`Devolver al solicitante`).
- **Tiempos y cuello de botella:** Duración promedio de **14.04 días** calendario por solicitud (mínima: **2.95 días**, máxima: **40.85 días**). La etapa con mayor espera promedio es **Emitir orden de compra** (**4.16 días**), seguida de **Firmar Contraloría** (**3.51 días**).

## 3. Recomendaciones
- Implementar validaciones obligatorias previas al envío para reducir el 50 % de devoluciones.
- Revisar la carga operativa y tiempos de respuesta en la emisión de órdenes de compra y firma de Contraloría.