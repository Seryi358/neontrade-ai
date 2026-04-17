# Audit mentoría TradingLab vs Atlas backend — 2026-04-17

## Resumen ejecutivo

- **Total discrepancias detectadas:** 24
- **Críticas:** 6 | **Altas:** 8 | **Medias:** 7 | **Bajas:** 3
- **Top 3 críticas:**
  1. **BLUE TP1 = EMA 4H** en Atlas (`backend/strategies/base.py:1863-1869`) vs mentoría Trading Plan PDF pg.6: "Pondré **siempre** un Take Profit 1 que significará llevar el precio hasta el **máximo o mínimo anterior**" — y EMA 4H es el TP **máximo** (TP_max), no TP1.
  2. **Trailing EMAs post-BE son EMA M5 50** en Atlas (`backend/core/position_manager.py:110`) vs Trading Plan PDF pg.5: "A partir de aquí usaré siempre las **dos medias móviles más cortas** en cada estilo de trading para gestionar mis posiciones (**EMA2m y EMA5m** para el Day trading)". El default Atlas es EMA 50 en M5, no EMAs 2/5 en M5.
  3. **EMA 8 Weekly filter como gate para TODAS las estrategias y activos** (`backend/strategies/base.py:405-419`, usado en BLUE, RED, PINK, WHITE, BLACK, GREEN) vs mentoría: EMA 8 semanal aparece **solo en Esp. Criptomonedas — Indicadores cripto**. En Trading Mastery no existe. Bloquea forex setups válidos por una regla cripto.

## Discrepancias

### Discrepancia 1: BLUE TP1 ≠ "máximo/mínimo anterior"
- **Tema:** Estrategias · TP
- **Mentoría dice:** Trading Plan PDF pg.6 ("Targets"): "Pondré **siempre** un Take Profit 1 que significará llevar el precio hasta el **máximo o mínimo anterior**. En función de algunas circunstancias, situaré un Take Profit máximo. **BLUE: EMA4H** / RED (con HTF a favor): Extensión de Fibonacci de 1 / WHITE: máximo/mínimo del impulso de 4H". Es decir, EMA 4H es TP_max para BLUE, no TP1.
- **App hace:** `backend/strategies/base.py:1844-1931` `BlueStrategy.get_tp_levels` asigna `tp1 = EMA 4H 50` (línea 1864-1869) y `tp_max = EMA 4H` para BLUE B/C (línea 1913-1919) o Fib 1.272/1.618 para BLUE A.
- **Severidad:** crítica
- **Archivos afectados:** `backend/strategies/base.py`
- **Sugerencia de fix:** Para BLUE invertir la asignación: `tp1 = swing high/low más cercano` (máximo/mínimo anterior), `tp_max = EMA 4H 50` (o Fib 1.272/1.618 para BLUE A). Se elimina la auto-contradicción y se alinea con la regla explícita del PDF.

### Discrepancia 2: Trailing post-BE usa EMA 50 (no EMA 2 + EMA 5)
- **Tema:** CP management · BE trailing
- **Mentoría dice:** Trading Plan PDF pg.5 ("Proceso de gestión"): "A partir de aquí usaré **siempre las dos medias móviles más cortas** en cada estilo de trading para gestionar mis posiciones (**EMA2m y EMA5m** para el Day trading)". También en la mentoría oral, después del 1% de beneficio y de romper el máximo anterior, se gestiona "con la media móvil de 50 de cinco minutos" en CP; pero el PDF (fuente autoritativa) es más específico y dice EMA 2 y EMA 5.
- **App hace:** `backend/core/position_manager.py:95-118` `_EMA_TIMEFRAME_GRID` mapea `(CP, DAY_TRADING) -> "EMA_M5_50"` (EMA 50 en M5) como trailing post-BE. Las EMAs ultra-cortas (`ema_fast=2`, `ema_slow=5`) existen en `config.py:238-239` pero no se usan para trailing — sólo para emergency exit en `_handle_aggressive_phase` (línea 911-912).
- **Severidad:** crítica
- **Archivos afectados:** `backend/core/position_manager.py`, `backend/config.py`
- **Sugerencia de fix:** Añadir un nuevo estilo/mapa que use EMA 2 y EMA 5 en M5 como par de trailing (BE trailing sigue EMA 5, emergency exit si rompe EMA 2). Para Day trading en modo CP, cambiar el mapa a `"EMA_M5_5"` como primary trail y `"EMA_M5_2"` para aggressive. Alternativa: mantener EMA 50 como "CP conservador" pero crear estilo `cp_alex` que refleje las EMAs cortas del Trading Plan PDF.

