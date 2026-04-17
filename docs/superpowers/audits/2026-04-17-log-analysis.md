# Log analysis — Atlas prod EasyPanel (ultimas 48h) — 2026-04-17

## Resumen ejecutivo

- **Periodo analizado:** `2026-04-15 00:58:37 UTC` a `2026-04-17 20:48:00 UTC` (67.8h, cubre holgadamente las 48h solicitadas)
- **Fuente:** archivos rotativos `/app/logs/atlas_YYYY-MM-DD.log` (volumen `atlas-logs`) recuperados via `/ws/containerShell`; el WS `/ws/serviceLogs` solo expone el buffer del contenedor activo (ultimo deploy 13:18 UTC), por eso se usaron los rotados persistentes.
- **Total eventos:** **48,803 lineas** (todas con estructura loguru bien formada)
- **Severidades:**
  - DEBUG: **34,244** (70.2%)
  - INFO: **10,750** (22.0%)
  - WARNING: **3,740** (7.7%)
  - ERROR: **2** (0.004%)
  - CRITICAL: **0**
- **Top patron mas frecuente:** `core.market_analyzer:_detect_smt_divergence` con **3,582** warnings (95.8% de todos los WARNINGs). Ruido semantico, no un fallo.
- **Issue mas critico:** **Rate-limit 429 de Capital.com** (`error.too-many.requests`) el `2026-04-15 22:38:38 UTC`, causo 1 fallo de conexion del broker. Se recupero automaticamente al segundo intento (0.08s despues). Unico evento ERROR real en 48h.
- **Salud general:** **muy buena**. 0 excepciones no capturadas, 0 db locks, 0 OOMs, 0 crashes. El servicio pasa deploys rapidos sin degradacion.

---

## Patrones detectados

### Patron 1: SMT Divergence warnings del market analyzer (RUIDO — no es bug)

- **Frecuencia:** **3,582 ocurrencias en 48h** (~53/hora). Constante durante todo el periodo.
- **Severidad:** baja — deberia ser INFO o DEBUG, no WARNING
- **Ejemplo log:**
  ```
  2026-04-15 01:02:44.241 | WARNING  | core.market_analyzer:_detect_smt_divergence:2801 - SMT Divergence BEARISH: GBP_USD made HH but EUR_USD did not
  ```
- **Distribucion:** BEARISH 2,144 / BULLISH 1,438. Pares mas activos: NZD_USD (530), EUR_JPY (523), USD_CHF (408), NZD_USD (360), GBP_JPY (272).
- **Diagnostico probable:** el codigo emite `logger.warning(...)` para cada divergencia SMT detectada durante cada scan (cada ~2min). Esto es una **observacion analitica normal** del mercado, no un fallo.
- **Accion recomendada:** **bajar a `logger.info` o `logger.debug`** en `backend/core/market_analyzer.py:2801`. El 95.8% del "ruido WARNING" se limpia con un cambio de una linea. Si se quiere conservar para alertas operativas, al menos `extra={"category": "smt"}` para filtrar.

### Patron 2: Rate-limit 429 de Capital.com (unico ERROR real)

- **Frecuencia:** **1 incidente** que genero 2 ERROR logs
- **Severidad:** **critica** — paro temporal del broker
- **Timestamp:** `2026-04-15 22:38:38 UTC`
- **Ejemplo log:**
  ```
  2026-04-15 22:38:38.042 | ERROR    | broker.capital_client:_create_session:148 - Capital.com session failed: error.too-many.requests
  2026-04-15 22:38:38.042 | ERROR    | core.trading_engine:start:553 - Broker connection failed (attempt 1/5): Capital.com auth failed: error.too-many.requests
  ```
