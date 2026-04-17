# Atlas ↔ TradingLab Full-Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-04-17-atlas-tradinglab-full-sync-design.md`

**Goal:** Sincronizar letra-por-letra la mentoría TradingLab con la app Atlas, blindar la app contra bugs y configuraciones incorrectas, y entregar el proyecto final de mentoría (3 trades reales aprobados manualmente por Sergio) sin pérdidas por bug.

**Architecture:** Fase 1 (blindaje) dispatches 4 subagentes Opus 4.7 en paralelo dentro de worktrees aislados para auditoría (mentoría vs código, logs EasyPanel, screenshots frontend, bugs estáticos), consolida findings, aplica config por defecto (day_trading, 1% risk sobre 190.88 USD, BLUE+RED, BE risk_distance, CP short-term, apalancamientos Capital.com), ejecuta fixes atómicos, corre testing matrix exhaustiva + simulación end-to-end, y valida pre-deploy. Fase 2 opera con mercado real en MANUAL mode: Sergio aprueba cada uno de los 3 trades requeridos por la mentoría.

**Tech Stack:** Python 3.12 + FastAPI + pytest, React Native/Expo TypeScript, Playwright (screenshots), Capital.com REST/WebSocket, Gmail OAuth2, EasyPanel tRPC, GitHub (webhook auto-deploy), Supabase, git worktrees.

**Capital operativo:** 190.88 USD (Capital.com cuenta 314623104804541636, MANUAL mode).

**Apalancamientos activos:** forex 100:1, indices 100:1, commodities 100:1, stocks 20:1, crypto 20:1, bonds 200:1, rates 200:1.

---

## Fase 1.1 — Dispatch paralelo de subagentes de auditoría

### Task 1: Verificar estado del repo y crear 4 worktrees aislados

**Files:**
- Modify (git): 4 nuevos worktrees en `/home/sergio/repos-seryi358/`

- [ ] **Step 1.1: Verificar git status limpio**

Run: `cd /home/sergio/repos-seryi358/neontrade-ai && git status --short`
Expected: vacío o solo archivos ignorables (transcripts `.txt`, `backend/data/`).

- [ ] **Step 1.2: Confirmar rama main actualizada**

Run: `git fetch origin main && git log --oneline -3`
Expected: HEAD en `66afce2 spec: Atlas↔TradingLab full-sync...` (el commit del spec escrito).

- [ ] **Step 1.3: Crear worktree para audit-mentoria**

Run:
```bash
cd /home/sergio/repos-seryi358/neontrade-ai
git worktree add ../neontrade-ai-audit -b audit/mentoria-sync-2026-04-17
```
Expected: `Preparing worktree (new branch 'audit/mentoria-sync-2026-04-17')`

- [ ] **Step 1.4: Crear worktree para log-analyzer**

Run:
```bash
git worktree add ../neontrade-ai-logs -b audit/logs-2026-04-17
```
Expected: worktree creado.

- [ ] **Step 1.5: Crear worktree para frontend-verifier**

Run:
```bash
git worktree add ../neontrade-ai-frontend -b audit/frontend-2026-04-17
```
Expected: worktree creado.

- [ ] **Step 1.6: Crear worktree para static-bug-hunter**

Run:
```bash
git worktree add ../neontrade-ai-bugs -b audit/static-bugs-2026-04-17
```
Expected: worktree creado.

- [ ] **Step 1.7: Verificar worktrees listados**

Run: `git worktree list`
Expected: 5 líneas (main + 4 audits).

- [ ] **Step 1.8: Crear directorio `docs/superpowers/audits/` en main si no existe**

Run:
```bash
cd /home/sergio/repos-seryi358/neontrade-ai
mkdir -p docs/superpowers/audits
```

- [ ] **Step 1.9: Commit del directorio audits con placeholder `.gitkeep`**

Run:
```bash
touch docs/superpowers/audits/.gitkeep
git add docs/superpowers/audits/.gitkeep
git commit -m "chore: scaffold docs/superpowers/audits/ for 4 subagent reports"
```
Expected: commit creado en `main`.

---

### Task 2: Dispatch subagente `audit-mentoria` (Opus 4.7)

**Files:**
- Create: `../neontrade-ai-audit/docs/superpowers/audits/2026-04-17-audit-mentoria.md` (el subagente la escribe)

- [ ] **Step 2.1: Invocar Agent tool con subagent_type="general-purpose" y modelo opus**

Prompt del subagente (copiar literal):

> Eres el subagente `audit-mentoria`. Trabajas en el worktree `/home/sergio/repos-seryi358/neontrade-ai-audit/` en la rama `audit/mentoria-sync-2026-04-17`.
>
> **Contexto:** Atlas es una app de trading automatizado basada en la mentoría TradingLab (Alex Ruiz). Ya hay un audit previo del 2026-04-15 en `AUDIT_REPORT_2026-04-15.md` que cerró 23 de 33 discrepancias; quedan ~10 pendientes y probablemente surgieron nuevas.
>
> **Tu tarea:** compara letra-por-letra la mentoría `TradingLab_Notas/` (5 módulos: Trading Mastery niveles 01-04, Workshop de Scalping, Workshop de SMC, Workshop de Cuentas Fondeadas, Esp. Criptomonedas) contra el código backend en `backend/`. Agrupa por tema:
> - Estrategias (BLUE, RED, GREEN, HAMMER si aplica)
> - Risk management (1% rule, max risk, cooldown)
> - Drawdown (niveles fijos, scaling de risk)
> - CP management (M5 EMA 50 trailing, BE)
> - Calendar económico (filtrado, blackouts)
> - Broker (Capital.com integration)
> - IA prompts (validación de setups)
> - Strategy detection pipeline (D→H4→H1→M5)
> - Monetary/position sizing
>
> **No modifiques código.** Solo escribe tu reporte en `docs/superpowers/audits/2026-04-17-audit-mentoria.md` con esta estructura por cada discrepancia:
>
> ```markdown
> ### Discrepancia [N]: [Título corto]
> - **Tema:** [categoría]
> - **Mentoría dice:** [cita exacta o paráfrasis con referencia a archivo]
> - **App hace:** [descripción con `archivo.py:línea`]
> - **Severidad:** crítica | alta | media | baja
> - **Archivos afectados:** [lista]
> - **Sugerencia de fix:** [propuesta]
> ```
>
> **Criterio de severidad:**
> - Crítica: haría perder dinero real (ej.: size incorrecto, leverage mal, BE mal)
> - Alta: emails perdidos, IA mal configurada, setups falsos positivos
> - Media: UI confusa, logs ruidosos, comportamiento raro no destructivo
> - Baja: cosmética
>
> **Entrega final:**
> 1. Reporte en el path especificado
> 2. Commit: `audit(mentoria): 2026-04-17 discrepancies report`
> 3. Reporte sumario breve (≤200 palabras) al cerrar: cuántas discrepancias por severidad + top 3 críticas.
>
> Prioriza profundidad sobre velocidad. Usa Grep, Read, Glob extensivamente. NO ejecutes código, NO deploys, NO toques otros archivos.

Parámetros del Agent tool:
- `description`: "Audit mentoría TradingLab vs código backend"
- `subagent_type`: "general-purpose"
- `model`: "opus"
- `isolation`: omitir (ya está el worktree listo; evitamos duplicar)
- `run_in_background`: true (se lanzará junto con los otros 3)

- [ ] **Step 2.2: Anotar task ID del subagente**

Cuando el Agent tool responda con ID de background task, anotarlo (se usará en §2.6 para poll).