### Discrepancia 3: EMA 8 Weekly bloquea forex/indices como filtro global
- **Tema:** Strategy detection · HTF filter
- **Mentoría dice:** EMA 8 semanal se enseña **solo en `Esp. Criptomonedas/01_Contenido/08_Indicadores cripto y su función/03_EMA 8 semanal`**. En Trading Mastery no hay mención de EMA 8 semanal como filtro para BLUE/RED/PINK/WHITE/BLACK. La mentoría base usa EMA 50 D y SMA 200 D.
- **App hace:** `backend/strategies/base.py:405-419` `_check_weekly_ema8_filter` fail-safe=False; invocado como penalización en BLUE (`base.py:1579-1587`), como hard block en GREEN (`base.py:4216-4217`), y en Pink/White/Black similares. Si `ema_w8` no existe → bloquea/penaliza; si existe → exige precio a favor.
- **Severidad:** crítica
- **Archivos afectados:** `backend/strategies/base.py` (todas las estrategias), `backend/core/market_analyzer.py`
- **Sugerencia de fix:** Restringir `_check_weekly_ema8_filter` exclusivamente a instrumentos crypto (GREEN crypto) mediante guard `if _is_crypto_instrument(analysis.instrument): ...`. Remover la llamada de BLUE/RED/PINK/WHITE/BLACK para forex/indices/commodities. En su lugar, para forex, reforzar EMA 50 D como trend filter que ya existe en market_analyzer.

### Discrepancia 4: RED TP_max usa Fib 1.272/1.618 pero Trading Plan dice "Extensión Fibonacci de 1"
- **Tema:** Estrategias · TP_max
- **Mentoría dice:** Trading Plan PDF pg.6: "RED (con HTF a favor): Extensión de Fibonacci de **1**". Es decir, la extensión 1.0 (100%), que proyecta la longitud del impulso desde el inicio del pullback. NO la 1.272 ni la 1.618.
- **App hace:** `backend/strategies/base.py:2399-2478` `RedStrategy.get_tp_levels` para Wave 3 usa fib_1618 primero, luego fib_1272 (línea 2419-2443), y sólo cae a fib_100 como "final fallback" (línea 2473). La mentoría invierte el orden: la **extensión 1.0** debería ser el default para Wave 3 con HTF a favor; 1.618 es más agresivo (sólo Wave 3 extendida).
- **Severidad:** alta
- **Archivos afectados:** `backend/strategies/base.py`
- **Sugerencia de fix:** Para RED con HTF a favor y wave_count="3", priorizar `ext_bull_1.0` / `ext_bear_1.0` como TP_max principal. Dejar 1.272 y 1.618 sólo como escaladas opcionales cuando se activa extensión de onda 3 justificada por Fib 1.0 ya alcanzado.

### Discrepancia 5: max_total_risk = 5% (mentoría = 7%)
- **Tema:** Risk · Max simultáneo
- **Mentoría dice:** Trading Plan PDF pg.3 ("Gestión Monetaria"): "Máximo riesgo total del **7%** a la vez".
- **App hace:** `backend/config.py:88` `max_total_risk: float = 0.05` (5%). El perfil `tradinglab_recommended` sí usa 7% (línea 691), pero el default no lo aplica a menos que el usuario invoque el perfil. En mentoría es el valor de referencia único; no es conservador del plan.
- **Severidad:** alta
- **Archivos afectados:** `backend/config.py`
- **Sugerencia de fix:** Cambiar default a `0.07`. Si se quiere un perfil conservador específico para $190 capital, crear profile "capital_pequeño" separado en lugar de mutar el default. Documentar el razonamiento del cap.

