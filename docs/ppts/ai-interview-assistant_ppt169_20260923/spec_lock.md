# Execution Lock

## canvas
- viewBox: 0 0 1280 720
- format: PPT 16:9

## colors
- bg: #FFFFFF
- bg_secondary: #F2F6FA
- bg_deep: #0B2E52
- primary: #1565C0
- primary_light: #E3EDF9
- accent: #F57C00
- secondary_accent: #00897B
- text: #1F2733
- text_secondary: #5A6B7D
- text_tertiary: #93A1B0
- text_on_deep: #EAF2FB
- border: #DCE5EE
- success: #2E7D32
- warning: #C62828

## typography
- font_family: "Microsoft YaHei", "PingFang SC", Arial, sans-serif
- code_family: Consolas, Courier New, monospace
- body: 18
- title: 32
- subtitle: 24
- cover_title: 64
- display_number: 150
- section_title: 44
- hero_number: 36
- code: 14
- annotation: 14
- chart_annotation: 13
- page_number: 11

## icons
- library: tabler-outline
- stroke_width: 2
- brand_library: simple-icons
- inventory: dashboard, history, flag-3, alert-triangle, bug, target, users, user-shield, user-check, briefcase, route, git-branch, binary-tree, stack-2, layers-intersect, package, puzzle, box, robot, sparkles, brain, sitemap, database, table, chart-bar, chart-radar, wave-sine, activity, telescope, rocket, refresh, refresh-dot, file-text, file-type-pdf, upload, printer, file-download, checklist, test-pipe, flask, arrows-split, settings, adjustments, code, codeblock, server, circle-check, circle-x, arrow-right, chevron-right, bulb, shield-check, shield-lock, lock, key

## page_rhythm
- P01: anchor
- P02: anchor
- P03: breathing
- P04: dense
- P05: dense
- P06: dense
- P07: dense
- P08: breathing
- P09: dense
- P10: dense
- P11: dense
- P12: dense
- P13: breathing
- P14: dense
- P15: dense
- P16: dense
- P17: dense
- P18: dense
- P19: breathing
- P20: dense
- P21: dense
- P22: dense
- P23: dense
- P24: dense
- P25: dense
- P26: dense
- P27: dense
- P28: dense
- P29: dense
- P30: dense
- P31: dense
- P32: dense
- P33: dense
- P34: dense
- P35: breathing

## page_charts
- P04: comparison_table
- P05: vertical_pillars
- P06: timeline
- P07: vertical_list
- P09: process_flow
- P10: process_flow
- P11: chevron_process
- P14: icon_grid
- P15: layered_architecture
- P17: basic_table
- P18: kpi_cards
- P20: basic_table
- P33: vertical_list
- P34: vertical_list
- P35: roadmap_vertical

## forbidden
- Mixing icon libraries
- rgba()
- `<style>`, `class`, `<foreignObject>`, `textPath`, `@font-face`, `<animate*>`, `<script>`, `<iframe>`, `<symbol>`+`<use>`
- `<g opacity>` (set opacity on each child element individually)
- HTML named entities in text (`&nbsp;`, `&mdash;`, `&copy;`, `&ndash;`, `&reg;`, `&hellip;`, `&bull;` …) — write as raw Unicode (`—`, `©`, `→`, NBSP, etc.); XML reserved chars `& < > " '` must be escaped as `&amp; &lt; &gt; &quot; &apos;`
- Drop shadows on panels (panels are flat: 1px #DCE5EE border + 8px radius, no shadow)
- clipPath (deck contains no raster images)