---

### Task 3: Dispatch subagente `log-analyzer` (Opus 4.7)

**Files:**
- Create: `../neontrade-ai-logs/docs/superpowers/audits/2026-04-17-log-analysis.md`

- [ ] **Step 3.1: Invocar Agent tool**

Prompt del subagente:

> Eres el subagente `log-analyzer`. Trabajas en `/home/sergio/repos-seryi358/neontrade-ai-logs/` en rama `audit/logs-2026-04-17`.
>
> **Objetivo:** detectar errores, warnings repetidos, excepciones no capturadas y patrones sospechosos en los logs productivos de EasyPanel de las últimas 48 horas.
>
> **Acceso a EasyPanel:**
> - URL: `https://zb12wf.easypanel.host`
> - Auth: POST a `/api/trpc/auth.login?batch=1` con body `{"0":{"json":{"email":"scastellanos@phinodia.com","password":"Gordis.358"}}}`
> - Token devuelto se usa como `Authorization: Bearer <token>`
> - Proyecto: `n8n`, servicio: `neontrade_ai`
> - tRPC para logs: probar `projects.inspectProject`, `services.app.getLogs` o `services.app.inspect` (explorar tRPC discovery si es necesario)
>
> **Tareas:**
> 1. Autenticarte y descargar logs últimas 48h
> 2. Clasificar eventos por severidad (DEBUG, INFO, WARNING, ERROR, CRITICAL)
> 3. Detectar patrones: 401/429 de broker Capital.com, timeouts, OOM, WebSocket disconnects, OAuth Gmail failures, DB write lock errors (el proyecto tuvo varios), race conditions
> 4. Agrupar por frecuencia; el bug más frecuente y el más crítico son los primeros en reporte
>
> **Entrega:** `docs/superpowers/audits/2026-04-17-log-analysis.md` con:
> - Resumen ejecutivo (≤5 líneas)
> - Tabla: `| timestamp | severidad | mensaje | frecuencia | diagnóstico probable | acción recomendada |`
> - Top 5 patrones más urgentes
>
> Commit: `audit(logs): 2026-04-17 EasyPanel 48h analysis`. Sumario ≤200 palabras al final.

Parámetros: igual que Task 2, `description`: "Análisis logs EasyPanel", `model`: "opus", `run_in_background`: true.

- [ ] **Step 3.2: Anotar task ID**

---

### Task 4: Dispatch subagente `frontend-verifier` (Opus 4.7)

**Files:**
- Create: `../neontrade-ai-frontend/docs/superpowers/audits/2026-04-17-frontend-issues.md`
- Create: `../neontrade-ai-frontend/docs/superpowers/audits/2026-04-17-frontend-screenshots/` (PNGs)

- [ ] **Step 4.1: Invocar Agent tool**

Prompt:

> Eres el subagente `frontend-verifier`. Trabajas en `/home/sergio/repos-seryi358/neontrade-ai-frontend/` en rama `audit/frontend-2026-04-17`.
>
> **Objetivo:** verificar visualmente y funcionalmente el frontend en producción.
>
> **Target URL:** `https://n8n-neontrade-ai.zb12wf.easypanel.host/`
>
> **Herramientas disponibles:** Playwright MCP (ya configurado):
> - `mcp__plugin_playwright_playwright__browser_navigate`
> - `mcp__plugin_playwright_playwright__browser_snapshot`
> - `mcp__plugin_playwright_playwright__browser_take_screenshot`
> - `mcp__plugin_playwright_playwright__browser_click`
> - `mcp__plugin_playwright_playwright__browser_console_messages`
> - `mcp__plugin_playwright_playwright__browser_network_requests`
> - `mcp__plugin_playwright_playwright__browser_resize`
>
> **Procedimiento:**
> 1. Abrir la URL en desktop (1920×1080), tomar screenshot de Home
> 2. Recorrer tabs: Home, Trade, Market, Log, Settings — screenshot de cada una
> 3. Interactuar con cada control (dropdowns, inputs, toggles); screenshots antes/después de interacción
> 4. Resize a mobile (390×844), repetir los 5 tabs
> 5. Verificar console (no errores rojos), network (no 4xx/5xx), fonts cargadas
> 6. Verificar `window.__ATLAS_API_KEY__` está inyectada
> 7. Probar un "setup de prueba" si hay botón (en Settings o Log tab)
>
> **Entrega:**
> - Screenshots en `docs/superpowers/audits/2026-04-17-frontend-screenshots/` con nombres descriptivos (ej.: `home-desktop.png`, `trade-mobile-filled.png`)
> - Reporte `docs/superpowers/audits/2026-04-17-frontend-issues.md` con:
>   - Lista de bugs UI (severidad, screenshot ref, descripción, sugerencia)
>   - Errores de consola por tab
>   - Errores de network por tab
>   - Verificación de font fallback (SF Pro vs system)
>
> Commit: `audit(frontend): 2026-04-17 Playwright sweep`. Sumario ≤200 palabras.

Parámetros: `description`: "Audit frontend con Playwright", `model`: "opus", `run_in_background`: true.

- [ ] **Step 4.2: Anotar task ID**

---

### Task 5: Dispatch subagente `static-bug-hunter` (Opus 4.7)

**Files:**
- Create: `../neontrade-ai-bugs/docs/superpowers/audits/2026-04-17-static-bugs.md`

- [ ] **Step 5.1: Invocar Agent tool**

Prompt:

> Eres el subagente `static-bug-hunter`. Trabajas en `/home/sergio/repos-seryi358/neontrade-ai-bugs/` en rama `audit/static-bugs-2026-04-17`.
>
> **Objetivo:** encontrar bugs estáticos y de runtime en el backend.
>
> **Procedimiento:**
> 1. Setup Python env si hace falta: `python3 -m venv .venv && source .venv/bin/activate && pip install -r backend/requirements-dev.txt`
> 2. Correr `pytest backend/ -v --tb=short` y capturar output completo
> 3. Correr `pytest backend/ --cov=backend --cov-report=term-missing` para cobertura
> 4. Revisión estática (Grep) de patrones sospechosos:
>    - `except:` sin tipo (catch demasiado amplio)
>    - `print(` fuera de scripts (debería usar logger)
>    - `os.system`, `shell=True` (command injection)
>    - String concatenation en queries SQL
>    - Tokens/passwords/API keys hardcoded
>    - TODO/FIXME/XXX pendientes
>    - `async def` sin `await` o con bloqueos síncronos
>    - Race conditions en handlers de WebSocket
>    - Mutable defaults en funciones (`def f(x=[])`)
>    - Contratos Pydantic inconsistentes entre request/response
>    - Handlers sin validación de input
> 5. Tipar consistencia: mypy si está instalado, o inspección manual de signatures críticas
> 6. Imports: detectar dead imports, circular imports
>
> **Entrega:** `docs/superpowers/audits/2026-04-17-static-bugs.md` con:
> - Resumen: tests pasan (X/Y), cobertura total (Z%)
> - Tabla: `| archivo:línea | tipo bug | hipótesis | test sugerido | prioridad |`
> - Tests fallando con causa raíz
> - Top 5 issues más críticos
>
> Commit: `audit(static): 2026-04-17 bugs + tests report`. Sumario ≤200 palabras.

Parámetros: `description`: "Static bug hunting + pytest", `model`: "opus", `run_in_background`: true.

- [ ] **Step 5.2: Anotar task ID**

---

### Task 6: Esperar completion de los 4 subagentes

- [ ] **Step 6.1: Poll o esperar notificación**

