# Static bug hunt + pytest report — Atlas backend — 2026-04-17

## Resumen ejecutivo

- **Tests pasados:** 1285 / 1287 collected (0 fallidos, 0 errores, 2 xfailed esperados)
- **Cobertura total:** 69% (31,143 statements / 9,783 uncovered)
- **Bugs estáticos detectados:** 11 (críticos: 0, altos: 2, medios: 5, bajos: 4)
- **Entorno:** Python 3.14, pytest 9.x, asyncio_mode=auto
- **Duración pytest:** 72.84s (full suite), 113.01s (con cobertura)

### Top 5 issues más urgentes

1. **Security "open-access" default (alto)** — `core/security.py:115` — cuando no hay API keys configuradas, `validate_key` devuelve `True` para todo: toda request sin key pasa auth. Solo un `logger.error` lo anuncia. En un despliegue recién levantado sin haber generado una key, el backend queda completamente abierto.
2. **Low coverage on critical module (alto)** — `core/trading_engine.py` 25% cobertura (1190 líneas sin ejercitar). Gran parte del engine runtime (scans, hooks, news close, Friday close) no está cubierta por pytest; los tests se enfocan en helpers estáticos. Cualquier regresión pasa silenciosa.
3. **WebSocket connection-limit TOCTOU race (medio)** — `main.py:67-76` — el check `len(active_connections) >= MAX_WS_CONNECTIONS` seguido de `.append()` no es atómico. Dos `connect()` concurrentes pueden superar el cap. El comentario afirma atomicidad pero no hay `asyncio.Lock`.
4. **`datetime.now()` sin timezone (medio)** — `api/routes.py:1080` — `get_engine_logs` usa `datetime.now()` sin `timezone.utc`; si el host no está en UTC, el nombre de archivo `atlas_YYYY-MM-DD.log` no coincide con el que `loguru` genera en UTC, causando logs vacíos.
5. **`async def` sin `await` haciendo I/O bloqueante (medio)** — `core/screenshot_generator.py:78` y `:166` — `capture_trade_open/close` son `async` pero llaman `matplotlib` de forma síncrona (`_generate_candlestick_chart`, `plt.savefig`). Ejecutar varias al mismo tiempo bloquea el event loop del trading engine durante cada render.

---

## Tests

### Resultado final

```
=========== 1285 passed, 2 xfailed, 94 warnings in 72.84s ============
```

**No hay tests fallidos ni con error.** Los dos XFAIL están marcados por el equipo: `test_round6_stress.py::test_23_oanda_urls` y `test_36_get_oanda_url_invalid_env` son integración OANDA retirada.

5 archivos legacy son excluidos por `conftest.py::collect_ignore` (test_final_integration, test_round4_comprehensive, test_round10_ultimate, test_broker_connection, test_live_*). Siguen siendo ejecutables vía `python3 <file>` pero no por pytest, porque llaman `sys.exit()` a nivel de módulo.

### Warnings notables

- `PydanticDeprecatedSince211`: 90 warnings en `test_strategies_pytest.py:21` por acceder `model_computed_fields` y `model_fields` desde instancia. Romperá en Pydantic V3.
- `RuntimeWarning: coroutine 'AsyncMockMixin._execute_mock_call' was never awaited` en `test_bugfix005_api_ws_notifications.py::TestEngineControl::test_stop_engine` — mock mal configurado. Esconde una posible regresión de flujo async.
- `RuntimeWarning: Degrees of freedom <= 0 for slice` y `invalid value encountered in scalar divide` en `test_backtester_coverage.py::TestComputeMetrics::test_basic_metrics` — la función de métricas no valida inputs vacíos/unitarios.

---

## Cobertura

### Total: 69% (31,143 stmt; 9,783 missed)

### Archivos producción <50% cobertura