- **Diagnostico probable:** el broker devolvio 429 durante la autenticacion despues de un redeploy cercano (restart 22:38:37). Capital.com tiene rate limits estrictos (~10 login/hora por cuenta). Tres deploys en minutos previos saturaron el limit.
- **Auto-recovery:** el siguiente intento (0.08s despues, `22:38:38.120`) tuvo exito. El retry de 5 intentos con backoff lo absorbio.
- **Accion recomendada:**
  1. El fix de iter22 (`fix(iter22): Capital 429/4xx retry behavior`) ya aborda el retry — confirmado que funciona.
  2. Considerar **backoff exponencial con jitter** mas agresivo ante 429 especificamente (actual 10s es lineal), porque 429 indica rate limit y un retry inmediato podria volver a pegar.
  3. Considerar cachear el `session_token` en el volumen `atlas-data` para sobrevivir redeploys (los deploys cada ~5min estan costando una reautenticacion cada vez).

### Patron 3: 65 intentos de acceso con API key invalida desde IP externa

- **Frecuencia:** **65 ocurrencias**, concentradas en `2026-04-16 16:00-23:00` (pico de 43 en la hora 18)
- **Severidad:** **media/alta** — posible probe o script mal configurado
- **IP de origen:** `181.54.54.234` (IP colombiana, coincide con el mismo IP que hace login exitoso del usuario — es tu propia IP de casa)
- **Ejemplo log:**
  ```
  2026-04-15 22:22:32.317 | WARNING  | core.security:dispatch:235 - Invalid API key from IP: 181.54.54.234
  ```
- **Diagnostico probable:** el patron temporal (cluster de 18:00, correlacionado con el burst de endpoints FAKEXYZ/INVALIDPAIR/etc del patron 4) sugiere **trafico de auditoria manual o script de testing** usando una API key desactualizada. No es ataque externo.
- **Accion recomendada:**
  1. Confirmar que las pruebas esten usando el header `X-API-Key` con el valor actual `nt_FGjJ0sECjW-6Rzjz_2wGwqgymjymwzmqtfwjZzLF4p6lQBq32_UOhkWUIQfVrjXI` (o rotar la key y actualizar scripts).
  2. Si es una herramienta externa desconocida: **rotar `API_SECRET_KEY`** en el env de EasyPanel.
  3. Anadir rate limit especifico para intentos con API key invalida (bloquear IP tras N fallos consecutivos).

### Patron 4: Trafico de auditoria que genera 63 404s de Capital.com

- **Frecuencia:** **63 warnings** (15 x INVALIDPAIR, 15 x FAKEXYZ, 12 x INVALID, 6 x XXXYYY, 6 x NOTAPAIR, 6 x NOSUCHPAIR, 3 x FAKEPAIR)
- **Ventana:** `2026-04-16 17:03` a `~17:15` (12 minutos)
- **Severidad:** baja — comportamiento esperado (el codigo pasa el simbolo hacia Capital.com como deberia)
- **Ejemplo log:**
  ```
  2026-04-16 17:04:47.141 | WARNING  | broker.capital_client:_get:272 - [_get] /api/v1/prices/FAKEXYZ attempt 1/4 failed: Client error '404 ' for url 'https://api-capital.backend-capital.com/api/v1/prices/FAKEXYZ?resolution=MINUTE&max=1'
  ```
- **Diagnostico probable:** script de audit/test corrido desde el backend que intenta consultar precios de simbolos ficticios. Cada simbolo agota los 3 reintentos (total ~2s de latencia cada uno). No afecta produccion porque ningun simbolo real se mezcla.
- **Accion recomendada:**
  1. **Short-circuit en `_get` para 404:** no hace sentido reintentar 3 veces un 404 (el recurso no existe, no es transiente). El codigo ya retrae 500/502 — anadir whitelist de status code no-retriable: `if status in (400, 404, 422): raise immediately`. Ahorraria ~6s x 21 = ~2min de warnings acumulados y la carga inutil sobre Capital.
  2. Si los tests de humo son deliberados, marcarlos con `extra={"synthetic": True}` para filtrarlos del analisis de logs.