Cuando los 4 subagentes corren en background, el runtime notificará al main agent cuando cada uno termine. NO usar `sleep` ni `poll manual`: esperar la notificación del sistema.

Si alguno falla o timeouts (>30 min), re-intentar una vez con el mismo prompt. Si vuelve a fallar, documentar en `docs/superpowers/audits/2026-04-17-dispatch-failures.md` y continuar con los 3 que sí terminaron.

- [ ] **Step 6.2: Verificar que cada worktree tiene el commit esperado**

Run:
```bash
cd /home/sergio/repos-seryi358/neontrade-ai-audit && git log --oneline -1
cd /home/sergio/repos-seryi358/neontrade-ai-logs && git log --oneline -1
cd /home/sergio/repos-seryi358/neontrade-ai-frontend && git log --oneline -1
cd /home/sergio/repos-seryi358/neontrade-ai-bugs && git log --oneline -1
```
Expected: cada uno muestra commit `audit(...): 2026-04-17 ...`.

---

### Task 7: Consolidar findings en documento priorizado

**Files:**
- Create: `docs/superpowers/audits/2026-04-17-findings-consolidated.md` (en `main`)

- [ ] **Step 7.1: Copiar los 4 reports al worktree main**

Run:
```bash
cd /home/sergio/repos-seryi358/neontrade-ai
cp ../neontrade-ai-audit/docs/superpowers/audits/2026-04-17-audit-mentoria.md docs/superpowers/audits/
cp ../neontrade-ai-logs/docs/superpowers/audits/2026-04-17-log-analysis.md docs/superpowers/audits/
cp ../neontrade-ai-frontend/docs/superpowers/audits/2026-04-17-frontend-issues.md docs/superpowers/audits/
cp -r ../neontrade-ai-frontend/docs/superpowers/audits/2026-04-17-frontend-screenshots docs/superpowers/audits/
cp ../neontrade-ai-bugs/docs/superpowers/audits/2026-04-17-static-bugs.md docs/superpowers/audits/
```

- [ ] **Step 7.2: Escribir documento consolidado**

Create `docs/superpowers/audits/2026-04-17-findings-consolidated.md` con esta estructura:

```markdown
# Findings consolidados 2026-04-17

## Resumen ejecutivo
- Total findings: N
- Críticos: C | Altos: A | Medios: M | Bajos: B
- Fuentes: audit-mentoria, log-analyzer, frontend-verifier, static-bug-hunter

## Priorización unificada (crítico → alto → medio → bajo)

### CRÍTICOS
1. [Título] — [archivo:línea] — [fuente] — [descripción 1-2 líneas] — [sugerencia fix]
2. ...

### ALTOS
...

### MEDIOS
...

### BAJOS (documentados, no se tocan por YAGNI)
...

## Plan de fixes

Cada crítico y alto → commit atómico. Formato sugerido de commits:
`fix(iter25+N): <descripción>`

## Links a reports originales
- [audit-mentoria](2026-04-17-audit-mentoria.md)
- [log-analysis](2026-04-17-log-analysis.md)
- [frontend-issues](2026-04-17-frontend-issues.md)
- [static-bugs](2026-04-17-static-bugs.md)
```

- [ ] **Step 7.3: Commit de findings consolidados**

Run:
```bash
git add docs/superpowers/audits/
git commit -m "audit: consolidated findings from 4 subagents (2026-04-17)"
```

---

### Task 8: Limpieza de worktrees completados

- [ ] **Step 8.1: Remover worktrees temporales**

Run:
```bash
cd /home/sergio/repos-seryi358/neontrade-ai
git worktree remove ../neontrade-ai-audit
git worktree remove ../neontrade-ai-logs
git worktree remove ../neontrade-ai-frontend
git worktree remove ../neontrade-ai-bugs
git branch -D audit/mentoria-sync-2026-04-17 audit/logs-2026-04-17 audit/frontend-2026-04-17 audit/static-bugs-2026-04-17
```
Expected: 4 worktrees removidos, 4 branches borradas.

- [ ] **Step 8.2: Verificar worktree list solo tiene main**

Run: `git worktree list`
Expected: 1 línea (solo `main`).

---

## Fase 1.2 — Aplicar config por defecto según mentoría + capital

### Task 9: Leer estado actual de `backend/config.py`

**Files:**
- Read: `backend/config.py`

- [ ] **Step 9.1: Ver contenido actual**

Run: `cat backend/config.py` (o usar Read tool).

- [ ] **Step 9.2: Identificar dónde viven los defaults**

Los defaults pueden estar en `config.py`, en una `settings_table` de DB, o en ambos. Grep:
```
Grep pattern "trading_style|risk_per_trade|max_trades_per_day" en backend/
```
Anotar qué archivos contienen esas constantes.

---

### Task 10: Escribir test de config esperada

**Files:**
- Create: `backend/test_config_defaults_mentoria.py`

- [ ] **Step 10.1: Escribir test que verifica cada valor de config**

Código completo del test (TDD: rojo primero):

```python
"""Verifica que los defaults de config coinciden con mentoría TradingLab + capital 190.88 USD."""
import pytest
from backend.config import (
    TRADING_STYLE,
    RISK_PER_TRADE_DAY_TRADING,
    MAX_TRADES_PER_DAY,
    COOLDOWN_MINUTES_AFTER_LOSSES,
    MAX_CONSECUTIVE_LOSSES_BEFORE_COOLDOWN,
    MAX_TOTAL_OPEN_RISK,
    DRAWDOWN_METHOD,
    DRAWDOWN_LEVELS,
    SCALPING_ENABLED,
    STRATEGIES_ACTIVE,
    TRADING_HOURS_UTC,
    DISCRETION_PCT,
    BE_TRIGGER_METHOD,
    POSITION_MANAGEMENT_MODE,
    CP_TRAILING_EMA_TF,
    CP_TRAILING_EMA_PERIOD,
    STRATEGY_PIPELINE,
    MODE,
    LEVERAGE_BY_CATEGORY,
)


def test_trading_style_is_day_trading():
    assert TRADING_STYLE == "day_trading"


def test_risk_per_trade_is_1_percent():
    assert RISK_PER_TRADE_DAY_TRADING == 0.01


def test_max_trades_per_day_is_3():
    assert MAX_TRADES_PER_DAY == 3


def test_cooldown_minutes_is_120():
    assert COOLDOWN_MINUTES_AFTER_LOSSES == 120


def test_max_consecutive_losses_is_2():
    assert MAX_CONSECUTIVE_LOSSES_BEFORE_COOLDOWN == 2


def test_max_total_open_risk_is_5_percent():
    assert MAX_TOTAL_OPEN_RISK == 0.05


def test_drawdown_method_is_fixed_levels():
    assert DRAWDOWN_METHOD == "fixed_levels"


def test_drawdown_levels_match_mentoria():
    assert DRAWDOWN_LEVELS == {4.12: 0.0075, 6.18: 0.0050, 8.23: 0.0025}


def test_scalping_disabled():
    assert SCALPING_ENABLED is False


def test_strategies_active_are_blue_and_red():
    assert set(STRATEGIES_ACTIVE) == {"BLUE", "RED"}


def test_trading_hours_utc():
    assert TRADING_HOURS_UTC == "07:00-21:00"


def test_discretion_is_zero():
    assert DISCRETION_PCT == 0.0


def test_be_trigger_method_is_risk_distance():
    assert BE_TRIGGER_METHOD == "risk_distance"


def test_position_management_is_cp():
    assert POSITION_MANAGEMENT_MODE == "CP"


def test_cp_trailing_ema_m5_50():
    assert CP_TRAILING_EMA_TF == "M5"
    assert CP_TRAILING_EMA_PERIOD == 50


def test_strategy_pipeline_d_h4_h1_m5():
    assert STRATEGY_PIPELINE == ["D", "H4", "H1", "M5"]


def test_mode_is_manual():
    assert MODE == "MANUAL"


def test_leverage_forex():
    assert LEVERAGE_BY_CATEGORY["forex"] == 100


def test_leverage_indices():
    assert LEVERAGE_BY_CATEGORY["indices"] == 100


def test_leverage_commodities():
    assert LEVERAGE_BY_CATEGORY["commodities"] == 100


def test_leverage_stocks():
    assert LEVERAGE_BY_CATEGORY["stocks"] == 20


def test_leverage_crypto():
    assert LEVERAGE_BY_CATEGORY["crypto"] == 20


def test_leverage_bonds():
    assert LEVERAGE_BY_CATEGORY["bonds"] == 200


def test_leverage_rates():
    assert LEVERAGE_BY_CATEGORY["rates"] == 200
```

