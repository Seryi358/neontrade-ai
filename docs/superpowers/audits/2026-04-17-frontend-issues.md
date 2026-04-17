# Frontend audit -- Atlas prod -- 2026-04-17

Target: `https://n8n-neontrade-ai.zb12wf.easypanel.host/`
Tool: Playwright MCP (Chromium 147, headless)
Viewports tested: 1920x1080 (desktop) y 390x844 (mobile)

## Resumen ejecutivo

- Tabs verificados: 5 (Home, Trade, Market, Log, Settings) x 2 viewports = 10 pantallas principales + 5 full-page desktop extra.
- Errores de consola: 0 errores recurrentes; 1 error transitorio `Failed to fetch` (ocurre durante resize/navegacion).
- Warnings de consola: 1 recurrente -- `Animated: useNativeDriver not supported` (propio de Expo web, no afecta UX pero ensucia consola).
- Errores de network (4xx/5xx): 0. Solo 2 `net::ERR_ABORTED` transitorios durante el cambio de viewport (no son del servidor, son cancelaciones del cliente).
- Bugs UI detectados: 4 (1 critico, 2 altos, 1 medio).
- `window.__ATLAS_API_KEY__` inyectada: **SI** (string base64 de 67 chars).
- Fonts: **SF Pro Display** cargadas correctamente (Regular 400, Medium 500, Semibold 600, Bold 700). Light (300) reportada como `unloaded` pero tiene fallback a `-apple-system, "Helvetica Neue", sans-serif`.
- Poll de API muy agresivo: se observan ~20 GETs repetidos a `account`, `status`, `risk-config`, `risk-status`, `watchlist`, `analysis/GBP_USD` durante la sesion corta de auditoria. Hay desperdicio de ancho de banda y bateria potencial en mobile.

## Bugs UI

### Bug 1: Chips de filtro de color en Log Tab renderizan como pildoras verticales gigantes
- **Severidad:** critica
- **Screenshots:**
  - `2026-04-17-frontend-screenshots/log-desktop-viewport.jpeg`
  - `2026-04-17-frontend-screenshots/log-mobile.jpeg`
  - `2026-04-17-frontend-screenshots/log-desktop.png`
- **Descripcion:** En la tab "Log" (Historial), los filtros de color (ALL, BLUE, RED, PINK, WHITE, BLACK, GREEN) se renderizan como pildoras verticales altisimas (~180-200px de alto x ~30-50px de ancho) en lugar de chips horizontales redondeados normales. El texto queda girado / comprimido y el control es practicamente inutilizable. Afecta desktop y mobile.
- **Sugerencia fix:** Revisar el componente de filtros en `app/(tabs)/Log*` -- probablemente un `flexDirection: "row"` que quedo en `column`, o `height` sin limite en un contenedor. Puede ser estilo que aplica un `aspectRatio` invertido o un `flex: 1` en items dentro de un contenedor vertical. Verificar estilos de `FilterChip` / `CategoryPill` en Log screen.

### Bug 2: Barra de sub-tabs duplicada en Market y Log (toda la app)
- **Severidad:** alta
- **Screenshots:**
  - `2026-04-17-frontend-screenshots/market-desktop-viewport.jpeg` (Watchlist/Crypto x2)
  - `2026-04-17-frontend-screenshots/market-mobile.jpeg`
  - `2026-04-17-frontend-screenshots/log-desktop-viewport.jpeg` (History/Journal/Exam arriba + HISTORY/JOURNAL abajo)
  - `2026-04-17-frontend-screenshots/log-mobile.jpeg`
  - `2026-04-17-frontend-screenshots/trade-desktop-viewport.jpeg` (Scan/Chart/Manual se ve solo una vez pero el patron es el mismo)
- **Descripcion:** En Market, Log (y parcialmente Trade), aparecen dos juegos de tabs: una barra superior subrayada ("Watchlist | Crypto", "History | Journal | Exam") Y una segunda pill horizontal debajo ("WATCHLIST / CRYPTO", "HISTORY / JOURNAL"). Peor aun: las dos barras no siempre contienen las mismas opciones (Log superior tiene Exam, la pill inferior no). Confunde al usuario sobre cual controla la vista.
- **Sugerencia fix:** Revisar la arquitectura de navegacion. Expo Router probablemente agrega un header con tabs automaticos (top) ademas de un `MaterialTopTabNavigator` o pills custom que montaron los desarrolladores. Eliminar una de las dos capas. Sospecho que los layouts `app/(tabs)/Market/_layout.tsx` y `app/(tabs)/Log/_layout.tsx` definen sub-routes y el componente pantalla a su vez renderiza su propio pill-switch. Consolidar en una sola fuente de verdad.

### Bug 3: En desktop, los 5 tab-screens se renderizan simultaneamente en el DOM
- **Severidad:** alta
- **Screenshots:**
  - `2026-04-17-frontend-screenshots/home-desktop.png` (fullPage -- muestra todo stack)
  - `2026-04-17-frontend-screenshots/trade-desktop.png`
  - `2026-04-17-frontend-screenshots/market-desktop.png`
  - `2026-04-17-frontend-screenshots/log-desktop.png`
  - `2026-04-17-frontend-screenshots/settings-desktop.png`