### Discrepancia 6: risk_swing = 1% (mentoría = 3%)
- **Tema:** Risk · Swing
- **Mentoría dice:** Trading Plan PDF pg.3: "Riesgos: 1% en Day trading / **3% en Swing trading** / 0.50% en Scalping".
- **App hace:** `backend/config.py:87` `risk_swing: float = 0.01`. Comentario reconoce la discrepancia ("3% for swing, but capped to 1% for $190 capital safety"). El perfil `tradinglab_recommended` también lo fija en 1% con nota "NON-NEGOTIABLE" que contradice el PDF.
- **Severidad:** alta
- **Archivos afectados:** `backend/config.py`
- **Sugerencia de fix:** Restaurar default a `0.03`. Si el objetivo es proteger cuentas pequeñas, añadir lógica en `get_risk_for_style` que reduzca automáticamente a 1% cuando balance < $500. El comentario "NON-NEGOTIABLE" en `tradinglab_recommended` es falso y engañoso — borrarlo. Alternativamente, dejar default en 1% pero eliminar comentario que afirma que viene de la mentoría.

### Discrepancia 7: BE trigger = "risk_distance" pero Trading Plan dice "mitad del beneficio hasta TP1"
- **Tema:** CP management · BE
- **Mentoría dice:** Trading Plan PDF pg.5: "**Cuando estemos por la mitad del beneficio hasta el Take Profit 1, pondré el BE**". Es decir, BE trigger = 50% de la distancia a TP1, NO 1x risk distance. El método "cuando tengo un 1% de ganancia" viene de la mentoría oral (Alex hablando) pero contradice explícitamente el documento `TradingPlan_2024.pdf` que es autoritativo.
- **App hace:** `backend/config.py:141` `be_trigger_method: str = "risk_distance"` (Alex oral). El código en `position_manager.py:632-637` soporta ambos métodos pero el default es el de oral (risk distance).
- **Severidad:** alta
- **Archivos afectados:** `backend/config.py`, `backend/core/position_manager.py`
- **Sugerencia de fix:** Cambiar default a `"pct_to_tp1"` con `move_sl_to_be_pct_to_tp1: 0.50` para alinearse con el Trading Plan PDF. Mantener `risk_distance` como opción alternativa (Alex oral). Para un R:R 2:1, ambos métodos coinciden; para R:R 1:1 (TP1 a máximo anterior), risk_distance coincide con "llegar a TP1" y nunca dispararía — el método PDF es más robusto.

### Discrepancia 8: Trailing no espera ruptura del máximo anterior
- **Tema:** CP management · Trailing activation
- **Mentoría dice:** Trading Mastery — Short Term (`04_Avanzado/02_Manejo de la posición/04_Short Term/transcripcion.txt`): "Ahí tenemos ya el 1%, break-even, y aparte de eso, tenemos el 1% de rentabilidad-riesgo. El 1%, break-even, y a partir de aquí vamos a esperar y empezaremos a gestionar con la media móvil de 50, de cinco minutos. **Hasta que no se rompa, evidentemente, este máximo anterior, no vamos a utilizarla**". Es decir: BE → esperar ruptura del máximo anterior (swing high para BUY, swing low para SELL) → entonces activar trailing con EMA 5m.
- **App hace:** `backend/core/position_manager.py:656-705` `_handle_be_phase` activa trailing en cuanto la EMA es "favorable" (debajo del precio para BUY, encima para SELL). No requiere ruptura del swing high/low previo — que es el gate explícito de la mentoría. Consecuencia: trailing se activa demasiado pronto y SLs pueden saltar en dientes de sierra antes de la confirmación de estructura.
- **Severidad:** alta
- **Archivos afectados:** `backend/core/position_manager.py`
- **Sugerencia de fix:** Añadir un paso intermedio entre BE y TRAILING_TO_TP1: monitorizar si `current_price > last_swing_high_before_entry` (BUY) o `< last_swing_low_before_entry` (SELL); sólo al confirmar ruptura, pasar a TRAILING. Los swing_highs/lows ya están disponibles en `_latest_swings`.

### Discrepancia 9: 50% risk reduction está cableado a 50% de BE threshold (debería ser "ruptura de estructura")
- **Tema:** CP management · Pre-BE risk cut
- **Mentoría dice:** Trading Plan PDF pg.5: "Pondré el SL por encima o debajo del máximo o mínimo anterior (si es posible), **en el momento en el que el precio haya empezado a ir a mi favor**". Mentoría oral y el propio comentario en el código dicen "al salir de la estructura/patrón". Es un trigger estructural, no un porcentaje fijo.
- **App hace:** `backend/core/position_manager.py:608-629` dispara "50% risk reduction" cuando `current_profit >= risk_distance * 0.5`. El comentario reconoce: "Mentorship says this should trigger when 'price exits the structure' (structural event). Current implementation uses 50% of BE distance as a proxy."
- **Severidad:** media
- **Archivos afectados:** `backend/core/position_manager.py`
- **Sugerencia de fix:** Usar `_handle_initial_phase` (`_latest_swings`) para detectar cuando el precio cierra por encima/debajo del swing reciente (ruptura de estructura) y disparar ahí. El 50% de profit como proxy infra-dispara (trigger temprano en pullbacks amplios) o sobre-dispara (nunca llega si estructura se rompe antes). Atlas ya tiene la infra (`_latest_swings` en position_manager).