- [ ] **Step 10.2: Correr test para verificar que falla (RED)**

Run: `cd /home/sergio/repos-seryi358/neontrade-ai && pytest backend/test_config_defaults_mentoria.py -v`
Expected: FAIL (probablemente `ImportError` o `AttributeError` por constantes faltantes).

---

### Task 11: Implementar config defaults (GREEN)

**Files:**
- Modify: `backend/config.py` (los paths exactos los confirma Task 9)

- [ ] **Step 11.1: Añadir constantes faltantes a `backend/config.py`**

Añadir (al final o donde corresponda según patrón existente):

```python
# ── TradingLab mentorship defaults (2026-04-17 sync) ──

TRADING_STYLE = "day_trading"
RISK_PER_TRADE_DAY_TRADING = 0.01  # 1% sobre equity
MAX_TRADES_PER_DAY = 3
COOLDOWN_MINUTES_AFTER_LOSSES = 120
MAX_CONSECUTIVE_LOSSES_BEFORE_COOLDOWN = 2
MAX_TOTAL_OPEN_RISK = 0.05  # 5% conservative para 190.88 USD
DRAWDOWN_METHOD = "fixed_levels"
DRAWDOWN_LEVELS = {4.12: 0.0075, 6.18: 0.0050, 8.23: 0.0025}
SCALPING_ENABLED = False  # Master day trading first
STRATEGIES_ACTIVE = ["BLUE", "RED"]
TRADING_HOURS_UTC = "07:00-21:00"
DISCRETION_PCT = 0.0
BE_TRIGGER_METHOD = "risk_distance"
POSITION_MANAGEMENT_MODE = "CP"
CP_TRAILING_EMA_TF = "M5"
CP_TRAILING_EMA_PERIOD = 50
STRATEGY_PIPELINE = ["D", "H4", "H1", "M5"]
MODE = "MANUAL"

LEVERAGE_BY_CATEGORY = {
    "forex": 100,
    "indices": 100,
    "commodities": 100,
    "stocks": 20,
    "crypto": 20,
    "bonds": 200,
    "rates": 200,
}
```

Si ya existen con otro nombre, renombrar referencias en el código (los consumidores) para que usen estos nombres canónicos. Los imports se verifican en Task 12.

- [ ] **Step 11.2: Correr test para verificar que pasa (GREEN)**

Run: `pytest backend/test_config_defaults_mentoria.py -v`
Expected: 24 passed.

---

### Task 12: Verificar que consumidores de config usan los nuevos nombres

**Files:**
- Modify: todos los archivos de `backend/` que hayan consumido los nombres antiguos.

- [ ] **Step 12.1: Grep de uso en consumidores**

Run:
```
Grep pattern "trading_style|risk_per_trade_day_trading|max_trades_per_day|drawdown_levels|cp_trailing" en backend/
```

- [ ] **Step 12.2: Actualizar imports/referencias para cada archivo**

Por cada archivo encontrado: cambiar el nombre del símbolo al canónico definido en Task 11. Mantener lógica intacta.

- [ ] **Step 12.3: Correr suite completa para verificar que no rompí nada**

Run: `pytest backend/ -v -x`
Expected: 100% passing. Si algo falla, fix y repetir.

- [ ] **Step 12.4: Commit**

Run:
```bash
git add backend/config.py backend/test_config_defaults_mentoria.py <cualquier otro consumidor modificado>
git commit -m "config: sync TradingLab mentorship defaults for 190.88 USD capital + Capital.com leverages"
```

---

### Task 13: Verificar endpoint de config devuelve los valores correctos

**Files:**
- Test: `backend/test_config_endpoint.py` (nuevo o extensión de existente)

- [ ] **Step 13.1: Buscar endpoint de exposición de config**

```
Grep pattern "@app\.(get|post).*config|router\.(get|post).*config" en backend/api/
```

- [ ] **Step 13.2: Escribir test de integración del endpoint**

Si el endpoint es `/config`:

```python
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

def test_config_endpoint_returns_mentorship_defaults():
    resp = client.get("/config")
    assert resp.status_code == 200
    data = resp.json()
    assert data["trading_style"] == "day_trading"
    assert data["max_trades_per_day"] == 3
    assert data["mode"] == "MANUAL"
    assert data["strategies_active"] == ["BLUE", "RED"]
    assert data["scalping_enabled"] is False
```

Si el endpoint no existe, crearlo en `backend/api/` siguiendo el patrón de los otros routers. No es obligatorio: si hay otra forma de exponer config (e.g., `/status` que incluye config), adaptarlo a eso.

- [ ] **Step 13.3: Correr test y fix si falla**

Run: `pytest backend/test_config_endpoint.py -v`
Expected: PASS.

- [ ] **Step 13.4: Commit**

```bash
git add backend/test_config_endpoint.py <otros si aplica>
git commit -m "test: config endpoint returns mentorship defaults"
```

---

## Fase 1.3 — Fixes iterativos (protocolo)

### Task 14: Protocolo de fixes por cada finding crítico/alto

**Este no es un paso único** — es un loop sobre cada finding consolidado en Task 7.

Para cada finding en `docs/superpowers/audits/2026-04-17-findings-consolidated.md`, crítico o alto, repetir este protocolo:

- [ ] **Step 14.A: Leer el finding** (archivo:línea, descripción, fix sugerido)

- [ ] **Step 14.B: Escribir test que reproduzca el bug (si aplica)**

Si el bug es de lógica (no de infra/UI), escribir un test unitario en `backend/test_<area>_<bug_short>.py` o extender uno existente si tiene sentido. Formato:
```python
def test_<describe_buggy_behavior>():
    # Arrange
    ...
    # Act
    result = buggy_function(...)
    # Assert
    assert result == expected
```

- [ ] **Step 14.C: Correr el test y verificar que falla (RED)**

Run: `pytest backend/test_<area>_<bug_short>.py::test_<name> -v`
Expected: FAIL reproduciendo el bug.

- [ ] **Step 14.D: Aplicar el fix mínimo**

Modificar solamente el archivo:línea afectado. Sin refactoring de áreas no relacionadas.

- [ ] **Step 14.E: Correr el test y verificar que pasa (GREEN)**

Run: `pytest backend/test_<area>_<bug_short>.py::test_<name> -v`
Expected: PASS.

- [ ] **Step 14.F: Correr suite completa**

Run: `pytest backend/ -v -x`
Expected: 100% PASS. Si algo rompió, revertir fix y reconsiderar.

