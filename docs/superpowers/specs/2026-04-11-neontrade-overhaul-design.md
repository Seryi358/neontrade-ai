# NeonTrade AI Complete Overhaul — Design Spec

**Date:** 2026-04-11
**Author:** Sergio Castellanos + Claude Opus 4.6

## Overview

Complete overhaul of NeonTrade AI covering: TradingLab mentorship compliance audit, Apple Liquid Glass Light UI redesign, email redesign, exam submission feature, deep testing, and capital adequacy analysis.

## Phase 1: TradingLab Mentorship Audit

Compare all 563 mentorship files against backend code. Every strategy rule, risk parameter, position management phase, and psychology principle must match word-for-word.

**Scope:**
- 6 strategies: BLUE (A/B/C variants), RED, PINK, WHITE, BLACK, GREEN
- Risk management: 1% rule, delta algorithm, correlation limits, max drawdown
- Position management: Long Term, Short Term, Short Term Aggressive, SL moves, partial takes, reentries
- Psychology: Pre-session checklist, revenge trading prevention, FOMO detection
- Funded account rules: No overnight, no weekend, no news, max drawdown

**Output:** Discrepancy report + code corrections

## Phase 2: Apple Liquid Glass Light UI

**Direction:** iOS 26 Liquid Glass, Light mode
**Background:** `#f2f2f7` (Apple system gray 6)
**Cards:** `backdrop-filter: blur(40px) saturate(180%)`, white translucent with inner reflections
**Font:** `-apple-system, 'SF Pro Display', 'SF Pro Text', 'Helvetica Neue', sans-serif`
**Colors:** Apple system colors (blue #007AFF, green #34C759, red #FF3B30, orange #FF9500, yellow #FFCC00)
**Text:** Primary `#1d1d1f`, secondary `#86868b`, tertiary `#aeaeb2`
**Borders:** `rgba(255,255,255,0.6)` on cards, `rgba(0,0,0,0.04)` on subtle dividers
**Shadows:** `0 8px 32px rgba(0,0,0,0.06)`, `inset 0 1px 0 rgba(255,255,255,0.8)`
**Border radius:** 20px cards, 14px sub-cards, 12px pills, 10px buttons
**Animations:** 0.3s ease transitions, subtle scale on hover/press

**Files to change:**
- Rename `cyberpunk.ts` → create `apple-glass.ts`
- Rewrite `HUDComponents.tsx` → `GlassComponents.tsx`
- Rewrite all 9 screens
- Update `App.tsx` navigation styling
- Update CSS variables for web

## Phase 3: Email Redesign

**Direction:** apple.com newsletter aesthetic
**Background:** White `#ffffff`
**Card backgrounds:** `#f5f5f7`
**Font:** `-apple-system, 'SF Pro Display', 'Helvetica Neue', Arial, sans-serif`
**Max width:** 600px centered
**Colors:** Same Apple system colors
**Layout:** Clean sections with generous padding (24-32px), minimal borders

## Phase 4: Exam Submission Feature

New screen "Exam" accessible from the LOG tab.

**Flow:**
1. User sees list of all closed trades
2. Selects exactly 5 trades
3. For each trade, system auto-generates:
   - Candlestick chart screenshot with entry/SL/TP marks
   - HTF analysis summary (trend, structure, key levels)
   - LTF analysis summary (confirmation, entry trigger)
   - Strategy identification + rule checklist
   - Risk calculation (lot size, % risk, R:R)
4. Generates combined HTML report (viewable + downloadable)
5. Can email the report to any address

**Backend:**
- New endpoint `POST /api/v1/exam/generate` accepts 5 trade IDs
- Returns HTML report with embedded chart images (base64)
- Uses existing screenshot_generator.py + analysis data from DB

**Frontend:**
- New `ExamScreen.tsx` in LOG tab (sub-nav: HISTORY | JOURNAL | EXAM)
- Trade selector with checkboxes (max 5)
- Preview + download/email buttons

## Phase 5: Testing + Bug Hunt

- Run full pytest suite (1284+ tests)
- Hit `/diagnostic` endpoint for broker connection
- Send test email via `/api/v1/test-alert`
- Verify position management logic against mentorship
- Static analysis for silent exception swallowing, race conditions, data loss

## Phase 6: Capital Adequacy

Analyze $190 USD against mentorship risk rules:
- 1% risk per trade = $1.90 per trade
- Minimum lot sizes on broker
- Whether $190 is viable or needs deposit
- Recommendations based on funded account workshop content
