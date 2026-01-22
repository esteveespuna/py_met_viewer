# Py Met Viewer

A graphical tool for visualizing and comparing espresso shot data from `.shot.json` files.

## Features

- **Load and visualize shot data**: View pressure, flow, weight, temperature sensors, and more
- **Compare two shots**: Overlay two shots side-by-side with different line styles
- **Customizable data series**: Select which metrics to display from categorized checkboxes
- **Secondary Y-axis**: Plot any series on a secondary axis with aligned zero lines
- **Line style customization**: Change color, line style (solid/dashed/dotted), and thickness for each series
- **Trim data**: Adjust the duration of each shot to focus on specific time ranges
- **Hover values**: See values for all plotted series at the cursor position with colored indicators
- **Save/Load sessions**: Save your configuration and reload it later
- **Export to PNG**: Save high-resolution plots for sharing or documentation
- **Auto-load recent files**: Automatically loads the 2 most recent `.shot.json` files on startup

## Requirements

- Python 3.8+
- wxPython 4.0+
- matplotlib 3.0+

## Installation

```bash
pip install wxPython matplotlib
```

## Usage

### Running the Application

```bash
python3 shot_viewer.py
```

The app auto-loads the 2 most recent `.shot.json` files from the current directory.

### Selecting Data Series

- Use checkboxes in the left panel to select which data series to plot
- Quick select buttons: **All**, **None**, **Shot**, **Temps**
- Check **2nd** to plot a series on the secondary Y-axis

### Comparing Shots

1. Load two shot files using the **Load** buttons
2. Check **Compare mode (overlay)** to overlay both shots
3. Shot 1 is shown with solid lines, Shot 2 with dashed lines

### Customizing Appearance

Click the **⚙** button next to any data series to customize:
- Color (preset colors or custom color picker)
- Line style (solid, dashed, dotted, dash-dot)
- Line width (0.5 - 5.0)

### Trimming Data

Click the **⚙** button next to each file to adjust the trim duration and show only part of the shot.

### Hover Values

Move your mouse over the plot to see values for all plotted series at that time point. The hover panel shows:
- Colored squares matching each line
- Values with units
- In compare mode: values from both shots side by side
- Related series are grouped together (e.g., Pressure next to Pressure Setpoint)

### Save/Load Sessions

- **Save Session**: Saves your current configuration to a `.session.json` file:
  - Loaded shot files
  - Trim settings
  - Selected data series and secondary axis settings
  - Line styles (colors, line types, widths)
  - Compare mode state
- **Load Session**: Restores a previously saved configuration

### Exporting

Click **Export PNG** to save the current plot as a high-resolution image (200 DPI).

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
        "setpoints": {
          "pressure": 0.0,
          "flow": 0.0,
          "power": 0.0
        }
      },
      "sensors": {
        "motor_speed": 0.0,
        "motor_power": 0.0,
        "motor_temp": 0.0,
        ...
      }
    }
  ]
}
```

## License

MIT License