| Archivo | Cob. | Notas críticas |
|---|---|---|
| `broker/ibkr_client.py` | 0% | 444/444 líneas sin cubrir. Sin tests unitarios — solo `test_broker_connection.py` (live, excluido). DH/HMAC crypto, OAuth, order placement, close — todo inexplorado. |
| `db/migrations/fix_status_constraint.py` | 0% | Migración ya aplicada en prod; es legacy one-off. Bajo riesgo. |
| `setup_gmail.py` | 0% | Script standalone de setup OAuth. Ejecutado manualmente. Bajo riesgo. |
| `broker/capital_client.py` | 9% | 571/629 sin cubrir. Toda la lógica del broker principal de producción (auth, order, close, positions, resilience) solo probada por tests live. Un cambio en headers/formato puede romper en silencio. |
| `ai/openai_analyzer.py` | 14% | Prompt building y parsing de respuestas sin cubrir. 100% LLM output unparseable rompe silenciosamente (ya hay `try/except` genéricos). |
| `eco_calendar/economic_calendar.py` | 19% | Fetch externo; falla silente con logger.warning. |
| `core/trading_engine.py` | 25% | Orquestador principal. 1190/1593 líneas sin ejercitar. Incluye scans, WS broadcasts, news close, Friday close, funded account phase advance, emergency close, trade execution. |
| `main.py` | 27% | Lifespan, WebSocket handler, broadcast loop, command handler. |
| `core/scalping_engine.py` | 27% | Full scalping flow sin cubrir (solo 27%). |
| `strategies/base.py` | 51% | 1318/2695 sin cubrir. Variantes de estrategias, condiciones específicas de direction/timeframe/SMT. |

### Archivos de módulos críticos (risk/broker/position) a mejorar

| Archivo | Cob. | Gaps clave |
|---|---|---|
| `core/risk_manager.py` | 81% | 127-148 (instance attrs init branches), 188-207 (funded_preset early exit), 600-633 (position-size margin reduce), 872-897 (funded phase advance). |
| `core/position_manager.py` | 85% | 307-310 (first-time init guard), 856-874 (trailing EMA no-data fallback), 1071-1092 (SL move broker rejection path). |
| `core/news_filter.py` | 55% | 362-516 (cached external source fetch), 583-611 (events diff). Crítico porque afecta close-on-news. |

---

## Bugs estáticos

### Bug 1: "open-access" mode cuando no hay API keys configuradas (alto)

- **Archivo:línea:** `backend/core/security.py:108-115`
- **Tipo:** security default / fail-open
- **Código:**
  ```python
  def validate_key(self, raw_key: str) -> bool:
      if not self.auth_enabled:
          return True
      if not self.api_keys:
          logger.error(
              "!!! SECURITY WARNING !!! No API keys configured — ALL requests are allowed. ..."
          )
          return True  # No keys configured = open access (first run)
  ```
- **Hipótesis:** En un despliegue nuevo (sin `data/security.json` poblado) todo el backend queda sin auth. El único aviso es `logger.error`, que puede pasar desapercibido si nadie mira logs. Ya hay marker "BUG-09 fix" que intentó mitigar — pero sigue siendo fail-open.
- **Test sugerido:** verificar que un POST a `/api/v1/security/generate-key` sin keys configuradas debería al menos requerir un "bootstrap token" o devolver 401 hasta que se cree la primera key.
- **Prioridad:** alta

### Bug 2: WebSocket connection-limit TOCTOU race (medio)

- **Archivo:línea:** `backend/main.py:67-76`
- **Tipo:** race condition
- **Código:**
  ```python
  async def connect(self, websocket: WebSocket) -> bool:
      if len(self.active_connections) >= MAX_WS_CONNECTIONS:
          await websocket.close(code=4003, reason="Connection limit reached")
          ...
          return False
      await websocket.accept()
      self.active_connections.append(websocket)   # non-atomic with check
  ```
