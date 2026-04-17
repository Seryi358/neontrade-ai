# Atlas ↔ TradingLab Full-Sync + Blindaje + Entregable Mentoría

**Fecha:** 2026-04-17
**Autor:** Sergio Castellanos + Claude Opus 4.7
**Estado:** Design approved → pending writing-plans
**Capital operativo:** 190.88 USD en Capital.com (cuenta 314623104804541636, MANUAL mode)
**Apalancamientos activos en broker:** divisas 100:1, índices 100:1, commodities 100:1, acciones 20:1, crypto 20:1, bonos 200:1, tasas de interés 200:1

---

## §1 Contexto y objetivos

### §1.1 Qué es Atlas
App de trading automatizado basada en la mentoría **TradingLab** (Alex Ruiz). Stack:

- **Backend:** FastAPI (Python 3.12) en `/home/sergio/repos-seryi358/neontrade-ai/backend/`
- **Frontend:** React Native + Expo (TypeScript) en `frontend/`
- **Infra:** VPS Hostinger con EasyPanel (proyecto `n8n`, servicio `neontrade_ai`, URL `https://n8n-neontrade-ai.zb12wf.easypanel.host/`)
- **Broker:** Capital.com (sesión MANUAL, cuenta 314623104804541636)
- **Notificaciones:** Gmail OAuth2 desde scastellanos@phinodia.com
- **Volumes críticos:** `atlas-data` (`/app/data`), `atlas-logs` (`/app/logs`)

### §1.2 Estado actual
- Rama `main` al commit `d2af5c3 fix(iter24): email alerts legibility + XSS escape + goodTillDate + WS shape`
- 24 iteraciones de fixes desde lanzamiento
- Audit previo del 2026-04-15 (`AUDIT_REPORT_2026-04-15.md`): switch de scalping a day trading, 33 discrepancias detectadas, 23 arregladas → **~10 pendientes**
- Mentoría TradingLab en `TradingLab_Notas/` con 5 módulos (Trading Mastery 4 niveles, Scalping, SMC, Cuentas Fondeadas, Criptomonedas)
- Sin CLAUDE.md (tarea paralela)

### §1.3 Objetivos del proyecto
1. **Sync total** mentoría ↔ app: cero discrepancias críticas entre lo que Alex enseña y lo que la app hace
2. **Blindaje**: broker, emails, IA, risk, drawdown, monetary, calendar, CP management, simulación end-to-end — todo verificado antes de tocar dinero real
3. **Config por defecto adaptada** a 190.88 USD + apalancamientos Capital.com
4. **Entregable mentoría**: 3 trades reales con screenshot + análisis por estrategia, aprobados manualmente por Sergio

### §1.4 Non-goals (fuera de scope)
- No activar AUTO mode
- No activar scalping (mentoría dice "domina day trading primero")
- No operar con capital > 190.88 USD
- No tocar credenciales broker sin pedir
- No refactoring general del código no relacionado con discrepancias encontradas

---

## §2 Fase 1 — Blindaje (sin dinero real hasta completar)

### §2.1 Paralelización con 4 subagentes Opus 4.7 en worktrees aislados

**Regla de oro:** cada subagente trabaja en su propio worktree para evitar race conditions en lecturas y permitir escrituras aisladas donde aplique.

#### §2.1.1 Subagente `audit-mentoria`
- **Worktree:** `../neontrade-ai-audit/` (branch `audit/mentoria-sync-2026-04-17`)
- **Modo:** solo-lectura de código y mentoría; puede escribir solo su propio reporte en `docs/superpowers/audits/`
- **Input:**
  - `TradingLab_Notas/` completa (5 módulos)
  - `backend/` completo (Python)
  - `AUDIT_REPORT_2026-04-15.md` (para no re-descubrir lo ya cerrado)
