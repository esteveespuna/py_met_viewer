# Py Met Viewer

A graphical tool for visualizing and comparing espresso shot data from `.shot.json` files.

## Features

- **Load and visualize shot data**: View pressure, flow, weight, temperature sensors, and more
- **Compare two shots**: Overlay two shots side-by-side with different line styles
- **Customizable data series**: Select which metrics to display from categorized checkboxes
- **Secondary Y-axis**: Plot any series on a secondary axis for better scale comparison
- **Line style customization**: Change color, line style (solid/dashed/dotted), and thickness for each series
- **Trim data**: Adjust the duration of each shot to focus on specific time ranges
- **Export to PNG**: Save high-resolution plots for sharing or documentation
- **Auto-load recent files**: Automatically loads the 2 most recent `.shot.json` files on startup

## Requirements

- Python 3.8+
- wxPython
- matplotlib

## Installation

```bash
# Install dependencies
pip install wxPython matplotlib

# Clone the repository
git clone git@github.com:esteveespuna/py_met_viewer.git
cd py_met_viewer

# Run the viewer
python3 shot_viewer.py
```

## Usage

### Basic Usage

1. Run `python3 shot_viewer.py`
2. The app auto-loads the 2 most recent `.shot.json` files from the current directory
3. Select data series to plot using checkboxes in the left panel
4. Use quick select buttons: **All**, **None**, **Shot**, **Temps**

### Comparing Shots

1. Load two shot files using the **Load** buttons
2. Check **Compare mode (overlay)** to overlay both shots
3. Shot 1 is shown with solid lines, Shot 2 with dashed lines

### Customizing Appearance

- Click the **⚙** button next to any data series to customize:
  - Color (preset or custom color picker)
  - Line style (solid, dashed, dotted, dash-dot)
  - Line width
- Check **2nd** to plot a series on the secondary Y-axis

### Trimming Data

- Click the **⚙** button next to each file to adjust:
  - Trim duration to show only part of the shot

### Exporting

- Click **Export PNG** to save the current plot as a high-resolution image

## Data Format

The viewer expects `.shot.json` files with the following structure:

```json
{
  "time": 1234567890.123,
  "profile_name": "Profile Name",
  "data": [
    {
      "time": 0,
      "shot": {
        "pressure": 0.0,
        "flow": 0.0,
        "weight": 0.0,
        "setpoints": { ... }
      },
      "sensors": {
        "motor_speed": 0.0,
        "motor_power": 0.0,
        ...
      }
    }
  ]
}
```

## Command Line Tool

A simple command-line plotting tool is also included:

```bash
python3 plot_met.py path/to/shot.json -o output.png
```

## License

MIT License

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.