- [ ] **Step 14.G: Commit atómico**

```bash
git add <archivos del fix + test>
git commit -m "fix(iter25+N): <descripción corta del bug fixed>"
```

**N incrementa** con cada fix. Primer fix = iter25, segundo = iter26, etc.

**Orden:** todos los críticos → todos los altos. Medios y bajos NO se tocan (documentados en consolidado, YAGNI).

---

### Task 15: Verificación post-fixes

- [ ] **Step 15.1: Correr suite completa con cobertura**

Run: `pytest backend/ --cov=backend --cov-report=term-missing -v`
Expected: 100% PASS. Cobertura ≥ la del audit inicial (no regresión).

- [ ] **Step 15.2: Revisar git log de fixes**

Run: `git log --oneline main ^66afce2`
Expected: una lista limpia de commits `fix(iterXX): ...` y `config: ...`.

- [ ] **Step 15.3: Si todo verde, proceder a Fase 1.4**

Si algo no pasó, retroceder a Task 14 para bugs residuales.

---

## Fase 1.4 — Testing matrix exhaustiva

### Task 16: Test broker connection end-to-end

**Files:**
- Modify/extend: `backend/test_broker_connection.py`

- [ ] **Step 16.1: Leer test actual**

Ver qué cubre `test_broker_connection.py`. Anotar gaps: session refresh, 429 retry, 401 re-auth, order placement con mock o demo, position update, position close.

- [ ] **Step 16.2: Añadir tests faltantes**

Ejemplo para session refresh:
```python
def test_session_refreshes_on_401():
    """Al recibir 401 de Capital.com, el cliente debe re-autenticar y reintentar la request."""
    from backend.broker.capital import CapitalClient
    client = CapitalClient(...)
    # Mock: primer call devuelve 401, segundo 200
    # Assert: request original se completó exitosamente tras re-auth
    ...
```

(El contenido exacto depende del patrón de mocking existente en el archivo; seguirlo.)

- [ ] **Step 16.3: Correr y verificar PASS**

Run: `pytest backend/test_broker_connection.py -v`
Expected: PASS.

- [ ] **Step 16.4: Commit**

```bash
git add backend/test_broker_connection.py
git commit -m "test(broker): session refresh, 429/401 retry, order lifecycle"
```

---

### Task 17: Test Gmail email delivery

**Files:**
- Modify/extend: `backend/test_alerts_coverage.py` o nuevo `backend/test_gmail_alerts.py`

- [ ] **Step 17.1: Verificar Gmail OAuth2 válido**

Corre script manual:
```bash
cd /home/sergio/repos-seryi358/neontrade-ai
python backend/setup_gmail.py --verify
```
Expected: "Gmail auth OK".

- [ ] **Step 17.2: Test unit de render HTML de setup alert**

Añadir test que construye un setup de prueba y verifica que el HTML resultante:
- Incluye par, strategy, entry, SL, TP, size, análisis
- Tiene escape XSS (ya fixed iter24, verificar no-regresión)
- Es legible (no texto blanco sobre blanco)

```python
def test_setup_alert_html_renders_correctly():
    from backend.notifications.gmail_alerts import render_setup_alert_html
    setup = {"pair": "EUR/USD", "strategy": "BLUE", "entry": 1.08500, "sl": 1.08300, "tp": 1.08900, "size": 1000, "analysis": "Break of structure + fib 61.8"}
    html = render_setup_alert_html(setup)
    assert "EUR/USD" in html
    assert "BLUE" in html
    assert "1.08500" in html
    assert "<script>" not in html  # XSS guard
```

- [ ] **Step 17.3: Test de envío real (opcional, fuera de CI)**

```python
@pytest.mark.live
def test_send_real_alert_to_sergio():
    from backend.notifications.gmail_alerts import send_setup_alert
    result = send_setup_alert(to="scastellanos@phinodia.com", setup={"pair": "EUR/USD", ...})
    assert result is True
```

- [ ] **Step 17.4: Correr + commit**

Run: `pytest backend/test_gmail_alerts.py -v` (excluir `@pytest.mark.live` en CI)
Expected: PASS.

Commit:
```bash
git add backend/test_gmail_alerts.py
git commit -m "test(notifications): Gmail setup alert HTML render + XSS + live mark"
```

---

### Task 18: Test IA prompt validation

**Files:**
- Modify/extend: `backend/test_05_ai_prompt.py`

- [ ] **Step 18.1: Añadir casos edge**

Tests nuevos:
- Setup incompleto (falta SL) → IA rechaza
- Setup con RR < min_rr_blue_c → IA rechaza
- Setup en blackout de calendar → IA rechaza
- Setup válido con strategy BLUE → IA acepta
- Setup válido con strategy RED → IA acepta

Formato similar a existentes en el archivo.

- [ ] **Step 18.2: Correr + commit**

Run: `pytest backend/test_05_ai_prompt.py -v`
Expected: PASS.

Commit:
```bash
git add backend/test_05_ai_prompt.py
git commit -m "test(ai): edge cases + calendar blackout + strategy rejection"
```

---

### Task 19: Test risk manager (leverage + sizing)

**Files:**
- Modify/extend: `backend/test_bugfix002_risk_manager.py`

- [ ] **Step 19.1: Añadir tests para cada categoría de leverage**

```python
@pytest.mark.parametrize("category,leverage,expected_margin_pct", [
    ("forex", 100, 0.01),
    ("indices", 100, 0.01),
    ("commodities", 100, 0.01),
    ("stocks", 20, 0.05),
    ("crypto", 20, 0.05),
    ("bonds", 200, 0.005),
    ("rates", 200, 0.005),
])
def test_margin_requirement_by_category(category, leverage, expected_margin_pct):
    from backend.core.risk_manager import calculate_margin_requirement
    notional = 10000  # USD
    margin = calculate_margin_requirement(notional, category)
    assert abs(margin - notional * expected_margin_pct) < 0.01
```

- [ ] **Step 19.2: Test de position sizing para 190.88 USD equity**

```python
def test_position_size_for_190_usd_eur_usd_20_pips():
    from backend.core.risk_manager import calculate_position_size
    size = calculate_position_size(equity=190.88, risk_pct=0.01, pair="EUR/USD", sl_pips=20)
    assert 900 <= size <= 1050  # aprox 1000 unidades (±5%)
```

- [ ] **Step 19.3: Correr + commit**

Run: `pytest backend/test_bugfix002_risk_manager.py -v`
Expected: PASS.

```bash
git add backend/test_bugfix002_risk_manager.py
git commit -m "test(risk): leverage by category + position sizing for 190.88 USD"
```

---

### Task 20: Test drawdown niveles fijos

**Files:**
- Create: `backend/test_drawdown_levels.py`

- [ ] **Step 20.1: Escribir test parametrizado**

```python
import pytest
from backend.core.risk_manager import compute_risk_with_drawdown


@pytest.mark.parametrize("drawdown_pct,expected_risk", [
    (0.0, 0.01),      # no DD → 1%
    (3.0, 0.01),      # <4.12% → 1%
    (4.12, 0.0075),   # exactamente en nivel 1 → 0.75%
    (5.5, 0.0075),    # entre 4.12 y 6.18 → 0.75%
    (6.18, 0.0050),   # nivel 2 → 0.50%
    (7.5, 0.0050),    # entre 6.18 y 8.23 → 0.50%
    (8.23, 0.0025),   # nivel 3 → 0.25%
    (10.0, 0.0025),   # >8.23 → 0.25%
])
def test_drawdown_reduces_risk(drawdown_pct, expected_risk):
    risk = compute_risk_with_drawdown(base_risk=0.01, drawdown_pct=drawdown_pct)
    assert risk == expected_risk
```

