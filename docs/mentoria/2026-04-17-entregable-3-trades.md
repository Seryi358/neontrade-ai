# Entregable Mentoría TradingLab — 3 Trades Reales

**Alumno:** Sergio Castellanos
**Fecha inicio:** 2026-04-17
**Capital operado:** 190.88 USD
**Broker:** Capital.com (MANUAL mode, cuenta 314623104804541636)
**Plataforma:** Atlas (app custom basada en TradingLab, commit `73e14db`)
**App URL:** https://n8n-neontrade-ai.zb12wf.easypanel.host/

## Configuración aplicada (per Trading Plan PDF + audit 2026-04-17)

| Parámetro | Valor | Fuente |
|---|---|---|
| trading_style | day_trading | Alex: "el mejor estilo independientemente de la situación" |
| risk_day_trading | 1% ($1.91/trade) | Ch18.3 Regla del 1% |
| max_trades_per_day | 3 | Day trading: quality over quantity |
| max_total_risk | 5% | Cap seguridad para $190 (PDF: 7%) |
| be_trigger_method | pct_to_tp1 (0.50) | Trading Plan PDF pg.5 |
| position_management | CP (short-term) | Alex: "salir cuanto antes" |
| trailing EMAs | EMA 5 (M5) principal, EMA 2 emergency | PDF pg.5 |
| strategies | BLUE + RED only | Mentoría: start con estas |
| trading_hours_utc | 07:00-21:00 | London + NY sessions |
| BLUE TP1 | swing anterior | PDF pg.6 (TP_max = EMA 4H) |
| RED TP_max | Fib 1.0 (Wave 3 + HTF favor) | PDF pg.6 |
| EMA 8 Weekly filter | solo crypto | Fuera de Trading Mastery |

## Flujo de cada trade

1. Atlas escanea mercado en ciclos de 120s (07-21 UTC)
2. Cuando detecta setup válido → IA valida → si OK:
   - Gmail alert a `scastellanos@phinodia.com` con detalles (par, strategy, entry, SL, TP, size, análisis)
   - WebSocket push a la Trade tab de la app
3. Sergio abre app, revisa, decide **Aprobar** o **Rechazar**
4. Si aprueba → orden enviada a Capital.com
5. Posición gestionada automáticamente:
   - BE cuando pct_to_tp1 = 0.50 alcanzado
   - Espera ruptura del swing previo antes de activar trailing
   - Trailing con EMA 5 (M5)
6. Cierre (TP, SL, trailing, o manual) → screenshot automático → Gmail close alert

## Trade 1

**Fecha/hora:** _(pendiente — esperando setup lunes 2026-04-20 07:00+ UTC)_

- **Par:** _TBD_
- **Strategy:** _BLUE | RED_
- **Direction:** _BUY | SELL_
- **Entry:** _TBD_
- **SL:** _TBD_
- **TP1:** _TBD (swing anterior)_
- **TP_max:** _TBD_
- **Size:** _TBD unidades_
- **Margin requerido:** _TBD USD_
- **R:R:** _TBD_

### Análisis pre-entry
_Qué vio Atlas: HTF alignment, condiciones de strategy, confluence. Razones de la IA para aprobar._

### Screenshot setup
`screenshots/trade_1_setup.png`

### Gestión
_Price action, si hubo BE, si activó trailing post-swing-break, momentos clave._

### Cierre
- **Tipo:** _TP1 | SL | trailing | manual_
- **Close price:** _TBD_
- **P&L USD:** _TBD_
- **P&L %:** _TBD_
- **Duración:** _HH:MM_

### Screenshot cierre
`screenshots/trade_1_close.png`

### Conclusión
_Qué aprendí. Fidelidad del flujo vs TradingLab._

---

## Trade 2

_(estructura idéntica; pendiente)_

---

## Trade 3

_(estructura idéntica; pendiente)_

---

## Resumen final (al completar)

| Trade | Par | Strategy | Direction | P&L USD | Duración |
|---|---|---|---|---|---|
| 1 | — | — | — | — | — |
| 2 | — | — | — | — | — |
| 3 | — | — | — | — | — |

**Total P&L:** _TBD_
**Balance final:** _TBD_

## Reflexión final

_(al completar)_