### Discrepancia 10: Setup/HTF filter con EMA 8 weekly también bloquea BLACK
- **Tema:** Strategy detection · BLACK filter
- **Mentoría dice:** BLACK es explícitamente **contratendencial** — se ejecuta contra la tendencia HTF. El System Prompt de openai_analyzer.py lo reconoce: "Never trade against the higher timeframe trend **unless running a BLACK (counter-trend) strategy** with RSI divergence confirmation". Un filtro EMA 8 semanal que exija precio "a favor" hace imposible detectar BLACK.
- **App hace:** BLACK usa `_check_weekly_ema8_filter` (ver Disc. 3). Esto convierte BLACK en inoperable porque por definición BLACK entra contra la tendencia semanal.
- **Severidad:** alta
- **Archivos afectados:** `backend/strategies/base.py` (BlackStrategy)
- **Sugerencia de fix:** Remover el weekly EMA 8 filter de BLACK por completo, o invertir el sentido (BLACK requiere precio **contra** EMA 8 + RSI divergence). Esta es una de las razones de la discrepancia #3.

### Discrepancia 11: GREEN weekly EMA 8 block para forex/indices
- **Tema:** Strategy detection · GREEN filter
- **Mentoría dice:** La mentoría cripto usa EMA 8 weekly; pero GREEN también se enseña para forex/indices/metales en Trading Mastery (Clase 17-18 Estrategias) sin ese filtro. GREEN en forex Weekly trend se mide con EMA 50 D / price action, no con EMA 8 W.
- **App hace:** `backend/strategies/base.py:4216-4217` `GreenStrategy.check_ltf_entry` hard-blocks con `_check_weekly_ema8_filter` para **todos** los instrumentos (forex incluido).
- **Severidad:** alta
- **Archivos afectados:** `backend/strategies/base.py`
- **Sugerencia de fix:** Sólo aplicar `_check_weekly_ema8_filter` si `_is_crypto_instrument(analysis.instrument)`. Para forex, usar el filtro de tendencia semanal basado en EMA 50 D + estructura HH/HL ya disponible en analysis.

### Discrepancia 12: WHITE TP_max no usa "máximo/mínimo del impulso 4H"
- **Tema:** Estrategias · TP_max
- **Mentoría dice:** Trading Plan PDF pg.6: "WHITE: **máximo/mínimo del impulso de 4H**" como TP_max.
- **App hace:** Revisión rápida de `WhiteStrategy.get_tp_levels` (`base.py:3351+`) muestra lógica basada en swing highs/lows y Fib extensions pero no implementa explícitamente "máximo/mínimo del impulso de 4H" (el high/low del impulso alcista/bajista más reciente en H4). Esto requiere identificar el swing impulse en H4 específicamente.
- **Severidad:** media
- **Archivos afectados:** `backend/strategies/base.py` (WhiteStrategy)
- **Sugerencia de fix:** Añadir detección de "impulso H4" (swing más reciente en H4 con velocidad >= X ATR) y usar su máximo/mínimo como TP_max en WHITE. Fallback al high/low de los últimos N candles H4.

### Discrepancia 13: BLACK min R:R en config = 2.0, mentoría = ~2:1/3:1
- **Tema:** Estrategias · R:R
- **Mentoría dice:** Mentoría `03_Estrategias/NOTAS_COMPLETAS.md` Clase 14-15 (Black): R:R mínimo alrededor de 2:1 pero "incluso hasta 3:1" dependiendo del contexto contratendencia.
- **App hace:** `backend/config.py:112` `min_rr_black: float = 2.0`. Consistente con el mínimo, pero no hay lógica que exija 3:1 cuando HTF está claramente contra la entrada BLACK.
- **Severidad:** baja
- **Archivos afectados:** `backend/config.py`, `backend/strategies/base.py` (BlackStrategy)
- **Sugerencia de fix:** Opcional: incrementar `min_rr_black` a 2.5 como defecto más conservador, o añadir lógica condicional que exija 3:1 cuando `analysis.htf_trend` contradiga la dirección del setup.

