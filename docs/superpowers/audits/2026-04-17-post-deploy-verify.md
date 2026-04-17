# Post-deploy verification -- Atlas prod -- 2026-04-17

Target: `https://n8n-neontrade-ai.zb12wf.easypanel.host/`
Deploy: `f34ef12` (audit fixes C4 / A7 / A8 / M13)
Tool: Playwright MCP (Chromium)
Viewports verified: 1920x1080 (desktop) y 390x844 (mobile)
Baseline para comparacion: `docs/superpowers/audits/2026-04-17-frontend-screenshots/`
Screenshots post-deploy: `/tmp/post-deploy-screenshots/` y `/home/sergio/post-deploy-screenshots/`

## Resumen ejecutivo

| Fix | Descripcion | Estado | Evidencia principal |
|---|---|---|---|
| **C4** | Chips filtro color en Log deben ser horizontales pequenos | **PASS** | chips 32px alto (antes ~180-200px) |
| **A7** | Quitar sub-tab bars duplicadas en Market y Log | **PASS** | solo 1 barra superior visible |
| **A8** | Solo tab activa montada en desktop (no 5 simultaneas) | **PASS** | contenido de tabs inactivas ausente del DOM |
| **M13** | Valor de fila TRADES en tarjeta RENDIMIENTO visible | **PASS** | texto "0" con color `rgb(29, 29, 31)` opacity 1 |

**Regresiones detectadas:** ninguna.
**Errores de consola nuevos:** 0 (solo persiste el warning benigno `Animated: useNativeDriver not supported`, pre-existente en Expo web).
**Requests 4xx/5xx:** 0 (todos los GETs a `/api/v1/*` devuelven 200).

---

## C4 -- Chips ALL/BLUE/RED/PINK/WHITE/BLACK/GREEN en Log tab

**Estado: PASS**

### Evidencia DOM (browser_evaluate)

Medicion exacta de cada chip en desktop 1920x1080 (Log tab, sub-tab History, todos los chips en fila horizontal top=311px):

| Label | Width (px) | Height (px) | Top (px) | Left (px) |
|---|---|---|---|---|
| ALL | 50 | 32 | 311 | 17 |
| BLUE | 71 | 32 | 311 | 73 |
| RED | 64 | 32 | 311 | 150 |
| PINK | 70 | 32 | 311 | 220 |
| WHITE | 80 | 32 | 311 | 296 |
| BLACK | 81 | 32 | 311 | 382 |
| GREEN | 81 | 32 | 311 | 469 |

- **Altura maxima**: 32px (todos los chips identicos).
- **Misma fila (top=311)**: confirmado flex-direction row correcto.
- En mobile 390x844, mismas dimensiones (32px alto). Los chips BLACK/GREEN quedan fuera del viewport de 390px pero accesibles por scroll horizontal (patron estandar mobile).

### Comparacion vs baseline

- Baseline (`log-desktop-viewport.jpeg`): chips renderizados como pildoras verticales altisimas ~180-200px, texto comprimido / girado, control inutilizable.
- Post-deploy (`/tmp/post-deploy-screenshots/log-desktop-post-deploy.png`): chips 32px altura, pildoras horizontales con bullet de color + label, alineadas en una sola fila. Interaccion correcta.

**Mejora clara y radical.**

### Screenshots
- `/tmp/post-deploy-screenshots/log-desktop-post-deploy.png`
- `/tmp/post-deploy-screenshots/log-mobile-post-deploy.png`

---

## A7 -- Sub-tab bars duplicadas en Market y Log

**Estado: PASS**

### Evidencia DOM

**Market (desktop + mobile):**

```json
{
  "wordCounts": {
    "watchlistLower": 1,   // "Watchlist" -- barra superior
    "watchlistUpper": 0,   // "WATCHLIST" -- ya no existe
    "cryptoLower": 1,
    "cryptoUpper": 0
  },
  "tablistCount": 1,       // solo el bottom nav principal
  "subTabsFound": []       // no hay buttons/pills duplicados con Watchlist/Crypto
}
```

**Log (desktop + mobile):**

```yaml
# browser_snapshot depth=3 sobre Log tab
- generic:
  - generic:              # sub-tabs: History / Journal / Exam (barra superior unica)
    - generic: History
    - generic: Journal
    - generic: Exam
  - generic: ...          # contenido del sub-tab activo
- tablist:                # UNICO role="tablist" en la pagina (bottom nav)
  - tab: Home
  - tab: Trade
  - tab: Market
  - tab: Log [selected]
  - tab: Settings
```

