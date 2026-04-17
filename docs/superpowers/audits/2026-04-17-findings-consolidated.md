# Findings consolidados — Atlas TradingLab audit — 2026-04-17

**Sources (4 subagentes Opus 4.7):**
- `2026-04-17-audit-mentoria.md` — comparación mentoría ↔ backend (commit `0f7ac7b` en worktree audit)
- `2026-04-17-log-analysis.md` — logs EasyPanel 48h (commit `3afd51e` en worktree logs)
- `2026-04-17-frontend-issues.md` + screenshots — Playwright sweep (commit `89b22e0` en worktree frontend)
- `2026-04-17-static-bugs.md` — pytest + cobertura + static review (commit `6e0da99` en worktree bugs)

---

## Resumen ejecutivo

| Métrica | Valor |
|---|---|
| Total findings únicos | ~38 (antes de consolidar overlaps) |
| Críticos | **5** (se atacan todos) |
| Altos | **11** (se atacan todos los relevantes) |
| Medios | **13** (se atacan los que están en scope del blindaje) |
| Bajos | **9** (documentados, NO se tocan — YAGNI) |
| Tests pytest pasan | **1285/1287** (0 fallos) |
| Cobertura actual | **69%** |
| Salud prod | **Excelente** (1 ERROR real en 48h, auto-recuperado) |

**Prioridades del usuario (recordatorio):** capital 190.88 USD, MANUAL mode, day_trading, sin scalping todavía, apalancamientos Capital.com activos (forex/índices/commodities 100:1, acciones/crypto 20:1, bonos/tasas 200:1).

**Decisiones intencionales NO revertidas** (caps de seguridad para cuenta pequeña):
- `risk_swing = 1%` (vs PDF 3%) — se mantiene pero se corrigen los comments que dicen "NON-NEGOTIABLE per mentorship" (es falso)
- `max_total_risk = 5%` (vs PDF 7%) — se mantiene pero se corrigen los comments

---

## CRÍTICOS (5) — se atacan todos

### C1. BLUE TP1 y TP_max invertidos
- **Fuente:** audit-mentoria §1
- **Archivos:** `backend/strategies/base.py:1844-1931` (`BlueStrategy.get_tp_levels`)
- **Mentoría dice (Trading Plan PDF pg.6):** TP1 = "máximo/mínimo anterior" (swing). TP_max = EMA 4H (BLUE B/C) o Fib 1.272/1.618 (BLUE A).
- **App hace:** `tp1 = EMA 4H 50` (línea 1864-1869). Inversión.
- **Impacto:** trades cierran demasiado lejos, pueden revertir antes de alcanzar TP.
- **Fix:** invertir asignación: `tp1 = swing anterior`, `tp_max = EMA 4H 50` o Fib.

### C2. Trailing post-BE usa EMA 50 en vez de EMA 2 + EMA 5
- **Fuente:** audit-mentoria §2
- **Archivos:** `backend/core/position_manager.py:95-118` (`_EMA_TIMEFRAME_GRID`), `backend/config.py:238-239`
- **Mentoría dice (PDF pg.5):** "dos medias móviles más cortas... **EMA2m y EMA5m** para el Day trading"
- **App hace:** `(CP, DAY_TRADING) → "EMA_M5_50"`. Las EMAs 2/5 existen en config pero solo se usan para emergency exit.
- **Impacto:** trailing demasiado amplio; no captura el criterio de gestión corto del PDF.
- **Fix:** crear mapa `(CP, DAY_TRADING) → "EMA_M5_5"` como trail principal, EMA_M5_2 como aggressive exit.