### Discrepancia 14: Scalping cooldown y max_trades_per_day no diferenciados
- **Tema:** Psicología · Anti-overtrading
- **Mentoría dice:** El Workshop de Scalping enfatiza alta frecuencia de trades (menos `max_trades_per_day` no aplica) y el cooldown/limit debe ajustarse a la naturaleza scalping (más trades por día, cooldowns más cortos tras pérdidas).
- **App hace:** `backend/config.py:149-151` `max_trades_per_day=3` y `cooldown_minutes=120` están fijados para day trading, pero también se aplican en scalping (mismo código en `trading_engine.py:1901-1918`). Para scalping, 3 trades/día es excesivamente limitante.
- **Severidad:** media
- **Archivos afectados:** `backend/config.py`, `backend/core/trading_engine.py`
- **Sugerencia de fix:** Añadir campos `max_trades_per_day_scalping: int = 10` y `cooldown_minutes_scalping: int = 30` y usar el valor apropiado según `settings.trading_style` en `trading_engine.py`.

### Discrepancia 15: Scalping BLUE mode "clean_only" necesita confidence threshold claro
- **Tema:** Estrategias · Scalping BLUE
- **Mentoría dice:** Workshop de Scalping Clase 4: "se formarán tesituras en las que haya una BLUE limpia. Sí, obvio. Ese es un tercer punto en el que puedes entrar y en el que vamos a recomendar más adelante, pero es mucho menos habitual." No define un threshold numérico explícito.
- **App hace:** `backend/config.py:256` `scalping_blue_mode: str = "clean_only"`. El comentario dice "80%+ confidence only" pero el código en `scalping_engine.py:421-431` no expone explícitamente el threshold.
- **Severidad:** baja
- **Archivos afectados:** `backend/core/scalping_engine.py`
- **Sugerencia de fix:** Añadir un campo de config `scalping_blue_clean_threshold: float = 0.80` y aplicarlo en `scalping_engine.py:421-431` con comentario cross-reference.

### Discrepancia 16: Crypto reentry risk progresión hardcodeada 0.5/0.25 no refleja "cada uno pone sus normas"
- **Tema:** Risk · Reentries
- **Mentoría dice:** `Esp. Criptomonedas/09_Estrategia de trading/07_Identificación de reentradas efectivas`: Alex usa 0.5% y 0.25% como ejemplos pero explícitamente dice "Cada uno pone sus normas". El punto es que sean **decrecientes** y haya un cap.
- **App hace:** `backend/config.py:158-160` `reentry_risk_1=0.50`, `reentry_risk_2=0.25`, `reentry_risk_3=0.25`. Funcional pero hardcoded, y el comentario sí reconoce que son "DEFAULTS, not hard rules".
- **Severidad:** baja
- **Archivos afectados:** ninguno (ya implementado como default configurable)
- **Sugerencia de fix:** Ninguna — implementación correcta. Sólo confirmar que la UI expone estos parámetros.

### Discrepancia 17: Avoid_news_minutes scalping 45/30 no refleja "olvídate completamente"
- **Tema:** Calendar · Scalping news
- **Mentoría dice:** Mentoría Clase 3 Cómo afecta noticias: "**Scalping, ni hablar de noticias**" — bloqueo total durante todo el período volátil. Las notas del código dicen 60/60 original pero reducido a 45/30 "as compromise".
- **App hace:** `backend/core/news_filter.py:48` `TradingStyle.SCALPING: (45, 30)`. Reducir el buffer es una decisión de negocio contra la mentoría explícita.
- **Severidad:** media
- **Archivos afectados:** `backend/core/news_filter.py`
- **Sugerencia de fix:** Restaurar a `(60, 60)` que es el valor mentoría literal. Si 60 es demasiado restrictivo en práctica, exponer como setting configurable en config.py con comment cross-referencing a mentoría.