Solo existe **1** elemento con `role="tablist"` en toda la pagina (el bottom nav). Las sub-tabs superiores de Market (Watchlist/Crypto) y Log (History/Journal/Exam) son contenedores simples sin role nested. No hay segunda pill horizontal duplicando las opciones.

### Comparacion vs baseline

- Baseline `market-desktop-viewport.jpeg`: dos barras ("Watchlist | Crypto" arriba + "WATCHLIST / CRYPTO" abajo).
- Baseline `log-desktop-viewport.jpeg`: dos barras ("History | Journal | Exam" arriba + "HISTORY / JOURNAL" abajo, con opciones distintas).
- Post-deploy: **una sola** barra superior con las opciones correctas. La duplicidad desaparece en ambos viewports.

### Screenshots
- `/tmp/post-deploy-screenshots/market-desktop-post-deploy.png`
- `/tmp/post-deploy-screenshots/market-mobile-post-deploy.png`
- `/tmp/post-deploy-screenshots/log-desktop-post-deploy.png`
- `/tmp/post-deploy-screenshots/log-mobile-post-deploy.png`

---

## A8 -- Solo tab activa montada en desktop

**Estado: PASS**

### Evidencia DOM (test de signatures textuales en `document.body.innerText`)

Verificamos tras click a cada tab si signatures de **otras** tabs siguen en el DOM. En el deploy anterior todas las 5 screens estaban montadas, por lo que `innerText` contenia signatures de las 5 simultaneamente.

**Tab Home activa (desktop 1920x1080):**
- totalChars = 439
- Signatures de Trade (`MARKET ANALYSIS`, `TENDENCIA`, `SCORE DE ANALISIS`): ausentes
- Signatures de Market (`WATCHLIST`, `CRYPTO`, `PARES`, `SENALES`): ausentes
- Signatures de Log (`RENDIMIENTO`, `TRADES`, filtros color): ausentes
- Solo presentes: Dashboard, ACCOUNT, ENGINE STATUS, RISK MONITOR, DAILY ACTIVITY, ACTIVE POSITIONS.

**Tab Trade activa:**
- Signatures de Home (Dashboard, ACCOUNT, ENGINE STATUS, DAILY ACTIVITY, RISK MONITOR, ACTIVE POSITIONS): **TODAS ausentes**.
- Signatures de Market y Log: ausentes.
- Solo presentes: MARKET ANALYSIS, SCAN, SCORE DE ANALISIS, TENDENCIA, etc.

**Tab Log activa:**
```json
{
  "homeContentPresent": { "dashboardHeading": false, "accountSection": false, "engineStatus": false, "dailyActivity": false, "riskMonitor": false },
  "tradeContentPresent": { "marketAnalysis": false, "tendencia": false, "scoreAnalisis": false },
  "marketContentPresent": { "watchlistText": false, "pares": false, "senales": false, "btcusd": false },
  "logContentPresent": { "rendimiento": true, "trades": true, "allFilter": true, "blueFilter": true }
}
```

Conclusion: el deploy **desmonta** las tabs inactivas en desktop. Solo la activa tiene su contenido presente en el arbol DOM.

### Observacion: atributo `[data-screen]` no existe

La query sugerida `document.querySelectorAll('[data-screen]').length` devuelve 0 (ese atributo no se uso en la implementacion). La verificacion se hace por signatures textuales exclusivas de cada tab (mas robusto; reduce falsos positivos que podrian darse si dos tabs compartieran un componente).

### Comparacion vs baseline

- Baseline (Bug 3): DOM contenia los 5 stacks de screens a la vez -> 5x polling en `/account`, `/status`, `/risk-config`, `/risk-status`, `/watchlist`, etc.
- Post-deploy: solo 1 screen montada -> reduccion de polling estimada 60-80% (coincide con hipotesis del audit original).

### Screenshots
- `/tmp/post-deploy-screenshots/home-desktop-post-deploy.png` (solo Home)
- `/tmp/post-deploy-screenshots/trade-desktop-post-deploy.png` (solo Trade)
- `/tmp/post-deploy-screenshots/market-desktop-post-deploy.png` (solo Market)
- `/tmp/post-deploy-screenshots/log-desktop-post-deploy.png` (solo Log)
- `/tmp/post-deploy-screenshots/settings-desktop-post-deploy.png` (solo Settings)

---

## M13 -- Valor de fila TRADES en tarjeta RENDIMIENTO (30 DIAS)

**Estado: PASS**