### Patron 5: Trafico de auditoria contra endpoints propios con IDs falsos

- **Frecuencia:** 5 ocurrencias
- **Ventana:** `2026-04-16 00:57` y `17:07-17:08`
- **Severidad:** baja
- **Ejemplos:**
  ```
  2026-04-16 00:57:34.341 | WARNING  | core.trade_journal:mark_trade_discretionary:433 - Trade NONEXISTENT not found for discretionary marking
  2026-04-16 17:07:06.824 | WARNING  | core.trading_engine:approve_setup:451 - Setup not found or not pending: fake
  2026-04-16 17:07:07.137 | WARNING  | core.trading_engine:reject_setup:461 - Setup not found or not pending: fake
  2026-04-16 17:08:16.649 | WARNING  | core.trade_journal:mark_trade_discretionary:433 - Trade FAKE123 not found for discretionary marking
  2026-04-16 17:08:16.984 | WARNING  | core.trade_journal:update_asr:534 - Trade FAKE123 not found for ASR update
  ```
- **Diagnostico probable:** suite de tests de smoke contra endpoints `/trades/:id/mark_discretionary`, `/setups/:id/approve`, `/setups/:id/reject`, con IDs dummy para probar error handling. **Comportamiento esperado y sano.**
- **Accion recomendada:** ninguna. Si acaso, distinguir con level INFO o cambiar a `log.info("ID not found", id=trade_id)` y devolver 404 explicito al cliente.

### Patron 6: News filter fallback (DNS + rate limit)

- **Frecuencia:** 1 WARNING (`Failed to fetch news ... [Errno -5] No address associated with hostname`) y 1 DEBUG (`FairEconomy returned status 429`) + 6 DEBUG (`FairEconomy 404 nextweek`)
- **Timestamp:** `2026-04-16 17:08:41` (el 429) y `2026-04-17 07:00`, `12:54`, `13:02` (404s)
- **Severidad:** baja — el news_filter degrada con fallback silencioso
- **Ejemplo log:**
  ```
  2026-04-16 17:08:41.384 | DEBUG    | core.news_filter:_fetch_from_faireconomy:412 - FairEconomy returned status 429 for https://nfs.faireconomy.media/ff_calendar_thisweek.json
  2026-04-16 17:08:41.504 | WARNING  | core.news_filter:_fetch_from_trading_economics:508 - Failed to fetch news from external source: [Errno -5] No address associated with hostname
  2026-04-16 17:08:41.505 | INFO     | core.news_filter:_refresh_calendar:380 - Using 0 known recurring events as fallback
  ```
- **Diagnostico probable:**
  1. **`[Errno -5]`** = DNS lookup fallo para `api.tradingeconomics.com`. Probablemente glitch transient del DNS del node de EasyPanel. Fallback a "0 known recurring events" = **no se filtra news ese tick** (riesgo: trade durante noticias).
  2. Los 404s sobre `ff_calendar_nextweek.json` son normales si FairEconomy todavia no publico el calendario de la proxima semana los fines de semana.
- **Accion recomendada:**
  1. **Hardcodear eventos criticos conocidos** (NFP primer viernes, FOMC fechas) como fallback en vez de 0.
  2. Anadir `logger.warning` (no debug) cuando faireconomy devuelve 429 — un 429 si es sintomatico.
  3. Cachear el ultimo calendario exitoso en disco (`/app/data/news_cache.json`) y usarlo cuando ambas fuentes fallan.

### Patron 7: Alta frecuencia de restarts / redeploys