### Discrepancia 18: DAY_TRADING avoid_news_after=15min no match mentoría
- **Tema:** Calendar · Day Trading news
- **Mentoría dice:** Clase 3 (Cómo afecta): "**day trading no vamos a ejecutar, pero podemos simplemente poner break evens y esperar**". No da un buffer temporal específico post-noticia pero implica "durante la volatilidad" — que suele ser 30-60 min post-release.
- **App hace:** `backend/core/news_filter.py:50` `TradingStyle.DAY_TRADING: (30, 15)`. 15 min post noticia es probablemente insuficiente para NFP, CPI, FOMC que generan volatilidad 30-60 min.
- **Severidad:** media
- **Archivos afectados:** `backend/core/news_filter.py`
- **Sugerencia de fix:** Cambiar a `(30, 30)` para dar margen post-release. Mentoría prioriza "no operar durante la volatilidad" más que optimizar ejecuciones tempranas.

### Discrepancia 19: Timeframes config lista M2 pero Capital.com no lo soporta nativamente
- **Tema:** Broker · Timeframes
- **Mentoría dice:** Day Trading CPA usa gráfico de 2 minutos.
- **App hace:** `backend/broker/capital_client.py:33-35` `"M2": "MINUTE"` — mapea M2 a MINUTE (M1) y nota que "market_analyzer derives M2 from M1". El código sí lo deriva, pero esto significa que las EMAs M2 en posición_manager (`EMA_M2_50` para CPA day trading) son en realidad calculadas sobre datos M1 muestreados. Funcional pero la fidelidad es imperfecta.
- **Severidad:** media
- **Archivos afectados:** `backend/broker/capital_client.py`, `backend/core/market_analyzer.py`
- **Sugerencia de fix:** Documentar explícitamente en `position_manager.py:116` ("CPA DAY_TRADING → EMA_M2_50") que M2 se deriva de M1, y que la fidelidad del trailing CPA es aproximada. Considerar usar directamente M1 como CPA para day trading y M5 como CP, eliminando la derivación M2.

### Discrepancia 20: sma_daily=200 aparece en config pero no hay filtro activo basado en él
- **Tema:** Strategy detection · Trend filter
- **Mentoría dice:** SMA 200 D es referencia de tendencia largoplacista — útil como filtro soft.
- **App hace:** `backend/config.py:244` `sma_daily: int = 200` está definido pero el valor se calcula en market_analyzer y no se usa explícitamente como gate en las estrategias.
- **Severidad:** baja
- **Archivos afectados:** `backend/strategies/base.py`
- **Sugerencia de fix:** Añadir en cada estrategia un bonus/penalización basado en posición del precio vs SMA 200 D (como confluence score, no hard block).

### Discrepancia 21: Partial profits toggle pero código default False (correcto) — pero perfil "conservative" lo fija False pese a que mentoría admite parciales en CPA
- **Tema:** CPA · Partials
- **Mentoría dice:** Alex NO toma parciales en su operativa personal (Trading Plan PDF pg.8: "No tomaré ningún tipo de profit parcial"), pero la mentoría (Clase CPA + Short Term Agresivo) explícitamente dice que CPA puede cerrar parcial 25/50/75/100% en zonas clave.
- **App hace:** `backend/config.py:161-165` `partial_taking=False`, `allow_partial_profits=False`. El perfil `tradinglab_recommended` refleja correctamente a Alex. Pero CPA en `position_manager.py` no implementa opción de partial incluso cuando CPA se dispara (ver `_handle_trailing_phase` partial section condicionada a `allow_partial_profits=True`).
- **Severidad:** baja
- **Archivos afectados:** `backend/core/position_manager.py`
- **Sugerencia de fix:** Cuando CPA se activa en zona clave (via `set_cpa_trigger`), permitir partial close automático independiente de `allow_partial_profits`. Esto refleja la recomendación mentoría "puedes cerrar 50% en máximo anterior con CPA".

### Discrepancia 22: Cooldown se reinicia al ganar un trade pero mentoría dice "2 pérdidas consecutivas → esperar"
- **Tema:** Psicología · Cooldown
- **Mentoría dice:** Psicología Avanzada: después de N pérdidas consecutivas, pausa. No especifica reset instantáneo tras una ganancia.
- **App hace:** `backend/core/trading_engine.py:1234-1237` incrementa `_consecutive_losses_today` en cada pérdida pero lo resetea a 0 en cualquier ganancia. Funcional pero puede llevar a "ping-pong" trade-to-trade.
- **Severidad:** baja
- **Archivos afectados:** `backend/core/trading_engine.py`
- **Sugerencia de fix:** Ninguna crítica. La implementación actual es razonable.