- [ ] **Step 20.2: Si `compute_risk_with_drawdown` no existe, crearlo en `backend/core/risk_manager.py`**

```python
from backend.config import DRAWDOWN_LEVELS


def compute_risk_with_drawdown(base_risk: float, drawdown_pct: float) -> float:
    """Reduce risk según niveles fijos de drawdown (mentoría TradingLab)."""
    thresholds = sorted(DRAWDOWN_LEVELS.items())  # [(4.12, 0.0075), (6.18, 0.0050), (8.23, 0.0025)]
    effective_risk = base_risk
    for threshold, reduced_risk in thresholds:
        if drawdown_pct >= threshold:
            effective_risk = reduced_risk
    return effective_risk
```

- [ ] **Step 20.3: Correr + commit**

Run: `pytest backend/test_drawdown_levels.py -v`
Expected: 8 passed.

```bash
git add backend/test_drawdown_levels.py backend/core/risk_manager.py
git commit -m "feat(risk): drawdown-based risk reduction (TradingLab fixed levels)"
```

---

### Task 21: Test calendar económico

**Files:**
- Modify/extend: `backend/test_alerts_coverage.py` o buscar tests existentes de `eco_calendar/`

- [ ] **Step 21.1: Verificar que hay tests de calendar**

```
Grep pattern "eco_calendar|economic_calendar|calendar" en backend/
```

Si no hay, crear `backend/test_eco_calendar.py`.

- [ ] **Step 21.2: Añadir tests clave**

- Evento HIGH impact en próximos 30 min para par específico → setup rechazado
- Evento LOW impact → setup aceptado
- Sin eventos → setup aceptado
- Evento LIVE en este momento → setup rechazado

- [ ] **Step 21.3: Correr + commit**

```bash
pytest backend/test_eco_calendar.py -v
git add backend/test_eco_calendar.py
git commit -m "test(calendar): blackout by impact + timing"
```

---

### Task 22: Test CP management (M5 EMA 50 trailing + BE)

**Files:**
- Modify/extend: `backend/test_bugfix002_position_manager.py`

- [ ] **Step 22.1: Tests clave**

- Precio se mueve 1x distancia de riesgo a favor → SL se mueve a BE (entry)
- Precio sigue moviéndose a favor → trailing sigue M5 EMA 50
- Precio regresa y toca trailing → posición cerrada
- En RED strategy: lógica inversa (short)

```python
def test_be_trigger_at_1x_risk_distance():
    from backend.core.position_manager import PositionManager
    pm = PositionManager(...)
    pm.open_position(entry=1.0850, sl=1.0830, direction="long")  # 20 pip SL
    pm.on_price_update(price=1.0870)  # +20 pip = 1x risk
    assert pm.current_sl == 1.0850  # BE
```

- [ ] **Step 22.2: Correr + commit**

```bash
pytest backend/test_bugfix002_position_manager.py -v
git add backend/test_bugfix002_position_manager.py
git commit -m "test(position_manager): BE trigger + M5 EMA 50 trailing for BLUE and RED"
```

---

### Task 23: Test strategy detection D→H4→H1→M5

**Files:**
- Modify/extend: `backend/test_01_strategies.py`

- [ ] **Step 23.1: Tests clave**

- Setup BLUE: D bullish + H4 pullback + H1 BoS + M5 entry → detectado
- Setup RED: D bearish + H4 pullback + H1 BoS + M5 entry → detectado
- D ranging → no setup
- HTF no alineado → no setup

Ya hay tests. Añadir los que falten según audit.

- [ ] **Step 23.2: Correr + commit**

```bash
pytest backend/test_01_strategies.py -v
git add backend/test_01_strategies.py
git commit -m "test(strategies): D→H4→H1→M5 alignment rejection cases"
```

---

### Task 24: Test WebSocket auth gate + reconnect

**Files:**
- Create: `backend/test_websocket.py` (si no existe con este scope)

- [ ] **Step 24.1: Test clave**

- Conexión sin API key → rechazada
- Conexión con API key correcta → aceptada, recibe push de eventos
- Desconexión del cliente → backend libera recursos

```python
from fastapi.testclient import TestClient
from backend.main import app


def test_ws_rejects_without_api_key():
    client = TestClient(app)
    with pytest.raises(Exception):
        with client.websocket_connect("/ws"):
            pass


def test_ws_accepts_with_api_key():
    client = TestClient(app)
    with client.websocket_connect(f"/ws?api_key={VALID_KEY}") as ws:
        msg = ws.receive_json()
        assert "type" in msg
```

- [ ] **Step 24.2: Correr + commit**

```bash
pytest backend/test_websocket.py -v
git add backend/test_websocket.py
git commit -m "test(ws): auth gate + reconnect"
```

---

### Task 25: Test DB persistence

**Files:**
- Create/extend: `backend/test_db_persistence.py`

- [ ] **Step 25.1: Verificar que settings, history y equity_curve se persisten en `/app/data`**

```python
def test_settings_persist_across_restart():
    from backend.db import save_setting, load_setting
    save_setting("test_key", "test_value")
    # Simular reinicio recreando conexión
    reload_db()
    assert load_setting("test_key") == "test_value"


def test_history_append():
    from backend.db import append_history, list_history
    append_history({"pair": "EUR/USD", "pnl": 1.5})
    assert len(list_history()) >= 1
```

- [ ] **Step 25.2: Correr + commit**

```bash
pytest backend/test_db_persistence.py -v
git add backend/test_db_persistence.py
git commit -m "test(db): settings + history + equity_curve persistence"
```

---

## Fase 1.5 — Simulación end-to-end con trades falsos

### Task 26: Escribir script de simulación end-to-end

**Files:**
- Create: `backend/test_simulation_end2end.py`

- [ ] **Step 26.1: Esqueleto del test**

```python
"""Simulación end-to-end: setup → alert → approve → execute → manage → close (5 escenarios)."""
import pytest
from unittest.mock import MagicMock, patch
from backend.main import app
from fastapi.testclient import TestClient


@pytest.fixture
def mock_broker():
    """Mock de CapitalClient para no tocar broker real."""
    with patch("backend.broker.capital.CapitalClient") as mock:
        instance = mock.return_value
        instance.place_order.return_value = {"id": "order_123", "status": "filled"}
        instance.get_position.return_value = {"id": "pos_123", "pnl": 0}
        instance.close_position.return_value = {"status": "closed"}
        yield instance


@pytest.fixture
def mock_gmail(monkeypatch):
    """Mock de Gmail para no enviar emails reales."""
    sent = []
    def fake_send(to, subject, html):
        sent.append({"to": to, "subject": subject, "html": html})
        return True
    monkeypatch.setattr("backend.notifications.gmail_alerts.send_email", fake_send)
    return sent


def test_scenario_1_blue_long_tp_win(mock_broker, mock_gmail):
    """Setup BLUE long → aprobado → TP alcanzado → close con ganancia."""
    # Arrange: inyectar candles sintéticas que disparen BLUE
    # Act: correr loop de engine una vez
    # Assert: order placed, Gmail sent, position closed on TP
    ...


def test_scenario_2_red_short_sl_loss(mock_broker, mock_gmail):
    """Setup RED short → aprobado → SL alcanzado → close con pérdida."""
    ...


def test_scenario_3_be_triggered(mock_broker, mock_gmail):
    """Setup BLUE long → precio a +1x risk → SL movido a BE → precio regresa → close en BE."""
    ...


def test_scenario_4_trailing_stop(mock_broker, mock_gmail):
    """Setup BLUE long → precio sube → trailing M5 EMA 50 sigue → precio corrige → close con ganancia parcial."""
    ...


def test_scenario_5_manual_close(mock_broker, mock_gmail):
    """Setup BLUE long → usuario hace close manual antes de TP/SL → close a precio de mercado."""
    ...
```