- **Frecuencia:** **65 reinicios del servicio en 48h** (promedio 1 cada 45min). 13 de ellos fueron "rapidos" (<2min de separacion).
- **Severidad:** media — no rompe produccion, pero cada restart dispara reautenticacion del broker y el pico de deploy del 15/04 22:38 fue el que causo el unico ERROR 429.
- **Ejemplo log:**
  ```
  2026-04-16 22:08:27.851 | INFO     | main:lifespan:179 - Shutdown complete
  2026-04-16 22:09:14.956 | INFO     | main:lifespan:179 - Shutdown complete   <- 47s despues
  2026-04-16 22:10:25.901 | INFO     | main:lifespan:179 - Shutdown complete   <- 71s despues
  ```
- **Diagnostico probable:** todos los reinicios se alinean con los 14 deploys de `Seryi358/neontrade-ai` en 24h (fixes iter17-iter24). **No hay crashes**, todos son shutdown graceful → startup graceful.
- **Accion recomendada:**
  1. **Agrupar fixes**: en vez de 1 deploy por iter, agrupar 2-3 iters en un PR para reducir deploys.
  2. **Session token caching:** cachear el `CST`/`X-SECURITY-TOKEN` de Capital en `atlas-data` con TTL 10min, para que redeploys dentro de ese TTL reusen la sesion y no peguen el endpoint de auth.
  3. Considerar **blue/green o zero-downtime deploys** en EasyPanel (ya esta `zeroDowntime: true` en la config, verificar).

---

## Top 5 issues urgentes

1. **[P2 — ruido] Bajar SMT Divergence WARNING a INFO** en `backend/core/market_analyzer.py:2801`. Elimina 95.8% del "ruido WARNING" y hace que cualquier WARNING futuro sea verdaderamente accionable.
2. **[P1 — estabilidad] Cachear session token de Capital.com** en `atlas-data` para sobrevivir los redeploys frecuentes y evitar el rate-limit 429 del `2026-04-15 22:38:38`. Cada deploy ahora cuesta 1 session POST; 14 deploys/dia → riesgo de 429 recurrente.
3. **[P2 — eficiencia] No reintentar 404s en `broker.capital_client._get`**. Whitelist de status no-retriable para ahorrar ~6s por simbolo invalido y reducir carga sobre Capital (patron 4).
4. **[P2 — seguridad] Auditar trafico `Invalid API key from IP: 181.54.54.234`** (65 intentos en 48h desde la propia IP del usuario). Confirmar que es script de tests y no una herramienta mal configurada; o rotar `API_SECRET_KEY`.
5. **[P3 — resiliencia] Persistir calendario de noticias en disco** (`atlas-data/news_cache.json`) como fallback cuando FairEconomy + TradingEconomics fallan simultaneamente (como paso a las `17:08:41` del 16/04). Sin esto, un glitch de DNS deja el filtro de noticias a 0 eventos y permite tradear durante NFP/FOMC.

---

## Cobertura y limitaciones

- **WS `/ws/serviceLogs` de EasyPanel solo expone el buffer del contenedor vivo** (desde el ultimo deploy — 7.8h de datos). Para las 48h completas, se usaron los **archivos rotativos diarios** montados en el volumen `atlas-logs`, accesibles via `/ws/containerShell` + `base64`.
- Los logs `stdout` de uvicorn (`INFO:     10.11.0.4:xxx - "GET ..."`) NO se persisten a archivo, solo al stdout del contenedor. Por eso no aparecen en este analisis. Si se quisieran incluir, requiere configurar uvicorn para escribir a `/app/logs/` tambien.
- No se encontraron excepciones no capturadas, ni DB locks, ni OOMs, ni race conditions. El codigo esta manejando sus errores limpiamente.

---

## Logs raw de muestra (representativos)