- **Hipótesis:** Aunque el comentario en `websocket_endpoint` dice "atomic check-and-accept", el check y el append no están dentro de un lock. Dos handshakes simultáneos pueden pasar ambos el check (len=N-1 < MAX) y acabar con N+1 conexiones. Bajo carga alta (o en tests con `asyncio.gather`) el cap de `MAX_WS_CONNECTIONS` se puede superar.
- **Test sugerido:** lanzar `MAX_WS_CONNECTIONS + 5` conexiones concurrentes con `asyncio.gather` y verificar que exactamente `MAX_WS_CONNECTIONS` quedan activas.
- **Prioridad:** media

### Bug 3: `datetime.now()` sin timezone en get_engine_logs (medio)

- **Archivo:línea:** `backend/api/routes.py:1080`
- **Tipo:** timezone mismatch
- **Código:**
  ```python
  today = datetime.now().strftime("%Y-%m-%d")
  log_dirs = ["logs", "/app/logs"]
  ...
  candidates = [os.path.join(log_dir, f"atlas_{today}.log"), ...]
  ```
- **Hipótesis:** Loguru escribe log files con timestamp UTC, pero aquí se usa la fecha local del host (sin `timezone.utc`). Si el contenedor corre en una TZ distinta (o si está cerca de medianoche UTC), el filename no coincide — el fallback busca cualquier `.log` pero puede elegir uno equivocado. Es el único `datetime.now()` sin TZ en backend de producción.
- **Test sugerido:** con TZ=America/Bogota (UTC-5), a las 20:00 local (01:00 UTC siguiente) verificar que `today` coincide con el filename de loguru.
- **Prioridad:** media

### Bug 4: `async def` sin `await` hace I/O síncrono bloqueante (medio)

- **Archivo:línea:** `backend/core/screenshot_generator.py:78, 166`
- **Tipo:** false async / blocking I/O in event loop
- **Código:**
  ```python
  async def capture_trade_open(self, ...) -> str:
      ...
      if candles and len(candles) > 0:
          self._generate_candlestick_chart(filepath, candles, levels, trade_info, ema_values)
      else:
          self._generate_info_card(filepath, trade_info)
      ...
  ```
- **Hipótesis:** `_generate_candlestick_chart` llama `matplotlib`/`mplfinance` y `plt.savefig` de forma síncrona, bloqueando el event loop entre 200-500 ms por screenshot. Si se abren varios trades seguidos, el WebSocket heartbeat y el `_status_broadcast_loop` se bloquean. Solución: `await asyncio.get_event_loop().run_in_executor(None, self._generate_candlestick_chart, ...)`.
- **Test sugerido:** spawn 5 `capture_trade_open()` en paralelo y medir que el event loop siga procesando un heartbeat cada 30s sin drift >1s.
- **Prioridad:** media

### Bug 5: `async def` sin `await` en position_manager._handle_be_phase (medio)

- **Archivo:línea:** `backend/core/position_manager.py:656`
- **Tipo:** async innecesario (penalización mínima) o señal de gap lógico
- **Código:**
  ```python
  async def _handle_be_phase(self, pos: ManagedPosition, current_price: float):
      """Phase 3: After BE, transition to EMA trailing."""
      base_key = self._get_base_ema_key(pos.instrument)
      if base_key is None:
          pos.phase = PositionPhase.TRAILING_TO_TP1
          ...
          return
      ema_value = self._get_trail_ema(pos.instrument, base_key)
      ...
  ```
- **Hipótesis:** Ninguna operación async dentro. Caller hace `await self._handle_be_phase(...)` por lo que el coste es menor (context switch), pero sugiere que probablemente falta una consulta broker para obtener EMA actualizado — actualmente usa caché. Si el caché está stale la transición a TRAILING se toma sobre un EMA obsoleto.
- **Test sugerido:** confirmar que cada actualización de posición refresca `_get_trail_ema` con el candle más reciente del ciclo.
- **Prioridad:** media