### C3. EMA 8 Weekly filter bloquea forex/indices (solo aplica a crypto)
- **Fuente:** audit-mentoria §3 + §10 + §11 (mismo root cause)
- **Archivos:** `backend/strategies/base.py:405-419` (`_check_weekly_ema8_filter`), usado en BLUE, RED, PINK, WHITE, BLACK, GREEN para TODOS los instrumentos
- **Mentoría dice:** EMA 8 semanal solo en `Esp. Criptomonedas/01_Contenido/08_Indicadores cripto`. No en Trading Mastery.
- **App hace:** filter aplicado globalmente. Hace BLACK (contratendencial) inoperable, bloquea setups forex válidos, hard-blocks GREEN forex.
- **Impacto:** setups forex perdidos, BLACK nunca dispara.
- **Fix:** gate con `if _is_crypto_instrument(analysis.instrument)` antes de aplicar. Para forex usar EMA 50 D (ya disponible).

### C4. Chips de filtro de color en Log renderizan como píldoras verticales gigantes
- **Fuente:** frontend-verifier §Bug 1
- **Archivos:** componente FilterChip / CategoryPill en Log screen (React Native / Expo)
- **Impacto:** control prácticamente inutilizable (~180-200px alto × 30-50px ancho). Desktop y mobile.
- **Fix:** revisar `flexDirection`, `height`, `aspectRatio` en el componente. Screenshot: `docs/superpowers/audits/2026-04-17-frontend-screenshots/log-desktop-viewport.jpeg`.

### C5. Rate-limit Capital.com por falta de session token caching
- **Fuente:** log-analyzer Patrón 2 + Patrón 7
- **Archivos:** `backend/broker/capital_client.py:148` (`_create_session`), `backend/core/trading_engine.py:553`
- **Evidencia:** 2026-04-15 22:38:38 UTC — `error.too-many.requests` durante auth post-redeploy. 65 reinicios del servicio en 48h (1 cada 45min promedio) saturan el rate limit de Capital.com (~10 login/hora).
- **Impacto:** riesgo de ventana operativa muerta cuando el broker rechaza auth.
- **Fix:** cachear `CST`/`X-SECURITY-TOKEN` en volumen `atlas-data/capital_session.json` con TTL 10min. Además, backoff exponencial con jitter para retries 429.

---

## ALTOS (11) — se atacan todos

### A1. RED TP_max prioriza Fib 1.272/1.618, PDF dice Fib 1.0
- **Fuente:** audit-mentoria §4
- **Archivos:** `backend/strategies/base.py:2399-2478` (`RedStrategy.get_tp_levels`)
- **Mentoría:** PDF pg.6 "RED (con HTF a favor): Extensión de Fibonacci de **1**" (no 1.272/1.618).
- **Fix:** para RED+HTF favor+Wave 3, priorizar `ext_1.0`; 1.272/1.618 solo como escaladas opcionales.

### A2. Comentarios falsos "NON-NEGOTIABLE per mentorship" en risk_swing y max_total_risk
- **Fuente:** audit-mentoria §5 + §6
- **Archivos:** `backend/config.py:87-88`, `backend/config.py:691` (perfil tradinglab_recommended)
- **Nota:** los valores (1% / 5%) son **caps conscientes** para capital 190.88. NO revertimos los valores. PERO los comentarios mienten sobre la fuente.
- **Fix:** actualizar comments a "cap de seguridad para capital bajo; mentoría original: 3% / 7% (PDF pg.3)". Borrar "NON-NEGOTIABLE".

### A3. BE trigger = "risk_distance" (oral) vs PDF = "pct_to_tp1" (0.50)
- **Fuente:** audit-mentoria §7
- **Archivos:** `backend/config.py:141`, `backend/core/position_manager.py:632-637`
- **Mentoría:** PDF pg.5 "mitad del beneficio hasta el Take Profit 1".
- **Nota:** el default oral de Alex dice "1% de ganancia" = risk_distance para R:R 1:1. PDF es autoritativo y más robusto (sirve para R:R 2:1 también).
- **Fix:** cambiar default a `be_trigger_method = "pct_to_tp1"` con `move_sl_to_be_pct_to_tp1 = 0.50`. Mantener `risk_distance` como opción.

