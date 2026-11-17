# Skies Studio Design System

## Identity
Desktop workstation GUI for Skies WebGL cartoon short rendering, storyboard inspection, audio-synced cel previewing, and MP4 encoding.

- **Visual Language**: Warm Analog Cel & Storyboard Studio
- **Mode**: Operate (primary task workspace), Experience (9:16 frame light-table & theater playback)
- **Dials**: `ENERGY 2 / RHYTHM 2 / MOTION 1`

## Color Palette (WCAG AA Verified)
Strict restraint: neutral paper/darkroom planes + 1 warm vermilion accent + functional status tones only.

### Light Mode (Drafting Table Parchment)
- Ground: `#f4efe6`
- Surface: `#fcfaf5`
- Muted Tray: `#e8e0d2`
- Hairline Border: `#d0c7b8` (strong: `#8f8679`)
- Ink Primary: `#1c1917` (15.27:1 on `#f4efe6`)
- Ink Secondary: `#57534e` (7.31:1 on `#fcfaf5`, 6.66:1 on `#f4efe6`)
- Accent (Vermilion Pencil): `#b93818` (`#ffffff` text contrast 5.77:1)
- Success: `#15803d` (4.81:1 on `#fcfaf5`)
- Warning: `#9a3412` (7.00:1 on `#fcfaf5`)
- Danger: `#b91c1c` (6.20:1 on `#fcfaf5`)

### Dark Mode (Film Darkroom)
- Ground: `#161412`
- Surface: `#1f1c19`
- Muted Tray: `#2a2622`
- Hairline Border: `#3a342e` (strong: `#665e55`)
- Ink Primary: `#f5f0e6` (16.18:1 on `#161412`)
- Ink Secondary: `#b8afa3` (7.83:1 on `#1f1c19`)
- Accent (Warm Vermilion): `#e05a36` (`#161412` text contrast 4.97:1)
- Success: `#4ade80` (9.73:1 on `#1f1c19`)
- Warning: `#fbbf24` (10.16:1 on `#1f1c19`)
- Danger: `#f87171` (6.13:1 on `#1f1c19`)

## Typography & Geometry
- **UI & Headings**: Native system sans-serif (`"Segoe UI", -apple-system, BlinkMacSystemFont, sans-serif`) for sharp legibility and instant render.
- **Technical Readouts Only**: `ui-monospace, Consolas, monospace` with `tabular-nums` strictly for frame numbers (`#00440`), timecodes (`00:14:20`), filenames, and render console output.
- **Radii**: Sharp drafting-table geometry: `6px` panels, `4px` buttons/inputs, `2px` timeline ticks.
- **Motion**: `MOTION 1` — instant frame updates; quiet `120ms ease` transitions only on hover/focus/disclosure states. Zero decorative pulses or loops.