### Discrepancia 23: close_before_friday_hour=20 cierra posiciones próximas a SL/TP; mentoría dice cerrar TODOS los trades abiertos
- **Tema:** Weekend · Close
- **Mentoría dice:** Trading Plan PDF pg.10 ("Gestión General"): "Cerraré **todos los trades** que estén cerca de Stop Loss o Take Profit antes de que cierre el mercado el Viernes". Trading Lab también enseña que posiciones lejanas de SL/TP en general se pueden mantener si hay setup fundamental claro pero el PDF dice "todos los cerca de SL/TP".
- **App hace:** `backend/core/trading_engine.py:983-1110` `_handle_friday_close` implementa correctamente: cierra solo los cerca de SL (<30% distance) y TP (<30%), mantiene otros. Coincide con mentoría.
- **Severidad:** ninguna (implementación correcta)
- **Archivos afectados:** ninguno
- **Sugerencia de fix:** Ninguna. Mantener como está.

### Discrepancia 24: Scalping engine no impone R:R min ~1.5 para Workshop (más atractivo)
- **Tema:** Scalping · R:R
- **Mentoría dice:** Workshop de Scalping: R:R asequibles del orden 5:1, 7:1, 10:1 gracias a SL apretado en Fib 0.618. No hay R:R mínimo explícito, pero las tablas del taller muestran targets de x5+ como típicos.
- **App hace:** `backend/core/scalping_engine.py` hereda `min_rr_ratio` de config (default 1.5). No sobrescribe para scalping.
- **Severidad:** baja
- **Archivos afectados:** `backend/config.py`, `backend/core/scalping_engine.py`
- **Sugerencia de fix:** Añadir setting `min_rr_scalping: float = 3.0` y usarlo en scalping_engine.py. R:R 1.5 en scalping es subóptimo — el valor agregado de scalping es precisamente el R:R alto por SL ajustado.

---

## Addendum — Items previos del AUDIT_REPORT_2026-04-15 confirmados OK

Los siguientes items del audit anterior están ahora correctamente implementados:

- Regla del 1% (`risk_day_trading=0.01`) ✓
- Correlated risk 0.75% fijo (`correlated_risk_pct=0.0075`) ✓
- Drawdown fixed_levels 4.12/6.18/8.23% → 0.75/0.50/0.25% (valores PDF exactos) ✓
- BLUE requires setup EMA broken + confirm EMA NOT broken ✓
- RED requires BOTH H1 and H4 EMA 50 broken ✓
- GREEN requires diagonal non-negotiable ✓
- Crypto GREEN uses EMA 50 W trailing (`trailing_tp_only`) ✓
- Capital.com auth + session management ✓
- Trading hours London + NY (7-21 UTC EDT) con DST offset ✓
- Friday close antes de 20:00 UTC ✓
- Max 3 trades/día + cooldown 120min tras 2 pérdidas (day trading) ✓
- Risk-aware position sizing con minimum deal size ✓
- BLUE A classifier con detección doble suelo/techo ✓
- Scalping 0.618 Fib SL enforcement ✓
- Funded account presets (FTMO/5RF/BitFunded) ✓

---

## Notas finales

- **Fuente autoritativa en conflicto**: Trading Plan PDF 2024 vs mentoría oral. El PDF es el documento firmado por Alex como su plan personal; la mentoría oral a veces difiere (ej. BE trigger, trailing EMAs). Este audit prioriza el PDF como autoritativo excepto cuando explícitamente contradice una regla enseñada en TODOS los videos (ej. "el TP de BLUE es la EMA 4H" se enseña en la intro de BLUE pero el PDF dice TP1=swing anterior y TP_max=EMA 4H — esto es consistente con pensar que el video oral usa "TP" como shorthand para TP_max).
- **Discrepancias intencionales**: `max_total_risk=5%`, `risk_swing=1%` están intencionalmente por debajo del PDF para proteger la cuenta de $190. Son decisiones de negocio válidas pero deben documentarse explícitamente y no presentarse como "de la mentoría".
- **Archivos no examinados en profundidad**: `backend/core/chart_patterns.py`, `backend/core/monthly_review.py`, `backend/core/trade_journal.py`. Audit concentrado en reglas de ejecución, riesgo y detección de estrategia por impacto directo en PnL.
