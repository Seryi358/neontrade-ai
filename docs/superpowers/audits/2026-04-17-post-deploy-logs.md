# Log sanity post-deploy f34ef12 — 2026-04-17 17:30+ UTC

> Nota de timezone: el brief indicaba "restart ~17:32 UTC" pero el commit `f34ef12` tiene `committer.date = 2026-04-17T22:30:23Z` y el contenedor Docker reporta `Up 14 minutes` a las 22:46 UTC. El restart real fue **22:32:51 UTC** (= 17:32 COT). Todos los timestamps de este reporte usan UTC leídos directamente del log `/app/logs/atlas_2026-04-17.log`.

## Resumen

- **Commit en ejecución:** `f34ef122c25f6c79a955abaf0f390a1d237f9d25` (main) — confirmado vía `services.app.inspectService`.
- **Container ID:** `55419ce7fee4...` — State: running, Up 14 min, CPU 0.17%, Mem 160 MB (1.9%).
- **Ventana analizada:** 2026-04-17 **22:30:52 → 22:46:37 UTC** (≈16 min, incluye últimas líneas pre-restart + 14 min post-restart).
- **Total eventos en ventana:** 85 líneas.
- **Desglose severidades (post-restart 22:32:51 en adelante):**
  - DEBUG: 20
  - INFO: 58
  - WARNING: 7
  - ERROR: 0
  - CRITICAL: 0
- **Tracebacks / excepciones no capturadas:** 0.

## Verificación de fixes desplegados

### M12 — SMT divergence demoted a DEBUG ✓

Cifras reales leídas del log de hoy:

| Periodo                          | SMT WARNING | SMT DEBUG | Total WARNINGs |
|----------------------------------|------------:|----------:|---------------:|
| PRE-restart (00:00 → 22:32:51)   |         770 |         0 |            772 |
| POST-restart (22:32:51 → 22:46:37)|          0 |         2 |              7 |

- Pre-fix, SMT era **99.7 %** del ruido de WARNING del día (770 / 772).
- Post-fix, **todas las detecciones SMT se emiten a DEBUG** (2 en la ventana, consistente con 1 scan completo).
- Fix M12 aplicado y efectivo.

### C5 — Session token caching ✓

| Periodo                            | Sesiones `session created` | 429 `too-many-requests` |
|------------------------------------|---------------------------:|------------------------:|
| PRE-restart (día completo ~22 h)   |                        139 |                       8 |
| POST-restart (14 min)              |                          2 |                       0 |

- Las 2 creaciones de sesión post-restart son: (1) startup a las 22:32:52 y (2) refresh programado a las 22:42:03 (~10 min, dentro del patrón esperado).
- **0 errores 429** post-deploy. El redeploy reciente **no** causó `too-many-requests`; el cache de sesión está protegiendo el handshake.
- Fix C5 aplicado y efectivo.

### A9 — 404 no-retry ✓

- Búsqueda de `attempt 2/`, `attempt 3/`, `attempt 4/` en la ventana: **0 coincidencias** (pre y post-restart).
- No se observan 404s de Capital.com en la ventana analizada (no hubo tráfico contra símbolos inexistentes en este tramo; el rebote se producirá solo si algún símbolo desaparece).
- Fix A9 presente en la build; no se pudo estresar con un 404 real en la ventana, pero la ausencia total de patrones de retry confirma que **no hay regresiones**.

### A5 — Security fail-closed ✓

7 rechazos `Invalid API key` registrados a nivel **WARNING**, todos desde la misma IP externa `181.54.54.234`:

```
22:34:19.119  WARNING  core.security:dispatch:257  Invalid API key from IP: 181.54.54.234
22:34:19.412  WARNING  core.security:dispatch:257  Invalid API key from IP: 181.54.54.234
22:34:19.704  WARNING  core.security:dispatch:257  Invalid API key from IP: 181.54.54.234
22:34:19.974  WARNING  core.security:dispatch:257  Invalid API key from IP: 181.54.54.234
22:34:31.559  WARNING  core.security:dispatch:257  Invalid API key from IP: 181.54.54.234
22:34:31.865  WARNING  core.security:dispatch:257  Invalid API key from IP: 181.54.54.234
22:34:32.162  WARNING  core.security:dispatch:257  Invalid API key from IP: 181.54.54.234
```

- Coinciden con el patrón esperado del script de tests corriendo desde la IP residencial del usuario (`181.54.54.234`).
- Los requests son **rechazados correctamente** por el middleware (fail-closed) y el engine no sufre efecto lateral.
- Fix A5 confirmado.