Cada escenario necesita datos sintéticos de candles. Los detalles los resuelves usando helpers existentes (grep `conftest.py` y utilidades en backend).

- [ ] **Step 26.2: Implementar escenario 1 completo**

Llenar el cuerpo de `test_scenario_1_blue_long_tp_win` con:
- Carga de candles sintéticas (pair EUR/USD, TF D/H4/H1/M5 alineados BLUE)
- Llamada al engine loop / strategy detector
- Assertions sobre `mock_broker.place_order` called
- Assertions sobre `mock_gmail` tiene 1 email con tipo "setup"
- Simular aprobación por API (endpoint `/trade/approve` o similar)
- Simular precio moviéndose a TP
- Assertions sobre position closed y Gmail close alert enviado

- [ ] **Step 26.3: Correr escenario 1**

Run: `pytest backend/test_simulation_end2end.py::test_scenario_1_blue_long_tp_win -v`
Expected: PASS.

- [ ] **Step 26.4: Implementar escenarios 2-5 siguiendo el mismo patrón**

Cada uno: arrange → act → assert; reutilizar helpers del escenario 1.

- [ ] **Step 26.5: Correr suite completa de simulación**

Run: `pytest backend/test_simulation_end2end.py -v`
Expected: 5 passed.

- [ ] **Step 26.6: Commit**

```bash
git add backend/test_simulation_end2end.py
git commit -m "test(simulation): end-to-end 5 scenarios (BLUE/RED x win/loss/BE/trailing/manual)"
```

---

## Fase 1.6 — Re-verificación final (go/no-go)

### Task 27: Smoke test manual de endpoints clave

- [ ] **Step 27.1: Iniciar backend localmente**

Run:
```bash
cd /home/sergio/repos-seryi358/neontrade-ai
python3 -m venv .venv 2>/dev/null || true
source .venv/bin/activate
pip install -q -r backend/requirements.txt
uvicorn backend.main:app --port 8000 &
SMOKE_PID=$!
sleep 3
```

- [ ] **Step 27.2: Hit cada endpoint de diagnóstico**

```bash
curl -s http://localhost:8000/health | jq .
curl -s http://localhost:8000/status | jq .
curl -s http://localhost:8000/config 2>/dev/null || echo "endpoint /config no existe (ok si se expone diferente)"
curl -s http://localhost:8000/broker 2>/dev/null | jq .
curl -s http://localhost:8000/account 2>/dev/null | jq .
```
Expected: todos devuelven 2xx con JSON válido.

- [ ] **Step 27.3: Kill backend local**

```bash
kill $SMOKE_PID
```

---

### Task 28: Playwright re-screenshot sweep contra prod (post-deploy)

**Nota:** esto se hace DESPUÉS del deploy en Task 30, no antes.

---

### Task 29: Correr suite completa con cobertura final

- [ ] **Step 29.1: Suite completa**

Run: `pytest backend/ --cov=backend --cov-report=term-missing --cov-report=html -v`
Expected: 100% passing.

- [ ] **Step 29.2: Verificar cobertura no regresó**

Comparar con cobertura registrada en audit Task 5 (report de static-bug-hunter). La cobertura debe ser ≥ la previa.

- [ ] **Step 29.3: Si todo verde → go. Si no → retroceder a Task 14.**

---

## Fase 1.7 — Deploy consolidado a prod

### Task 30: Push a main y verificar auto-deploy de EasyPanel

- [ ] **Step 30.1: Revisar commits pendientes de push**

Run: `git log origin/main..main --oneline`
Expected: lista limpia de commits `fix(iterXX): ...`, `config: ...`, `test(...): ...`, `audit: ...`.

- [ ] **Step 30.2: Push**

Run: `git push origin main`
Expected: push exitoso, webhook de EasyPanel dispara deploy.

- [ ] **Step 30.3: Esperar 2-3 min y verificar deploy en EasyPanel**

Usar credenciales del memory `reference_phinodia_credentials.md`:
```bash
# Auth tRPC EasyPanel
curl -X POST "https://zb12wf.easypanel.host/api/trpc/auth.login?batch=1" \
  -H "Content-Type: application/json" \
  -d '{"0":{"json":{"email":"scastellanos@phinodia.com","password":"Gordis.358"}}}'
# Extraer token, luego:
curl -H "Authorization: Bearer <TOKEN>" \
  "https://zb12wf.easypanel.host/api/trpc/services.app.inspectService?...&serviceName=neontrade_ai"
```
Verificar status "running" + nueva imagen desplegada.

- [ ] **Step 30.4: Smoke en prod URL**

```bash
curl -s https://n8n-neontrade-ai.zb12wf.easypanel.host/health | jq .
```
Expected: 200, healthy.

---

### Task 31: Playwright screenshots post-deploy

**Files:**
- Create: `docs/superpowers/audits/2026-04-17-frontend-post-deploy-screenshots/`

- [ ] **Step 31.1: Invocar Playwright MCP para navegar prod URL y capturar 10 screenshots (5 tabs × desktop + mobile)**

Similar a Task 4 pero ahora en main agent. Si hay diferencias visuales vs las screenshots de Task 4 (audit), anotarlas en `docs/superpowers/audits/2026-04-17-post-deploy-visual-diff.md`.

- [ ] **Step 31.2: Commit**

```bash
git add docs/superpowers/audits/2026-04-17-frontend-post-deploy-screenshots/ docs/superpowers/audits/2026-04-17-post-deploy-visual-diff.md
git commit -m "verify(frontend): post-deploy Playwright screenshots"
git push origin main
```

---

### Task 32: Log sanity check post-deploy

- [ ] **Step 32.1: Esperar 5 min tras deploy**

Esperar con Monitor tool o ScheduleWakeup si el deploy acaba de completarse.

- [ ] **Step 32.2: Descargar logs últimos 10 min de EasyPanel**

Usar tRPC `services.app.getLogs` (credenciales memory).

- [ ] **Step 32.3: Verificar: 0 ERROR, 0 CRITICAL, WARNING solo esperados**

Si hay ERROR/CRITICAL, diagnosticar y volver a Task 14 con el nuevo bug. No proceder a Fase 2.

---

## Fase 2 — Entregable mentoría (3 trades reales)

### Task 33: Preparación de Fase 2

- [ ] **Step 33.1: Verificar `mode=MANUAL` en prod**

```bash
curl -s https://n8n-neontrade-ai.zb12wf.easypanel.host/config | jq .mode
```
Expected: `"MANUAL"`.

- [ ] **Step 33.2: Verificar balance Capital.com**

```bash
curl -s https://n8n-neontrade-ai.zb12wf.easypanel.host/account | jq .balance
```
Expected: aprox 190.88 USD.

- [ ] **Step 33.3: Verificar engine encendido + scanning**

```bash
curl -s https://n8n-neontrade-ai.zb12wf.easypanel.host/status | jq '.engine_running, .last_scan_utc'
```

- [ ] **Step 33.4: Enviar email de prueba a Sergio**