### Bug 6: Duplicate `if not instrument: return False` en _is_crypto_instrument (bajo)

- **Archivo:línea:** `backend/strategies/base.py:1094, 1100`
- **Tipo:** redundant check / dead code
- **Código:**
  ```python
  def _is_crypto_instrument(instrument: str) -> bool:
      if not instrument:
          return False
      global _crypto_watchlist_cache
      if not _crypto_watchlist_cache:
          ...
      if not instrument:
          return False  # ← duplicate, unreachable
      inst_upper = instrument.upper()
  ```
- **Hipótesis:** Seguramente quedó de un refactor previo. No causa bug, pero confunde al lector y ensucia coverage.
- **Test sugerido:** N/A.
- **Prioridad:** baja

### Bug 7: `_crypto_watchlist_cache` global sin invalidación (bajo)

- **Archivo:línea:** `backend/strategies/base.py:1085-1099`
- **Tipo:** stale cache
- **Código:**
  ```python
  _crypto_watchlist_cache: set = set()

  def _is_crypto_instrument(instrument: str) -> bool:
      ...
      global _crypto_watchlist_cache
      if not _crypto_watchlist_cache:
          from config import settings
          _crypto_watchlist_cache = {s.upper() for s in settings.crypto_watchlist}
  ```
- **Hipótesis:** Si el usuario modifica `crypto_watchlist` vía API (`PUT /api/v1/risk-config` o `POST /api/v1/watchlist/categories`) la caché no se invalida. Un instrumento recién agregado al watchlist crypto no será reconocido como crypto hasta un restart del proceso. No es crítico porque los instrumentos son estables pero puede sorprender.
- **Test sugerido:** mutar `settings.crypto_watchlist` en runtime y verificar que `_is_crypto_instrument` refleja el cambio.
- **Prioridad:** baja

### Bug 8: `except Exception` masking después de catch específico en websocket auth (bajo)

- **Archivo:línea:** `backend/main.py:283`
- **Tipo:** redundant exception types
- **Código:**
  ```python
  except (asyncio.TimeoutError, json.JSONDecodeError, Exception):
      pass
  ```
- **Hipótesis:** `Exception` ya cubre los otros dos tipos. Peor, se traga TODO (incluyendo `RuntimeError`, `AttributeError`) silenciosamente. Auth failure por bug en `receive_text()` quedaría enmascarada y `api_key` quedaría en `""`, luego `validate_key("")` devuelve `False` → el cliente ve "Invalid API key" pero la causa real es opaca.
- **Test sugerido:** simular una excepción inesperada en `json.loads` y verificar que se loguea.
- **Prioridad:** baja

### Bug 9: Coroutine no awaited en test — señal de async mock mal configurado (medio)

- **Archivo:línea:** `backend/test_bugfix005_api_ws_notifications.py::TestEngineControl::test_stop_engine`
- **Tipo:** test warning / falso positivo potencial
- **Código:** (detectado vía warning)
  ```
  RuntimeWarning: coroutine 'AsyncMockMixin._execute_mock_call' was never awaited
  ```
- **Hipótesis:** Un AsyncMock se está usando sin await. El test pasa, pero la assertion sobre side-effect del mock puede no estar ejecutándose. Esto oculta potencial regresión de `stop_engine`.
- **Test sugerido:** revisar el test y confirmar que todas las llamadas a mocks `AsyncMock` van precedidas de `await`.
- **Prioridad:** media

### Bug 10: `_calc_sharpe` / `_calc_sortino` explotan con <=1 trade (bajo)

- **Archivo:línea:** `backend/core/backtester.py:1255-1296`
- **Tipo:** input validation missing
- **Código:**
  ```python
  # _calc_sharpe
  returns = [t.pnl for t in trades]
  ...
  std_ret = np.std(returns, ddof=1)  # ← RuntimeWarning si len(returns) < 2
  ```