### A4. Trailing no espera ruptura del máximo/mínimo anterior
- **Fuente:** audit-mentoria §8
- **Archivos:** `backend/core/position_manager.py:656-705` (`_handle_be_phase`)
- **Mentoría:** Short Term — "Hasta que no se rompa, evidentemente, este máximo anterior, no vamos a utilizarla (la EMA)". BE → esperar ruptura del swing → entonces trailing.
- **Fix:** paso intermedio entre BE y TRAILING: monitorizar `current_price > last_swing_high_before_entry` (BUY) o `<` (SELL). Swing info ya disponible en `_latest_swings`.

### A5. Security fail-open cuando no hay API keys configuradas
- **Fuente:** static-bug-hunter Bug 1
- **Archivos:** `backend/core/security.py:108-115` (`validate_key`)
- **Evidencia:** si `self.api_keys` está vacío → `return True` para cualquier request. Solo un `logger.error`.
- **Impacto:** despliegue nuevo sin keys queda completamente abierto.
- **Fix:** devolver `False` y requerir `generate_api_key()` CLI previo al primer startup, o generar una random key en primer boot y loggear una sola vez.

### A6. `core/trading_engine.py` cobertura 25%
- **Fuente:** static-bug-hunter Top 2
- **Archivos:** `backend/core/trading_engine.py` (1190/1593 líneas sin ejercitar)
- **Impacto:** scans, WS broadcasts, news close, Friday close, funded phase advance — sin tests. Regresiones pasan silenciosas.
- **Fix:** añadir tests unitarios para happy path y edge cases de los orquestadores principales. Cobertura objetivo ≥ 50%.

### A7. Duplicate sub-tab bars en Market y Log
- **Fuente:** frontend-verifier Bug 2
- **Archivos:** `frontend/app/(tabs)/Market/_layout.tsx`, `frontend/app/(tabs)/Log/_layout.tsx`, y componentes pantalla
- **Evidencia:** dos barras de navegación ("Watchlist | Crypto" arriba + pill "WATCHLIST / CRYPTO" abajo). Peor: no siempre tienen las mismas opciones (Exam falta en la pill inferior del Log).
- **Fix:** consolidar en una sola fuente de verdad. Eliminar una de las dos capas.

### A8. Desktop renderiza los 5 tab-screens simultáneamente (multiplica polling)
- **Fuente:** frontend-verifier Bug 3
- **Archivos:** `frontend/app/(tabs)/_layout.tsx` o equivalente
- **Evidencia:** 5 screens montadas → ~20 GETs redundantes a `/account`, `/watchlist`, `/analysis/*`. Mobile OK.
- **Fix:** `unmountOnBlur: true` o `display: none` en screens inactivas en desktop.

### A9. 404s de Capital.com con retry innecesario (3x por símbolo)
- **Fuente:** log-analyzer Patrón 4
- **Archivos:** `backend/broker/capital_client.py:272` (`_get`)
- **Evidencia:** 63 warnings de 404 en 12 min (tráfico de auditoría con símbolos ficticios). Cada uno reintenta 3 veces.
- **Fix:** whitelist de status no-retriable: `if status in (400, 404, 422): raise immediately`.

### A10. 65 "Invalid API key" desde IP del usuario (181.54.54.234)
- **Fuente:** log-analyzer Patrón 3
- **Archivos:** `backend/core/security.py:235`
- **Evidencia:** picos concentrados en 2026-04-16 16:00-23:00 desde la IP de Sergio. Parece script local con API key obsoleta.
- **Fix:** (a) rotar `API_SECRET_KEY` en EasyPanel env y (b) añadir rate limit para intentos con API key inválida.

### A11. News filter fallback a 0 eventos cuando ambas fuentes fallan
- **Fuente:** log-analyzer Patrón 6
- **Archivos:** `backend/core/news_filter.py:362-516`
- **Evidencia:** 2026-04-16 17:08:41 — FairEconomy 429 + TradingEconomics DNS fail simultáneos → "Using 0 known recurring events as fallback". Riesgo: tradear durante NFP/FOMC sin saber.
- **Fix:** cachear último calendar exitoso en `/app/data/news_cache.json` + hardcodear eventos recurrentes conocidos (NFP primer viernes, FOMC fechas).