- **Tarea:** comparar letra-por-letra mentoría ↔ código, agrupada por tema (estrategias BLUE/RED/GREEN/HAMMER, risk management, drawdown, CP management, calendar, broker, IA prompts, strategy detection pipeline D→H4→H1→M5)
- **Output:** `docs/superpowers/audits/2026-04-17-audit-mentoria.md` con tabla: `{tema, mentoría dice, app hace, discrepancia, severidad (crit/alto/medio/bajo), archivos afectados, sugerencia de fix}`
- **Severidad crítica = discrepancia que haría perder dinero real**

#### §2.1.2 Subagente `log-analyzer`
- **Worktree:** `../neontrade-ai-logs/` (branch `audit/logs-2026-04-17`)
- **Modo:** solo-lectura (API EasyPanel + tRPC); puede escribir solo su reporte en `docs/superpowers/audits/`
- **Input:**
  - Logs de EasyPanel (últimas 48h via tRPC `services.app.getLogs` o similar)
  - Credenciales: scastellanos@phinodia.com (password in personal manager — NEVER commit; see Claude memory `reference_phinodia_credentials.md`)
  - Volúmenes `atlas-logs` si son accesibles vía EasyPanel API
- **Tarea:** detectar errores, warnings repetidos, excepciones no capturadas, patrones sospechosos (401/429 de broker, timeouts, OOM, crashes de WebSocket)
- **Output:** `docs/superpowers/audits/2026-04-17-log-analysis.md` con: `{timestamp, severidad, mensaje, frecuencia, diagnóstico probable, acción recomendada}`

#### §2.1.3 Subagente `frontend-verifier`
- **Worktree:** `../neontrade-ai-frontend/` (branch `audit/frontend-2026-04-17`)
- **Modo:** solo-lectura de código + Playwright contra PROD URL; escribe reporte + screenshots en `docs/superpowers/audits/`
- **Input:**
  - URL prod: `https://n8n-neontrade-ai.zb12wf.easypanel.host/`
  - API key desde frontend HTML (`window.__ATLAS_API_KEY__`)
  - `frontend/src/` para referencia de componentes
- **Tarea:** screenshots sistemáticos de cada tab (Home, Trade, Market, Log, Settings) en desktop + mobile viewport; interacción con cada control; verificar: fonts (SF Pro Display fallback), layouts, errores de consola, network errors, XSS en alertas
- **Output:**
  - `docs/superpowers/audits/2026-04-17-frontend-screenshots/` (PNGs organizados por tab y estado)
  - `docs/superpowers/audits/2026-04-17-frontend-issues.md` con bugs UI detectados

#### §2.1.4 Subagente `static-bug-hunter`
- **Worktree:** `../neontrade-ai-bugs/` (branch `audit/static-bugs-2026-04-17`)
- **Modo:** lectura + ejecución local de tests (NO push)
- **Input:** `backend/` completo
- **Tarea:**
  - Correr `pytest backend/` con cobertura
  - Revisión estática: race conditions, escapes sin validar, SQL injection, hardcoded secrets, dead code, inconsistencia de tipos
  - Verificar consistency de imports, contratos de schemas Pydantic, handlers WebSocket
- **Output:** `docs/superpowers/audits/2026-04-17-static-bugs.md` con: `{archivo:línea, tipo bug, hipótesis, test sugerido, prioridad}`

#### §2.1.5 Dispatch protocol
- Main agent crea los 4 worktrees con `git worktree add`
- Dispatch simultáneo de los 4 subagentes Opus 4.7 via Agent tool con `subagent_type: "general-purpose"` (o specialized si aplica) y `isolation: "worktree"` donde sea posible
- Main agent espera a los 4 outputs en paralelo
- Si un subagente falla, se re-intenta una vez antes de continuar sin él

### §2.2 Consolidación (main agent)

- Leer los 4 outputs de subagentes
- Consolidar en `docs/superpowers/audits/2026-04-17-findings-consolidated.md`
- Priorización:
  - **Crítico:** pérdida de dinero / trades incorrectos / broker desconectado sin alert
  - **Alto:** emails no enviados, IA mal configurada, calendar events perdidos
  - **Medio:** UI rota, logs ruidosos, mensajes confusos
  - **Bajo:** mejora cosmética, refactor opcional

### §2.3 Config por defecto aplicada a capital 190.88 USD