### Evidencia DOM

```json
{
  "tradesRowValue": {
    "text": "0",
    "color": "rgb(29, 29, 31)",    // gris oscuro -- visible sobre fondo blanco
    "fontSize": "16px",
    "opacity": "1",
    "visibility": "visible",
    "display": "flex",
    "parentText": "TRADES0",
    "rect": { "w": 11, "h": 20 }
  }
}
```

Valor renderizado correctamente: `"0"` con color #1D1D1F (muy oscuro, alto contraste).

### Comparacion vs baseline

- Baseline (`log-desktop-viewport.jpeg` + `log-mobile.jpeg`): la fila TRADES quedaba blanca / sin valor mientras que WIN RATE `0.0%`, P&L TOTAL `$0.00`, AVG R:R `---` si renderizaban.
- Post-deploy: fila TRADES muestra `0` con el mismo estilo visual que el resto (texto oscuro, alineado a la derecha). Consistencia visual restablecida.

### Screenshots
- `/tmp/post-deploy-screenshots/log-desktop-post-deploy.png`
- `/tmp/post-deploy-screenshots/log-mobile-post-deploy.png`

---

## Errores de consola (nuevo deploy)

| Nivel | Conteo total sesion | Detalle |
|---|---|---|
| Error | 0 | ningun error tras navegacion, resize y cambio de tabs |
| Warning | 1 | `Animated: useNativeDriver is not supported ... Falling back to JS-based animation.` (Expo web benigno, pre-existente) |
| Info | 0 | -- |
| Debug | 0 | -- |

- El error transitorio `Failed to fetch` observado en el baseline mobile (Home) **no se reprodujo** en esta sesion.
- `net::ERR_ABORTED` tambien ausente.

## Network 4xx/5xx (nuevo deploy)

| Endpoint | Status | Ocurrencias |
|---|---|---|
| GET /api/v1/account | 200 | 5+ |
| GET /api/v1/status | 200 | 6+ |
| GET /api/v1/risk-config | 200 | 5+ |
| GET /api/v1/risk-status | 200 | 5+ |
| GET /api/v1/watchlist | 200 | 4 |
| GET /api/v1/analysis/EUR_GBP | 200 | 2 |
| GET /api/v1/history?limit=200 | 200 | 2 |
| GET /api/v1/history/stats?days=30 | 200 | 2 |
| GET /api/v1/mode | 200 | 2 |
| GET /api/v1/broker | 200 | 2 |
| GET /api/v1/strategies/config | 200 | 2 |
| GET /api/v1/alerts/config | 200 | 2 |
| GET /api/v1/scalping/status | 200 | 2 |
| GET /api/v1/funded/status | 200 | 2 |
| GET /api/v1/watchlist/categories | 200 | 2 |
| GET /api/v1/security/status | 200 | 2 |

**Total requests: 50. Errores 4xx/5xx: 0.**

## Observaciones adicionales

1. **API polling todavia duplicado**: aunque A8 desmonta tabs inactivas, el log de network muestra 5 `/api/v1/account` y 6 `/api/v1/status` en una sesion corta. Parece que Home dispara estos polls. Es un patron distinto al del baseline (no es 5x por 5 tabs montadas) -- probablemente hay un intervalo corto (5-10s) desde una sola tab. Recomendado revisar `staleTime` del store/query client. No es regresion.
2. **Expo Router + React Native Web**: la app usa componentes con classes `r-*` (react-native-web) y NO usa atributos `data-screen` ni `role="tabpanel"` en los paneles. Si se quiere mantener verificabilidad automatica (Playwright, tests), seria util agregar `testID="screen-home"` etc. a las screens y usar `react-native-web` `testID -> data-testid` para exponerlo al DOM.
3. **Mobile chips con overflow**: en viewport 390px los 7 chips (ALL..GREEN) suman ~500px de ancho. En mobile los ultimos 2 (BLACK, GREEN) quedan fuera de viewport y requieren scroll horizontal. Screenshot confirma que BLACK/GREEN estan en el DOM con las mismas dimensiones que los demas, por lo que el comportamiento es consistente. Considerar si seria mas ergonomico wrap a 2 filas o scroll indicator.

## Archivos generados

- Screenshots: `/tmp/post-deploy-screenshots/` (10 PNGs) + `/home/sergio/post-deploy-screenshots/` (mismo contenido).
- Este reporte: `/home/sergio/repos-seryi358/neontrade-ai/docs/superpowers/audits/2026-04-17-post-deploy-verify.md`.