Usar endpoint `/alerts/test` (ya existe según audit 2026-04-15):
```bash
curl -X POST https://n8n-neontrade-ai.zb12wf.easypanel.host/alerts/test
```
Sergio confirma recepción en scastellanos@phinodia.com.

---

### Task 34: Trade 1 — detección, aprobación manual, ejecución, cierre

- [ ] **Step 34.1: Esperar setup (pasivo)**

Atlas escanea 07-21 UTC. Expectativa: 0-3 setups/día. Esperar notificación Gmail.

- [ ] **Step 34.2: Notificar a Sergio cuando llegue alerta**

Cuando el email llega, verificar contenido y transmitir a Sergio: "Setup en {par}, strategy {BLUE/RED}, entry {X}, SL {Y}, TP {Z}, size {N} unidades. Margin requerido: {M} USD. ¿Apruebas?"

- [ ] **Step 34.3: Sergio aprueba/rechaza en la app**

Sergio entra a `https://n8n-neontrade-ai.zb12wf.easypanel.host/`, va a Trade tab, revisa, click en "Aprobar" o "Rechazar".

- [ ] **Step 34.4: Si aprobado → Atlas envía orden a Capital.com**

Verificar en prod logs que el order fue placed (`order_id` en logs).

- [ ] **Step 34.5: Atlas gestiona posición (CP trailing + BE)**

Monitorear vía `/positions` endpoint o UI.

- [ ] **Step 34.6: Cierre (TP, SL, trailing, o manual)**

Cuando cierre, Atlas captura screenshot automáticamente y envía Gmail de close.

- [ ] **Step 34.7: Registrar análisis del Trade 1**

Create `docs/mentoria/trade_1_2026-04-17.md`:

```markdown
# Trade 1 — [fecha UTC]

- **Par:** [EUR/USD]
- **Strategy:** BLUE | RED
- **Entry:** [X]
- **SL:** [Y]
- **TP:** [Z]
- **Size:** [N] unidades
- **Margin:** [M] USD

## Análisis pre-entry
[qué vio Atlas, por qué la IA aprobó, HTF alignment]

## Screenshot entry
![entry](../mentoria/screenshots/trade_1_entry.png)

## Gestión
[resumen de price action, si hubo BE move, trailing]

## Cierre
- **Tipo:** TP | SL | trailing | manual
- **P&L:** [USD]
- **Duración:** [HH:MM]

## Screenshot cierre
![close](../mentoria/screenshots/trade_1_close.png)

## Conclusión
[qué aprendí, si se ejecutó fielmente a TradingLab]
```

- [ ] **Step 34.8: Commit**

```bash
git add docs/mentoria/
git commit -m "mentoria: trade 1 documented with screenshots + analysis"
```

---

### Task 35: Trade 2 (repetir protocolo Task 34)

Igual estructura. Puede ser días distintos si el mercado no produce setups.

---

### Task 36: Trade 3 (repetir protocolo Task 34)

Igual estructura.

---

### Task 37: Entregable final consolidado

**Files:**
- Create: `docs/mentoria/2026-04-17-entregable-3-trades.md`

- [ ] **Step 37.1: Escribir documento de entrega**

```markdown
# Entregable final Mentoría TradingLab — 3 Trades

**Alumno:** Sergio Castellanos
**Fecha:** [rango de fechas de los 3 trades]
**Capital operado:** 190.88 USD, Capital.com MANUAL mode
**Plataforma:** Atlas (app custom basada en TradingLab)

## Resumen

| Trade | Par | Strategy | Direction | P&L USD | Duración |
|---|---|---|---|---|---|
| 1 | ... | ... | ... | ... | ... |
| 2 | ... | ... | ... | ... | ... |
| 3 | ... | ... | ... | ... | ... |

**Total P&L:** X USD
**Balance final:** Y USD

## Trade 1
[link a docs/mentoria/trade_1_*.md o incluir aquí]

## Trade 2
...

## Trade 3
...

## Reflexión final

Tres trades ejecutados aplicando estrategias BLUE y RED según TradingLab. La gestión siguió el criterio CP (short-term) con BE trigger en risk_distance y trailing M5 EMA 50. Regla del 1% respetada; drawdown dentro de niveles permitidos.
```

- [ ] **Step 37.2: Commit + push**

```bash
git add docs/mentoria/
git commit -m "mentoria: entregable final 3 trades completed"
git push origin main
```

- [ ] **Step 37.3: Sergio envía a mentor de TradingLab**

Sergio copia el contenido + screenshots y lo envía por el canal de la mentoría. Fin.

---

## Fase 3 (opcional paralela) — CLAUDE.md nuevo

### Task 38: Invocar skill claude-md-management:claude-md-improver

- [ ] **Step 38.1: Invocar skill**

```
Skill: claude-md-management:claude-md-improver
```
Esto auditaría el repo y crearía/actualizaría CLAUDE.md.

- [ ] **Step 38.2: Revisar resultado + commit**

```bash
git add CLAUDE.md
git commit -m "docs: initial CLAUDE.md via claude-md-improver skill"
git push origin main
```

---

## Self-Review del plan

### Spec coverage
- §2.1 (4 subagentes) → Tasks 1-6
- §2.2 (consolidación) → Task 7
- §2.3 (config) → Tasks 9-13
- §2.4 (fixes protocol) → Tasks 14-15
- §2.5 (testing matrix) → Tasks 16-25
- §2.6 (simulación) → Task 26
- §2.7 (go/no-go verify) → Tasks 27-29
- §3.1 (preparación) → Task 33
- §3.2 (3 trades) → Tasks 34-36
- §3.3 (entregable) → Task 37
- §8 deliverables: 4 audit reports (Tasks 2-5), consolidated (Task 7), plan (este doc), fix commits (Task 14), mentoría docs (Tasks 34-37), CLAUDE.md opcional (Task 38) — ✅

### Placeholder scan
- Task 14 es un protocolo iterativo por cada finding. Esto NO es un placeholder: es un loop paramétrico sobre los findings descubiertos en Task 7. Los findings específicos no pueden enumerarse de antemano porque dependen del output de los subagentes. Justificado.
- Tasks 34-36 dependen de mercado real; no podemos predecir el par ni la estrategia exacta. Justificado.

### Type consistency
- Nombres de constantes en `backend/config.py` son uniformes (UPPER_SNAKE) y consistentes entre Task 10 (test) y Task 11 (impl).
- `compute_risk_with_drawdown` en Task 20 tiene firma consistente.
- `CapitalClient`, `PositionManager`, `render_setup_alert_html` son referencias a módulos existentes del backend; verificar exactitud durante ejecución.

### Scope
Plan enfocado al spec. Sin refactoring de áreas no relacionadas. Bajos explícitamente fuera de scope.

---

## Execution Handoff

Plan completo y guardado en `docs/superpowers/plans/2026-04-17-atlas-tradinglab-full-sync-plan.md`.

**Opciones de ejecución:**

1. **Subagent-Driven (recomendada)** — Main agent dispatches un subagente fresco Opus 4.7 por cada task, revisa output entre tasks, iteración rápida. Ideal para este plan largo con subagentes paralelos.

2. **Inline Execution** — Main agent ejecuta todas las tasks en esta sesión. Más lento pero sin overhead de dispatches extra.

Para este proyecto, **Subagent-Driven es fuertemente recomendada** porque:
- Tasks 2-5 son ya subagentes paralelos
- Cada task de testing (16-25) es independiente y paralela
- Evita quemar contexto del main agent en detalles de implementación

**Plan → proceder con Subagent-Driven.**