Archivos a modificar (según mentoría):

| Setting | Valor | Unidad | Fuente mentoría |
|---|---|---|---|
| `trading_style` | `day_trading` | - | Alex: "el mejor estilo independientemente" |
| `risk_per_trade_day_trading` | 0.01 | fracción | Ch18.3 Regla del 1% |
| `risk_usd_per_trade` | 1.91 | USD | 1% × 190.88 |
| `max_trades_per_day` | 3 | - | Day trading quality > quantity |
| `cooldown_minutes_after_losses` | 120 | min | 2h tras 2 losses consecutivos |
| `max_consecutive_losses_before_cooldown` | 2 | - | Risk mgmt |
| `max_total_open_risk` | 0.05 | fracción | Conservative para 190.88 |
| `drawdown_method` | `fixed_levels` | - | Mentoría |
| `drawdown_levels` | `{4.12: 0.0075, 6.18: 0.0050, 8.23: 0.0025}` | drawdown% → risk% | Mentoría |
| `scalping_enabled` | `false` | - | Master day trading first |
| `strategies_active` | `["BLUE", "RED"]` | - | Mentoría: start con estas |
| `trading_hours_utc` | `"07:00-21:00"` | - | London + NY sessions |
| `discretion_pct` | 0.0 | - | Beginners: follow plan |
| `be_trigger_method` | `risk_distance` | - | Alex: "cuando tengo 1% ganancia" |
| `position_management_mode` | `CP` | - | Alex: "salir cuanto antes" |
| `cp_trailing_ema_tf` | `M5` | - | Mentoría |
| `cp_trailing_ema_period` | 50 | - | Mentoría |
| `strategy_pipeline` | `D→H4→H1→M5` | timeframes | Mentoría |
| `mode` | `MANUAL` | - | Usuario aprueba cada trade |
| `watchlist` | (10 forex pairs per memoria) | - | Mentoría forex-focus |

**Apalancamientos** (configurados por categoría de instrumento, reflejan lo activo en Capital.com):

| Categoría | Leverage |
|---|---|
| forex | 100 |
| indices | 100 |
| commodities | 100 |
| stocks | 20 |
| crypto | 20 |
| bonds | 200 |
| rates | 200 |

**Position sizing validado:**
- EUR/USD con SL 20 pips: ~1000 unidades (del audit previo)
- Margin a 100:1: ~11.27 USD (holgura amplia en 190.88 USD)
- En nivel DD 3 (0.25% risk = 0.48 USD): 218 unidades — por encima del mínimo Capital.com (100 unidades)

**Archivo(s) a tocar:** esperados `backend/config.py` (constantes default) y `backend/core/risk_manager.py` (lógica de risk/leverage); posible `backend/db/` si hay tabla de settings persistidos. El audit §2.1 confirma paths exactos antes de tocar.

### §2.4 Protocolo de fixes (commits atómicos)

Cada bug/config-change encontrado:
1. Trabajar directamente en `main` (los fixes son secuenciales y el repo usa webhook de EasyPanel que auto-deploya en cada push; no hay PR review process)
2. Escribir test que reproduzca el bug (si aplica)
3. Fix minimal
4. Verificar test pasa localmente (`pytest backend/<test>`)
5. Commit con formato: `fix(iter25+N): <descripción corta>` | `config: <cambio>` | `audit: <discrepancia cerrada>`
6. Acumular commits locales; push único al final de Fase 1 (para que EasyPanel deploye una sola vez tras todo verde)

**Orden de fixes:** críticos → altos → medios. Los bajos se documentan pero no se tocan (YAGNI).

### §2.5 Testing matrix exhaustiva

Organizado por módulo:

| Módulo | Tests a correr | Método |
|---|---|---|
| **Broker** | connection, session token refresh, order placement, position update, position close, 429/401 retry | `test_broker_connection.py` + nuevos + live contra broker demo si disponible |
| **Emails** | Gmail OAuth2 válido, envío setup alert, envío close alert, legibilidad HTML, XSS escape (ya fixed iter24) | Tests unit + envío real a scastellanos@phinodia.com |
| **IA** | Prompt construction, validación de response, decisiones (accept/reject) | `test_05_ai_prompt.py` + nuevos edge cases |
| **Risk** | 1% calc, max total risk, leverage por categoría, position sizing | `test_bugfix002_risk_manager.py` + nuevos |
| **Drawdown** | Niveles fijos 4.12→0.75%, 6.18→0.50%, 8.23→0.25% | Test parametrizado |
| **Calendar** | Eventos económicos próximos, filtrado por impacto, blackout periods | `test_alerts_coverage.py` extendido |
| **Monetary** | Margin calc, lot rounding, currency conversion | Test unit nuevo si falta |
| **CP Management** | M5 EMA 50 trailing, BE move, close paths | `test_bugfix002_position_manager.py` + integración |
| **Strategy detection** | BLUE pipeline D→H4→H1→M5, RED pipeline, rejection de setups no válidos | `test_01_strategies.py` + integración |
| **UI** | Tabs load, API key injection, WebSocket conecta, font fallback | Playwright (reuse §2.1.3) |
| **DB** | Persistence de settings, history, equity curve en `/app/data` volume | Test de integración |
| **WebSocket** | Auth gate, reconexión, broadcast de eventos | Tests nuevos si faltan |

**Criterio de pase:** 100% pytest passing + tests nuevos verdes.

### §2.6 Simulación end-to-end con trades falsos

Script/orquestador que simule:

1. **Setup detection**: inyectar candles sintéticas que disparen strategy BLUE (long) y RED (short)
2. **Validación IA**: verificar que responde accept/reject con prompt correcto
3. **Position sizing**: verificar cálculo de unidades para 190.88 USD con apalancamiento correcto
4. **Alert flow**: setup → Gmail enviado → WebSocket push → UI muestra
5. **Aprobación**: simular click en "Aprobar" (Trade tab)
6. **Order placement**: en MANUAL mode, verificar que envía orden al broker (demo/mock)
7. **Management**: simular price updates, verificar trailing M5 EMA 50, BE move a 1x risk
8. **Cierre**: cubrir 5 escenarios → win por TP, loss por SL, BE hit, trailing stop, close manual
9. **Post-close**: verificar email de close, screenshot capture, registro en history

**Implementación:** nuevo archivo `backend/test_simulation_end2end.py` (reusa `pytest` infra existente, fixtures pueden vivir ahí mismo o en `conftest.py`).

### §2.7 Re-verificación final (go/no-go)

- **Smoke test manual**: login app → recorrer tabs → forzar alerta de prueba → verificar Gmail en bandeja
- **Playwright re-run** de §2.1.3 → comparar screenshots para no-regresiones visuales
- **Log sanity check**: últimos 10 min de EasyPanel sin ERROR ni CRITICAL
- **Config verification**: endpoint `/config` (o similar) devuelve values exactos de §2.3
- **Broker connection test**: endpoint de diagnóstico responde `healthy` con token válido

**GO criterion:** todo verde → proceder a Fase 2. Si algo rojo → volver a §2.4 con el nuevo finding.

---

## §3 Fase 2 — Entregable mentoría (solo si §2 verde)

### §3.1 Preparación
- Confirmar `mode = MANUAL` en config prod
- Confirmar feature "3 trades screenshot + análisis" funcional (tests ya pasaron en §2.5)
- Sergio listo para recibir Gmail alerts y aprobar en la app

### §3.2 Ejecución (3 trades)
- Atlas escanea mercado (07-21 UTC) buscando setups BLUE/RED válidos
- Cuando detecta setup:
  1. IA valida
  2. Gmail alert con detalle (par, strategy, entry, SL, TP, size, análisis)
  3. WebSocket push a Trade tab
  4. Sergio abre app, revisa, decide Aprobar/Rechazar
  5. Si aprueba → orden a Capital.com → position gestionada con CP trailing + BE
  6. Screenshot automático del setup capturado en el momento
  7. Cierre: screenshot automático de posición cerrada + análisis (strategy ejecutada, resultado)