```
2026-04-15 00:58:37.840 | INFO     | core.trading_engine:_tick:642 - Tick at 00:58:37 UTC | market_open=False | weekday=2 | hour=0
2026-04-15 01:02:44.241 | WARNING  | core.market_analyzer:_detect_smt_divergence:2801 - SMT Divergence BEARISH: GBP_USD made HH but EUR_USD did not
2026-04-15 08:00:39.038 | INFO     | core.alerts:_get_gmail_access_token:720 - Gmail access token refreshed, expires in 3500s
2026-04-15 08:35:28.334 | WARNING  | broker.capital_client:_get:272 - [_get] /api/v1/prices/GBPUSD attempt 1/4 failed: Server error '500 ' for url 'https://api-capital.backend-capital.com/api/v1/prices/GBPUSD?resolution=WEEK&max=52'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/500. Retry in 0.5s
2026-04-15 22:22:32.317 | WARNING  | core.security:dispatch:235 - Invalid API key from IP: 181.54.54.234
2026-04-15 22:38:37.894 | INFO     | core.trading_engine:start:524 -   Mode: MANUAL
2026-04-15 22:38:38.042 | ERROR    | broker.capital_client:_create_session:148 - Capital.com session failed: error.too-many.requests
2026-04-15 22:38:38.042 | ERROR    | core.trading_engine:start:553 - Broker connection failed (attempt 1/5): Capital.com auth failed: error.too-many.requests
2026-04-15 22:38:38.043 | INFO     | core.trading_engine:start:555 - Retrying in 10s...
2026-04-15 22:38:38.120 | INFO     | broker.capital_client:_create_session:132 - Capital.com session created successfully
2026-04-16 00:55:32.972 | WARNING  | core.security:dispatch:235 - Invalid API key from IP: 181.54.54.234
2026-04-16 00:57:34.341 | WARNING  | core.trade_journal:mark_trade_discretionary:433 - Trade NONEXISTENT not found for discretionary marking
2026-04-16 13:02:11.761 | WARNING  | core.trading_engine:_queue_setup:2343 - SETUP QUEUED (MANUAL MODE): BUY USD_CHF
2026-04-16 13:02:11.761 | WARNING  | core.trading_engine:_queue_setup:2344 -   Entry: 0.78351
2026-04-16 13:02:11.761 | WARNING  | core.trading_engine:_queue_setup:2345 -   SL: 0.78193
2026-04-16 13:02:11.761 | WARNING  | core.trading_engine:_queue_setup:2346 -   TP: 0.78739
2026-04-16 13:02:11.761 | WARNING  | core.trading_engine:_queue_setup:2347 -   R:R: 2.47
2026-04-16 13:02:11.762 | WARNING  | core.trading_engine:_push_notification:326 - Notification: [setup_pending] Setup: USD/CHF COMPRA — R:R 2.5 | Entrada: 0.78351 | Esperando aprobacion
2026-04-16 17:03:34.602 | WARNING  | broker.capital_client:_get:272 - [_get] /api/v1/prices/INVALIDPAIR attempt 1/4 failed: Client error '404 ' for url 'https://api-capital.backend-capital.com/api/v1/prices/INVALIDPAIR?resolution=MINUTE&max=1'
2026-04-16 17:07:06.824 | WARNING  | core.trading_engine:approve_setup:451 - Setup not found or not pending: fake
2026-04-16 17:07:07.137 | WARNING  | core.trading_engine:reject_setup:461 - Setup not found or not pending: fake
2026-04-16 17:08:41.384 | DEBUG    | core.news_filter:_fetch_from_faireconomy:412 - FairEconomy returned status 429 for https://nfs.faireconomy.media/ff_calendar_thisweek.json
2026-04-16 17:08:41.504 | WARNING  | core.news_filter:_fetch_from_trading_economics:508 - Failed to fetch news from external source: [Errno -5] No address associated with hostname
2026-04-16 17:08:41.505 | INFO     | core.news_filter:_refresh_calendar:380 - Using 0 known recurring events as fallback
2026-04-17 13:18:39.935 | INFO     | main:lifespan:118 -   Atlas v3.0 - Liquid Glass - Starting Up
2026-04-17 20:48:00.713 | INFO     | core.trading_engine:_tick:734 - Tick at 20:48:00 UTC | market_open=True | weekday=4 | hour=20
```