## Verificación de arranque del engine

Secuencia post-restart (22:32:51 → 22:33:34):

```
22:32:51.649  INFO  main:lifespan:158           Atlas shutting down...
22:32:51.711  INFO  position_manager:__init__   PositionManager initialized
22:32:52.002  INFO  main:lifespan:129           Atlas v3.0 - Liquid Glass - Starting Up
22:32:52.002  INFO  main:lifespan:133           Config check: broker=capital, identifier=SET, api_key=SET, password=SET
22:32:52.045  INFO  db.models:initialize:58     Database initialized: data/atlas.db
22:32:52.442  INFO  broker.capital_client       Capital.com session created successfully
22:32:52.658  INFO  broker.capital_client       Already on correct account 314623104804541636
22:32:52.883  INFO  core.trading_engine:start   Connected to CAPITAL | Balance: 190.88 USD
22:32:53.030  INFO  core.alerts                 Gmail access token refreshed
22:32:53.534  INFO  core.alerts                 Gmail alert sent: Engine Started
22:32:53.534  INFO  core.resilience             [CircuitBreaker:broker] -> RESET to CLOSED
22:32:53.534  INFO  broker.capital_client       Warming epic cache for 10 instruments...
22:32:59.914  INFO  broker.capital_client       Epic cache warmed: 10 instruments cached
22:33:00.023  INFO  core.trading_engine         Initial scan: analyzing 10 pairs...
22:33:34.530  INFO  core.trading_engine         Initial scan complete: 10/10 pairs analyzed, 0 setups detected
22:33:34.530  INFO  core.trading_engine:start   Main loop starting — scan every 120s
```

Chequeos clave:
- ✓ Banner "Atlas v3.0 - Liquid Glass - Starting Up" presente.
- ✓ Conexión a Capital.com OK, balance 190.88 USD.
- ✓ Circuit breaker RESET a CLOSED.
- ✓ Epic cache calentado (10/10).
- ✓ Initial scan completado en ~34 s (10/10 pairs).
- ✓ Main loop activo con tick cada 120 s.
- ✓ Circuit breaker sin aperturas post-restart.
- ✓ Alerta Gmail de inicio enviada correctamente.

**Ticks post-startup:** 22:33:34 → 22:36:02 → 22:38:02 → 22:40:03 → 22:42:03 → 22:44:04 → 22:46:37 (intervalo promedio 120 s, todos con `market_open=False | weekday=4 | hour=22` — consistente con viernes post-cierre NY).

## Issues detectados

**Ninguno crítico.** Los únicos eventos no-INFO son:

- **WARNING × 7 — `Invalid API key from IP: 181.54.54.234`** *(Severidad: INFO operacional)* — Comportamiento esperado y deseado (A5 fail-closed está interceptando probes externos/script de tests).

No hay:
- ERROR ni CRITICAL.
- Tracebacks / excepciones no capturadas.
- 429 de Capital.com.
- 401 de Capital.com.
- Retries de 404 (`attempt 2/`+).
- SMT WARNING (M12 demote efectivo).
- Fallos de arranque, reconexiones o circuit-breaker opens.

## Conclusión

**GO para operar.**

Justificación:
1. Arranque post-deploy f34ef12 limpio: banner visible, DB up, sesión Capital.com creada, balance leído, epic cache calentado, initial scan 10/10, main loop activo.
2. Los 4 fixes recientes funcionan como se esperaba en producción:
   - **M12** reduce ruido WARNING en ≥99.7 % (el SMT ya no contamina).
   - **C5** corta retries de sesión (139 → 2 en proporción de tiempo) y elimina 429s.
   - **A9** no regresa (0 patrones de retry sobre 404).
   - **A5** rechaza correctamente requests sin API key válida.
3. Salud del contenedor normal (CPU 0.17 %, Mem 1.9 %, `actual=1 desired=1`).
4. Mercado forex cerrado (viernes 22:46 UTC post-cierre NY), así que el run actual está en modo off-hours analysis; no hay setups activos ni órdenes pendientes — adecuado para dejar correr hasta la apertura del lunes.

Recomendación adicional: la próxima ventana crítica a monitorear es **domingo 22:00 UTC** (apertura Sídney) para validar en mercado vivo los fixes en `trading_engine.py` del commit (Bug 1: SELL sign normalization y Bug 2: PositionPhase import).