---

## MEDIOS (13) — se atacan los relevantes al blindaje

### M1. 50% risk reduction hardcoded a % de profit vs "ruptura de estructura"
- **Fuente:** audit-mentoria §9
- **Archivos:** `backend/core/position_manager.py:608-629`
- **Fix:** usar `_latest_swings` para detectar ruptura de estructura como trigger, no proxy de 50% profit.

### M2. WHITE TP_max no implementa explícitamente "máximo/mínimo del impulso de 4H"
- **Fuente:** audit-mentoria §12
- **Archivos:** `backend/strategies/base.py` (`WhiteStrategy.get_tp_levels`)
- **Fix:** añadir detección de swing impulse en H4 y usar ese high/low como TP_max.

### M3. Scalping hereda max_trades_per_day=3 y cooldown=120min de day trading
- **Fuente:** audit-mentoria §14
- **Archivos:** `backend/config.py:149-151`, `backend/core/trading_engine.py:1901-1918`
- **Decisión:** scalping está disabled para el usuario (day trading primero). Documentamos el issue pero **no lo arreglamos** esta vez (YAGNI hasta que active scalping).

### M4. avoid_news scalping 45/30 vs mentoría 60/60
- **Fuente:** audit-mentoria §17
- **Decisión:** scalping disabled → documentar, no fix ahora.

### M5. avoid_news day_trading 30/15 → buffer post-release insuficiente
- **Fuente:** audit-mentoria §18
- **Archivos:** `backend/core/news_filter.py:50`
- **Fix:** cambiar a `(30, 30)` para margen post-release NFP/CPI/FOMC.

### M6. M2 timeframe derivado de M1 en Capital (fidelidad aproximada)
- **Fuente:** audit-mentoria §19
- **Decisión:** funciona, documentar comment en `position_manager.py:116`. No cambiamos infra.

### M7. WebSocket TOCTOU race en connection limit
- **Fuente:** static-bug-hunter Bug 2
- **Archivos:** `backend/main.py:67-76`
- **Fix:** envolver check+append en `asyncio.Lock()`.

### M8. `datetime.now()` sin timezone en get_engine_logs
- **Fuente:** static-bug-hunter Bug 3
- **Archivos:** `backend/api/routes.py:1080`
- **Fix:** `datetime.now(timezone.utc)`.

### M9. screenshot_generator async con matplotlib sync bloquea event loop
- **Fuente:** static-bug-hunter Bug 4
- **Archivos:** `backend/core/screenshot_generator.py:78, 166`
- **Fix:** envolver `_generate_candlestick_chart` en `run_in_executor`.

### M10. `_handle_be_phase` es async pero no hace I/O async
- **Fuente:** static-bug-hunter Bug 5
- **Decisión:** penalización mínima; señal de gap lógico (EMA desde caché posiblemente stale). Documentar, no fix ahora (no hay bug funcional probado).

### M11. AsyncMock no awaited en `test_stop_engine` (warning)
- **Fuente:** static-bug-hunter Bug 9
- **Archivos:** `backend/test_bugfix005_api_ws_notifications.py::TestEngineControl::test_stop_engine`
- **Fix:** añadir `await` a las calls del AsyncMock.

### M12. SMT Divergence emite 3,582 WARNINGs (95.8% ruido)
- **Fuente:** log-analyzer Patrón 1
- **Archivos:** `backend/core/market_analyzer.py:2801`
- **Fix:** cambiar `logger.warning` a `logger.debug` (o `info`).

### M13. Frontend — "TRADES" sin valor en Log stats card
- **Fuente:** frontend-verifier Bug 4
- **Archivos:** componente StatsCard en Log
- **Fix:** fallback a "0" o "---" cuando `trades` es `undefined`/`null`.