- Repetir hasta 3 trades cerrados

### §3.3 Entregable final
- Documento `docs/mentoria/2026-04-17-entregable-3-trades.md` con:
  - Trade 1: screenshot + strategy + análisis + resultado
  - Trade 2: ídem
  - Trade 3: ídem
  - Conclusión: "3 trades completados aplicando estrategias BLUE/RED según TradingLab"
- Screenshots en `docs/mentoria/screenshots/`

---

## §4 Restricciones (reafirmadas)

- Ningún deploy a prod sin §2 completa y verde
- No activar AUTO mode
- No activar scalping
- No tocar `.env` directamente; usar EasyPanel tRPC (`services.app.updateEnv`) si hace falta
- No operar con capital superior a 190.88 USD hasta entregar mentoría
- No hacer refactoring general fuera del scope de discrepancias o bugs
- Git: sin `--no-verify`, sin `--amend` a commits ya pusheados, sin `push --force` a `main`

---

## §5 Riesgos y mitigaciones

| Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|
| Race condition entre subagentes | Media | Alto | Worktrees aislados + solo-lectura donde aplique |
| Deploy a prod rompe algo | Baja | Alto | Smoke test post-deploy; rollback con `git revert` si falla |
| Trade real con bug no detectado | Baja | Crítico | Fase 1 completa + simulación end-to-end antes de Fase 2 |
| Quota subagentes Opus 4.7 agotada | Media | Medio | Serializar los 4 si es necesario |
| Capital.com demo no disponible | Media | Medio | Fallback: mock del broker client en simulación |
| EasyPanel API rate-limit | Baja | Medio | Cache logs localmente, retry con backoff |
| Gmail OAuth token expira | Baja | Medio | Re-auth + `setup_gmail.py` (ya existe) |
| Setup no detectado en mercado real | Alta | Medio | Expectativa 0-3 setups/día; si día sin setup, esperar siguiente sesión |

---

## §6 Success criteria

- [ ] 4 subagentes completados con outputs consolidados
- [ ] Discrepancias críticas = 0; altas resueltas o documentadas con razón
- [ ] Config §2.3 aplicada y verificada en prod
- [ ] `pytest backend/` 100% passing
- [ ] Simulación end-to-end cubre 5 escenarios de cierre
- [ ] Broker connection estable (sin 401/429 en smoke)
- [ ] Gmail entregado en prueba real a scastellanos@phinodia.com
- [ ] Playwright screenshots sin regresiones visuales
- [ ] Logs EasyPanel limpios post-deploy
- [ ] 3 trades reales ejecutados y documentados
- [ ] Entregable de mentoría enviado

---

## §7 Orden de ejecución (resumen)

1. Crear 4 worktrees + dispatch 4 subagentes Opus 4.7 (§2.1)
2. Consolidar findings (§2.2)
3. Aplicar config por defecto (§2.3)
4. Fix bugs por prioridad (§2.4)
5. Correr testing matrix (§2.5)
6. Correr simulación end-to-end (§2.6)
7. Go/no-go verificación (§2.7)
8. Deploy consolidado a prod
9. Smoke prod post-deploy
10. Fase 2: esperar setups + 3 trades reales con aprobación manual (§3)
11. Entregable mentoría (§3.3)
12. (Opcional, paralelo) CLAUDE.md nuevo via `claude-md-management` skill

---

## §8 Deliverables finales

- `docs/superpowers/audits/2026-04-17-*.md` (4 outputs + 1 consolidado)
- `docs/superpowers/specs/2026-04-17-atlas-tradinglab-full-sync-design.md` (este doc)
- `docs/superpowers/plans/2026-04-17-atlas-tradinglab-full-sync-plan.md` (generado por writing-plans)
- Commits en `main` con fixes (`iter25..iter25+N`)
- `docs/mentoria/2026-04-17-entregable-3-trades.md` + screenshots
- Nuevo `CLAUDE.md` en raíz (opcional paralelo)

---

**Estado:** approved-by-user (2026-04-17). Next: invocar `superpowers:writing-plans` para generar plan de implementación.
