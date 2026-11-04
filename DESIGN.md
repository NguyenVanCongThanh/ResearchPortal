---
name: ResearchPortal
description: Machine Learning Research Operations & Training Control Plane
colors:
  primary: "#4f46e5"
  primary-hover: "#6366f1"
  success: "#10b981"
  warning: "#f59e0b"
  danger: "#f43f5e"
  neutral-void: "#070b14"
  neutral-surface: "#0d1527"
  neutral-overlay: "#151f32"
  neutral-border: "#1e293b"
  neutral-border-bright: "#334155"
  text-primary: "#f8fafc"
  text-muted: "#94a3b8"
typography:
  display:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 700
    lineHeight: 1.25
  body:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.5
  mono:
    fontFamily: "JetBrains Mono, monospace"
    fontSize: "0.75rem"
    fontWeight: 500
    lineHeight: 1.4
rounded:
  sm: "4px"
  md: "8px"
  lg: "12px"
  xl: "16px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.md}"
    padding: "8px 16px"
  card:
    backgroundColor: "{colors.neutral-surface}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.lg}"
    padding: "20px"
---

# Design System: ResearchPortal

## Overview

**Creative North Star: "The Mission Control Bridge"**

ResearchPortal is an operator-facing control plane and telemetry dashboard designed for high-density, uninterrupted monitoring of remote Kaggle kernels and W&B training runs. Ambient clarity, calm dark-mode ergonomics, and strict separation between automated fixture and live environments drive the user interface.

### Key Characteristics:
- **Restrained Dark Palette:** Deep cosmic void backdrop (`#070b14`) paired with slate elevation layers prevents eye fatigue during extended experimentation.
- **Semantic Status Signals:** Vibrant emerald (`#10b981`), amber (`#f59e0b`), rose (`#f43f5e`), and sky blue (`#38bdf8`) indicators communicate health at a glance without decorative clutter.
- **Monospace Data Density:** Code references, iterations, loss metrics, and commit hashes always render in JetBrains Mono.

## Colors

The palette employs deep void surfaces with focused neon semantic accents.

### Primary
- **Indigo Accent** (`#4f46e5` / `#6366f1` hover): Primary triggers, brand identity badges, active selections.

### Semantic
- **Emerald Progress** (`#10b981`): Healthy training progression, verified accounts, active worker.
- **Amber Warning** (`#f59e0b`): Suspected training stalls, ambiguity resolution, pending operator confirmation.
- **Rose Danger** (`#f43f5e`): Failed runs, API errors, offline services.
- **Sky Telemetry** (`#38bdf8`): Remote logs, secondary loss series.

### Neutral
- **Portal Void** (`#070b14`): Base canvas backdrop.
- **Portal Surface** (`#0d1527`): Elevated cards, containers, tab panels.
- **Portal Overlay** (`#151f32`): Terminal bodies, dropdowns, modal windows.
- **Portal Border** (`#1e293b`): Subtle gridlines and separators.

### Named Rules
**The Rarity of Accent Rule.** The primary indigo accent is restricted to explicit call-to-action buttons, active navigation markers, and brand emblems. Informational data remains neutral or semantic.

## Typography

**Body & UI Font:** Inter, system-ui, sans-serif  
**Data & Telemetry Font:** JetBrains Mono, monospace  

### Hierarchy
- **Headline** (700, 1rem to 1.125rem, 1.25): Panel headers and section titles.
- **Body** (400 to 500, 0.8125rem to 0.875rem, 1.5): Descriptive copy, instructions, form labels.
- **Mono / Metric** (500 to 700, 0.75rem to 1.25rem, 1.2): Kernel slugs, hashes, iterations, loss values.

## Layout

A constrained max-width container (`max-w-7xl`) with responsive gutters (`px-4 sm:px-6 lg:px-8`) anchors the dashboard. Grid structures adapt from single column on small mobile screens to 2 and 4 columns on tablets and desktop monitors.

## Elevation & Depth

Surfaces rely on tonal layering and crisp 1px borders rather than heavy drop shadows. Modals and toast notifications use subtle, colored ambient glows to elevate without creating visual noise.

## Shapes

- **Cards & Modals:** Rounded corners (`12px` / `rounded-xl`).
- **Buttons & Inputs:** Medium rounded corners (`8px` / `rounded-lg`).
- **Status Badges & Chips:** Compact pill or rounded corners (`4px` / `rounded`).

## Components

### Buttons
- **Primary:** Indigo background (`#4f46e5`), hover (`#6366f1`), min-height 38px–44px, bold label.
- **Secondary:** Slate-800 background, border slate-700, hover slate-700.

### Modal Dialogs
- **Backdrop:** 75% black blur backdrop.
- **Body:** `bg-slate-900`, `border-slate-800`, `rounded-xl`, full ARIA accessibility and focus trapping.

### Terminal & Metric Displays
- **Terminal:** `bg-portal-void`, header `bg-portal-surface`, mono font, custom scrollbar.

## Do's and Don'ts

### Do:
- **Do** format model metric metrics (mDice, loss) to 4 decimal places using monospace font.
- **Do** provide non-blocking toast notifications for mutation dispatches.
- **Do** wrap primary interactive targets to at least 38px–44px for touch accessibility.

### Don't:
- **Don't** use synchronous browser `alert()` or `confirm()` dialogs.
- **Don't** introduce light mode or high-saturation white backdrops that break the mission-control dark mode.
- **Don't** mix un-tokenized raw color hexes outside the portal color system.