---

## BAJOS (9) — documentados, NO se tocan (YAGNI)

- audit-mentoria §13 — BLACK min R:R 2.0 vs 2.5 sugerido
- audit-mentoria §15 — scalping BLUE threshold no expuesto (scalping disabled)
- audit-mentoria §16 — crypto reentry risk hardcoded (es default configurable, OK)
- audit-mentoria §20 — SMA 200 D sin uso activo como gate (opcional mejora)
- audit-mentoria §21 — CPA partial close no disponible (alex no toma parciales per PDF)
- audit-mentoria §22 — cooldown reset en ganancia (comportamiento razonable)
- audit-mentoria §23 — Friday close implementación correcta
- audit-mentoria §24 — scalping R:R min 1.5 (scalping disabled)
- static-bug-hunter Bugs 6, 7, 8, 10, 11 — cleanups cosméticos

---

## Plan de fixes (orden de ejecución)

**Protocolo:** por cada finding crítico y alto, crear commit atómico.

Formato de commit:
- Fixes de código: `fix(iter25+N): <descripción corta>` o `fix(audit): <short>`
- Ajuste de config: `config(audit): <cambio>`
- Tests nuevos: `test(<area>): <short>`
- Cambios frontend: `fix(frontend): <short>`

**Orden propuesto:**

### Bloque 1 — CRÍTICOS backend (core logic de trading)
1. C1 — BLUE TP1/TP_max inversion
2. C2 — Trailing EMAs 2/5 en vez de 50
3. C3 — EMA 8 Weekly filter solo para crypto
4. C5 — Session token caching Capital.com
5. A1 — RED Fib 1.0 como TP_max default
6. A3 — BE trigger pct_to_tp1 default
7. A4 — Trailing espera ruptura de swing

### Bloque 2 — CRÍTICOS frontend + altos frontend
8. C4 — Chips de filtro Log (vertical → horizontal)
9. A7 — Duplicate sub-tab bars Market/Log
10. A8 — Desktop mount only active tab
11. M13 — TRADES stat value fallback

### Bloque 3 — Altos seguridad / estabilidad
12. A5 — Security fail-closed cuando no hay keys
13. A9 — Capital.com 404 no-retry whitelist
14. A10 — Rotar API_SECRET_KEY + rate limit invalid-key intents
15. A11 — News filter cache persistente a disco

### Bloque 4 — Altos comments / coverage
16. A2 — Corregir comments falsos en config.py (mantener valores)
17. A6 — Añadir tests para trading_engine.py (objetivo 50% coverage)

### Bloque 5 — Medios seleccionados
18. M5 — avoid_news day_trading (30, 30)
19. M7 — WS TOCTOU race con asyncio.Lock
20. M8 — datetime.now(timezone.utc)
21. M9 — screenshot_generator run_in_executor
22. M11 — test_stop_engine await fix
23. M12 — SMT WARNING → DEBUG

### Bloque 6 — Medios estructurales (opcional si hay tiempo)
24. M1 — risk reduction por estructura
25. M2 — WHITE TP_max con impulso H4

Los bajos quedan documentados en este consolidado. Los medios M3/M4 de scalping se retoman cuando el usuario active scalping.

---

## Links a reports originales

- [audit-mentoria](2026-04-17-audit-mentoria.md) — 24 discrepancias
- [log-analysis](2026-04-17-log-analysis.md) — 7 patrones + Top 5
- [frontend-issues](2026-04-17-frontend-issues.md) — 4 bugs UI + observaciones
- [frontend-screenshots/](2026-04-17-frontend-screenshots/) — 15 PNGs
- [static-bugs](2026-04-17-static-bugs.md) — 11 bugs + cobertura 69%

**Estado:** consolidado listo → proceder a Fase 1.2 (config defaults) + Fase 1.3 (fixes por bloque).
