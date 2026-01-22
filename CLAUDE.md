# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

py_met_viewer is a Python GUI application for visualizing and comparing espresso shot data from `.shot.json` files. It includes both an interactive GUI viewer (wxPython) and a CLI plotting tool.

## Commands

### Run the GUI application
```bash
python3 shot_viewer.py
```

### Run the CLI plotting tool
```bash
python3 plot_met.py <shot.json> [-o output.png] [--dpi 300] [--width 16] [--height 8]
```

### Install dependencies
```bash
pip install -r requirements.txt
```

## Architecture

### Main Components

**shot_viewer.py** - Interactive GUI application (~950 lines)
- `ShotData`: Data container class for loading and managing shot JSON files. Handles JSON parsing, time series extraction, and auto-scales time from milliseconds to seconds.
- `ShotViewerFrame`: Main wxPython window with splitter layout (file list/settings on left, matplotlib plot on right)
- `FileSettingsDialog`: Per-file configuration dialog for trimming shot duration
- `StyleDialog`: Line appearance customization (color, style, width)

**plot_met.py** - CLI batch plotting tool (~250 lines)
- Generates PNG plots from shot files with configurable series visibility

### Data Format

Shot files (`.shot.json`) contain:
```json
{
  "time": <unix_timestamp>,
  "profile_name": "<name>",
  "data": [{"time": <elapsed_ms>, "shot": {...}, "sensors": {...}}]
}
```

### Key Patterns

- **Live preview**: Settings dialogs use callbacks to update the plot in real-time
- **Dual Y-axis**: Supports secondary axis for comparing different scales. Zero lines are aligned horizontally via `align_yaxis_zero()`.
- **Compare mode**: Overlay two shots with different line styles (solid vs dashed)
- **Safe nested access**: Uses `safe_get(dict, path, default)` for traversing nested JSON
- **Session persistence**: Save/Load session buttons store configuration to `.session.json` files (loaded files, trim settings, checkbox states, line styles)

## Notes

- Do not execute export to XLSX every time. Just have a test to see data was added to the tables.