- **Hipótesis:** El test `test_basic_metrics` emite dos RuntimeWarnings (`Degrees of freedom <= 0`, `invalid value in scalar divide`) porque el helper no valida `len(trades) >= 2` antes de `np.std(..., ddof=1)`. Devuelve `nan`; el consumer puede serializar `nan` a JSON inválido.
- **Test sugerido:** `_calc_sharpe([])` debe devolver `0.0` sin warnings; `_calc_sharpe([single_trade])` igual.
- **Prioridad:** baja

### Bug 11: Inconsistencia entre `trade_id` y `pos.trade_id` en mensaje de log (bajo)

- **Archivo:línea:** `backend/core/trading_engine.py:1708`
- **Tipo:** log inconsistency
- **Código:**
  ```python
  for trade_id, pos in list(self.position_manager.positions.items()):
      ...
      except Exception as ae:
          logger.warning(f"Close alert failed for {trade_id}: {ae}")   # local var
  # vs. línea 1679:
  logger.warning(f"DB update failed for news close {pos.trade_id}: {db_err}")  # attribute
  ```
- **Hipótesis:** No es bug funcional (dict key == `ManagedPosition.trade_id` por construcción), pero inconsistencia de estilo. Si alguien alguna vez almacena la posición con key distinto al trade_id, los logs divergen.
- **Test sugerido:** N/A; style fix.
- **Prioridad:** baja

---

## Patrones revisados (sin hallazgos de riesgo)

| Patrón | Resultado |
|---|---|
| `except:` bare | 0 ocurrencias |
| `os.system`, `shell=True` | 0 ocurrencias |
| `eval()`, `exec()` | 0 ocurrencias |
| `pickle.load`, `yaml.load` unsafe | 0 ocurrencias |
| `verify=False` en httpx/requests | 0 ocurrencias |
| SQL injection (f-string con input) | 0 (único f-string en db/models.py tiene whitelist `allowed_columns`) |
| Secrets hardcoded | 0 en código prod (solo en fixtures/tests) |
| TODO/FIXME/XXX | 0 en código real ("HACK" es ticker ETF) |
| Mutable defaults (`def f(x=[])`) | 0 ocurrencias |
| `datetime.utcnow()` deprecado | 0 ocurrencias |
| `time.sleep()` en async | 0 en código prod (solo en tests) |
| `assert` en código producción | 0 ocurrencias |
| `async def` sin `await` | 13 en código real (mayoría son conformidad con interfaz abstracta; 2-3 casos reales de bloqueo — bugs 4 y 5) |
| `except Exception:` pass | 45 ocurrencias totales — mayormente legítimas (flujos de "best-effort" como alerts, WS, logging); bug 8 es el único concerning |

---

## Recomendaciones

1. **Seguridad:** cambiar comportamiento de `validate_key` con `not self.api_keys` a `return False` y documentar que se debe llamar `generate_api_key()` vía CLI antes del primer startup. Alternativa: generar una random key al primer startup y logearla solo una vez.
2. **Cobertura:** priorizar tests unitarios para `core/trading_engine.py` (scans + execute_trade + close_positions), `broker/capital_client.py` (al menos el happy path de auth, place_market_order, close_trade), y `broker/ibkr_client.py` (placeholder tests con httpx_mock).
3. **Async I/O:** envolver `matplotlib` llamadas en `run_in_executor` para no bloquear event loop.
4. **Timezone:** reemplazar `datetime.now()` por `datetime.now(timezone.utc)` en `routes.py:1080`.
5. **Warnings:** arreglar el AsyncMock no-awaited en `test_bugfix005_api_ws_notifications.py::test_stop_engine` — es la segunda señal de que el stop_engine test pasa por side-effect no-validado.
6. **Cleanup:** eliminar duplicate check y global cache invalidation hook en `strategies/base.py::_is_crypto_instrument`.