- **Descripcion:** Al inspeccionar el DOM en viewport 1920x1080, todos los contenedores de screen (Home, Trade, Market, Log, Settings) estan montados y presentes al mismo tiempo en el arbol del body. Aunque el click en tabs cambia el `document.title` correctamente y hace scroll al panel activo, los otros 4 siguen renderizados (con fetches activos). Esto multiplica el trabajo de polling (cada screen dispara su propio refresh) y explica el ruido de requests observado (watchlist, analysis, etc. corriendo aunque no estes en esa tab). En mobile el layout parece correcto (solo 1 screen a la vez).
- **Sugerencia fix:** Revisar el `TabNavigator` o layout root para desktop. Probablemente falta `display: none` o `unmountOnBlur: true` en las screens inactivas, o el layout media-query desktop decidio mostrar todo en flex-row. Confirmar con `@react-navigation/*` config. Ver tambien `app/(tabs)/_layout.tsx` / `app/_layout.tsx`.

### Bug 4: Campo "TRADES" en tarjeta RENDIMIENTO (30 DIAS) sin valor numerico
- **Severidad:** media
- **Screenshots:**
  - `2026-04-17-frontend-screenshots/log-desktop-viewport.jpeg`
  - `2026-04-17-frontend-screenshots/log-mobile.jpeg`
- **Descripcion:** Dentro de la tarjeta RENDIMIENTO (30 DIAS) en Log, la fila "TRADES" no muestra valor (queda blanco). Las filas WIN RATE (0.0%), P&L TOTAL ($0.00) y AVG R:R (---) si renderizan valor. Inconsistencia visual.
- **Sugerencia fix:** Revisar componente `StatsCard` o equivalente en Log. Probablemente el campo `trades` llega como `undefined` / `null` en vez de `0`. Fallback a "0" o a "---" como el resto.

## Observaciones adicionales (no bug critico, pero vale revisar)

- **Polling agresivo**: cada ~10-15s se dispara `/api/v1/account`, `/status`, `/risk-config`, `/risk-status`, `/watchlist`, `/analysis/GBP_USD`. Con 5 screens montadas simultaneamente (ver Bug 3), cada screen corre su ciclo -> 5x polls. Consolidar en un store compartido (Zustand/Redux/React Query con `staleTime`) reduciria requests entre 60-80%.
- **Warning de Animated/useNativeDriver**: esperado en Expo web, pero ensucia la consola y aparece dos veces. Se puede silenciar con `LogBox.ignoreLogs([...])` o idealmente reemplazar las animaciones con `react-native-reanimated` v3 que si funciona bien en web.
- **Desktop subutilizado**: El layout desktop muestra cada tab a full-width de 1920px, con contenido denso a la izquierda y mucho whitespace. El home-desktop.png evidencia margenes enormes alrededor. Podria beneficiar de un max-width de 1280-1440px o un layout tipo dashboard con multi-columna real (no stack vertical).
- **API KEY visible en Settings**: La seccion System Info muestra `nt_FGjJ0...rjXI` (truncado OK) y el backend URL completo. Esto esta bien porque es vista de admin, pero confirmar que el boton "Eliminar Key" pide confirmacion.

## Errores de consola (acumulado durante toda la sesion)

| Tab | Viewport | Errores | Warnings | Ejemplos |
|---|---|---|---|---|
| Home | Desktop | 0 | 1 | `Animated: useNativeDriver is not supported` |
| Trade | Desktop | 0 | 1 | (mismo warning, propagated) |
| Market | Desktop | 0 | 1 | (mismo) |
| Log | Desktop | 0 | 1 | (mismo) |
| Settings | Desktop | 0 | 1 | (mismo) |
| Home | Mobile | 1 | 2 | `Failed to fetch` (transient al resize/nav) |
| Trade | Mobile | 0 | 1 | (mismo warning Animated) |
| Market | Mobile | 0 | 1 | (mismo) |
| Log | Mobile | 0 | 1 | (mismo) |
| Settings | Mobile | 0 | 1 | (mismo) |

Resumen: solo 1 error real en toda la auditoria (`Failed to fetch`), y es transitorio durante el cambio de viewport -- no representa bug de produccion.

## Errores de network

| Endpoint | Status | Tab / contexto |
|---|---|---|
| `/api/v1/account` | `net::ERR_ABORTED` | Ocurre 1 vez justo despues de `browser_resize` a mobile -- request abortada por el cliente, no error del server. |
| `/api/v1/risk-status` | `net::ERR_ABORTED` | Mismo contexto (resize). |

Todos los demas requests (>100 observados) -- 200 OK. El backend responde correctamente y consistentemente.

## Verificaciones OK

- `window.__ATLAS_API_KEY__` esta inyectada correctamente (67 chars, base64-like).
- Las fonts SF Pro Display cargan (Regular/Medium/Semibold/Bold). Fallback a `-apple-system` disponible para el peso Light.
- Todos los endpoints `/api/v1/*` responden 200: account, status, risk-config, risk-status, watchlist, analysis, history, strategies, alerts, scalping, funded, broker, mode, categories, security.
- Navegacion entre tabs funciona (click -> document.title cambia -> viewport muestra contenido correcto).
- Presets en Settings son clickeables (TRADINGLAB RECOMMENDED, CONSERVATIVE).
- Color contrast: no se detectaron casos de texto blanco-sobre-blanco ni combinaciones ilegibles. La paleta es correcta (azul #1E88E5 links, verde #00C853 para positivo, rojo para negativo).
- Bottom tab bar renderiza correctamente en desktop y mobile con 5 items (Home, Trade, Market, Log, Settings).
- Settings refleja estado real (MANUAL mode, API KEY AUTENTICADA, Broker=capital CONECTADO, Version Atlas v3.0).
- Estado vacio de Log/Positions muestra mensajes apropiados ("No active positions", "No hay historial de operaciones").
- Score gauge en Trade Scan se renderiza (75/100 con color amarillo) correctamente.
