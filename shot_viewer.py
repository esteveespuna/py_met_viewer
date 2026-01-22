#!/usr/bin/env python3
"""
shot_viewer.py — GUI tool for visualizing espresso shot data from *.shot.json files.

Features:
- Load and visualize shot data
- Select which sensors/metrics to display
- Compare two shots side by side
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import wx
import wx.html
import wx.lib.scrolledpanel as scrolled

import matplotlib
matplotlib.use('WXAgg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as FigureCanvas
from matplotlib.backends.backend_wxagg import NavigationToolbar2WxAgg as NavigationToolbar
from matplotlib.figure import Figure


def align_yaxis_zero(ax1, ax2):
    """
    Adjust y-axis limits of ax1 and ax2 so that zero appears at the same
    vertical position on both axes.
    """
    y1_min, y1_max = ax1.get_ylim()
    y2_min, y2_max = ax2.get_ylim()

    # Ensure zero is included in both axes
    y1_min, y1_max = min(y1_min, 0), max(y1_max, 0)
    y2_min, y2_max = min(y2_min, 0), max(y2_max, 0)

    # Handle edge cases
    if y1_max == 0 and y2_max == 0:
        # Both entirely negative, zero is at top
        return
    if y1_min == 0 and y2_min == 0:
        # Both entirely positive, zero is at bottom
        return

    # Calculate negative/positive ratios
    ratio1 = -y1_min / y1_max if y1_max > 0 else float('inf')
    ratio2 = -y2_min / y2_max if y2_max > 0 else float('inf')

    # Use the larger ratio for both (so neither axis clips data)
    target_ratio = max(ratio1, ratio2)

    # Apply to ax1
    if y1_max > 0:
        new_y1_min = -target_ratio * y1_max
        ax1.set_ylim(new_y1_min, y1_max)

    # Apply to ax2
    if y2_max > 0:
        new_y2_min = -target_ratio * y2_max
        ax2.set_ylim(new_y2_min, y2_max)


# Data field definitions: (path, display_name, category, unit)
DATA_FIELDS = [
    # Shot data
    (["shot", "pressure"], "Pressure", "Shot", "bar"),
    (["shot", "flow"], "Flow", "Shot", "ml/s"),
    (["shot", "weight"], "Weight", "Shot", "g"),
    (["shot", "gravimetric_flow"], "Gravimetric Flow", "Shot", "g/s"),
    # Setpoints
    (["shot", "setpoints", "pressure"], "Pressure Setpoint", "Setpoints", "bar"),
    (["shot", "setpoints", "flow"], "Flow Setpoint", "Setpoints", "ml/s"),
    (["shot", "setpoints", "power"], "Power Setpoint", "Setpoints", "%"),
    # Motor sensors
    (["sensors", "motor_speed"], "Motor Speed", "Motor", "rpm"),
    (["sensors", "motor_power"], "Motor Power", "Motor", "%"),
    (["sensors", "motor_current"], "Motor Current", "Motor", "A"),
    (["sensors", "motor_temp"], "Motor Temp", "Motor", "°C"),
    (["sensors", "motor_position"], "Motor Position", "Motor", "mm"),
    # Temperature sensors
    (["sensors", "external_1"], "External Temp 1", "Temperature", "°C"),
    (["sensors", "external_2"], "External Temp 2", "Temperature", "°C"),
    (["sensors", "bar_up"], "Bar Up Temp", "Temperature", "°C"),
    (["sensors", "bar_mid_up"], "Bar Mid Up Temp", "Temperature", "°C"),
    (["sensors", "bar_mid_down"], "Bar Mid Down Temp", "Temperature", "°C"),
    (["sensors", "bar_down"], "Bar Down Temp", "Temperature", "°C"),
    (["sensors", "tube"], "Tube Temp", "Temperature", "°C"),
    (["sensors", "lam_temp"], "LAM Temp", "Temperature", "°C"),
    # Other sensors
    (["sensors", "pressure_sensor"], "Pressure Sensor Raw", "Other", ""),
    (["sensors", "bandheater_power"], "Bandheater Power", "Other", "%"),
    (["sensors", "bandheater_current"], "Bandheater Current", "Other", "A"),
    (["sensors", "weight_prediction"], "Weight Prediction", "Other", "g"),
    (["sensors", "adc_0"], "ADC 0", "ADC", ""),
    (["sensors", "adc_1"], "ADC 1", "ADC", ""),
    (["sensors", "adc_2"], "ADC 2", "ADC", ""),
    (["sensors", "adc_3"], "ADC 3", "ADC", ""),
]


def safe_get(d: Dict[str, Any], path: List[str], default=float("nan")):
    """Safely navigate nested dict."""
    cur: Any = d
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def infer_time_scale(times_raw: List[float]) -> float:
    """Returns multiplier to convert time to seconds."""
    if len(times_raw) < 2:
        return 1.0
    deltas = [abs(times_raw[i] - times_raw[i - 1]) for i in range(1, len(times_raw))]
    deltas = [d for d in deltas if d > 0]
    if not deltas:
        return 1.0
    deltas_sorted = sorted(deltas)
    med = deltas_sorted[len(deltas_sorted) // 2]
    return 1.0 / 1000.0 if med >= 5 else 1.0


class ShotData:
    """Container for loaded shot data."""

    def __init__(self, path: Path):
        self.path = path
        self.profile_name = "Unknown"
        self.shot_time: Optional[float] = None
        self.records: List[Dict[str, Any]] = []
        self.time_s: List[float] = []
        self._load()

    def _load(self):
        with self.path.open("r", encoding="utf-8") as f:
            doc = json.load(f)

        if "data" not in doc or not isinstance(doc["data"], list):
            raise ValueError("JSON missing 'data' list")

        self.profile_name = doc.get("profile_name", "Unknown Profile")
        self.shot_time = doc.get("time", None)
        self.records = doc["data"]

        # Build time series
        times_raw = [float(r.get("time", 0.0)) for r in self.records]
        t0 = times_raw[0] if times_raw else 0.0
        scale = infer_time_scale(times_raw)
        self.time_s = [(t - t0) * scale for t in times_raw]

    def get_series(self, path: List[str]) -> List[float]:
        """Extract a data series by path."""
        result = []
        for r in self.records:
            val = safe_get(r, path, float("nan"))
            try:
                result.append(float(val) if val is not None else float("nan"))
            except (TypeError, ValueError):
                result.append(float("nan"))
        return result

    def get_title(self) -> str:
        if self.shot_time:
            dt = datetime.fromtimestamp(self.shot_time)
            return f"{self.profile_name} – {dt.strftime('%Y-%m-%d %H:%M:%S')}"
        return self.profile_name

    def get_short_name(self) -> str:
        return self.path.stem

    def get_date_label(self) -> str:
        """Get a short date/time label for display."""
        if self.shot_time:
            dt = datetime.fromtimestamp(self.shot_time)
            return dt.strftime("%Y-%m-%d %H:%M")
        return self.path.stem


class FileSettingsDialog(wx.Dialog):
    """Dialog to configure file-specific settings like trim duration."""

    def __init__(self, parent, shot_data: 'ShotData', current_settings: Dict, on_change_callback=None):
        super().__init__(parent, title=f"Settings: {shot_data.get_short_name()}", size=(400, 200))

        self.shot_data = shot_data
        self.on_change_callback = on_change_callback
        self.saved = False

        # Calculate default duration (last time - first time)
        # Ensure max_duration is at least 0.1 to avoid GTK SpinCtrl assertion errors
        self.max_duration = max(0.1, shot_data.time_s[-1] if shot_data.time_s else 0.1)
        self.result_settings = current_settings.copy() if current_settings else {}

        if "trim_duration" not in self.result_settings:
            self.result_settings["trim_duration"] = self.max_duration

        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Info label
        info_text = f"Total duration: {self.max_duration:.2f} seconds"
        info_label = wx.StaticText(panel, label=info_text)
        sizer.Add(info_label, 0, wx.ALL, 10)

        # Duration input
        dur_sizer = wx.BoxSizer(wx.HORIZONTAL)
        dur_sizer.Add(wx.StaticText(panel, label="Trim to duration (s):"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)

        # Clamp initial value to valid range to avoid GTK errors
        initial_value = self.result_settings.get("trim_duration", self.max_duration)
        initial_value = max(0.1, min(initial_value, self.max_duration))
        self.duration_ctrl = wx.SpinCtrlDouble(panel, min=0.1, max=self.max_duration,
                                                initial=initial_value, inc=0.5, size=(120, -1))
        self.duration_ctrl.SetDigits(2)
        self.duration_ctrl.Bind(wx.EVT_SPINCTRLDOUBLE, self._on_duration_change)
        dur_sizer.Add(self.duration_ctrl, 0, wx.ALIGN_CENTER_VERTICAL)

        # Reset to max button
        btn_max = wx.Button(panel, label="Max", size=(50, -1))
        btn_max.SetToolTip("Reset to full duration")
        btn_max.Bind(wx.EVT_BUTTON, self._on_reset_max)
        dur_sizer.Add(btn_max, 0, wx.LEFT, 5)

        sizer.Add(dur_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # Buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_defaults = wx.Button(panel, label="Defaults")
        btn_defaults.SetToolTip("Reset all settings to defaults")
        btn_defaults.Bind(wx.EVT_BUTTON, self._on_defaults)
        btn_sizer.Add(btn_defaults, 0, wx.RIGHT, 10)
        btn_sizer.AddStretchSpacer()
        btn_cancel = wx.Button(panel, wx.ID_CANCEL, "Cancel")
        btn_sizer.Add(btn_cancel, 0, wx.RIGHT, 5)
        btn_save = wx.Button(panel, wx.ID_OK, "Save")
        btn_save.Bind(wx.EVT_BUTTON, self._on_save)
        btn_sizer.Add(btn_save, 0)
        sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 10)

        panel.SetSizer(sizer)

    def _on_duration_change(self, event):
        self.result_settings["trim_duration"] = self.duration_ctrl.GetValue()
        if self.on_change_callback:
            self.on_change_callback(self.result_settings)

    def _on_reset_max(self, event):
        self.duration_ctrl.SetValue(self.max_duration)
        self.result_settings["trim_duration"] = self.max_duration
        if self.on_change_callback:
            self.on_change_callback(self.result_settings)

    def _on_defaults(self, event):
        self.result_settings = {"trim_duration": self.max_duration}
        self.saved = True
        if self.on_change_callback:
            self.on_change_callback(self.result_settings)
        self.EndModal(wx.ID_OK)

    def _on_save(self, event):
        self.result_settings["trim_duration"] = self.duration_ctrl.GetValue()
        self.saved = True
        self.EndModal(wx.ID_OK)

    def get_settings(self) -> Dict:
        return self.result_settings


class StyleDialog(wx.Dialog):
    """Dialog to customize line style for a data series."""

    PRESET_COLORS = [
        ("Auto", None),
        ("Blue", "#1f77b4"),
        ("Orange", "#ff7f0e"),
        ("Green", "#2ca02c"),
        ("Red", "#d62728"),
        ("Purple", "#9467bd"),
        ("Brown", "#8c564b"),
        ("Pink", "#e377c2"),
        ("Gray", "#7f7f7f"),
        ("Yellow", "#bcbd22"),
        ("Cyan", "#17becf"),
        ("Black", "#000000"),
    ]

    LINESTYLES = [
        ("Solid", "-"),
        ("Dashed", "--"),
        ("Dotted", ":"),
        ("Dash-Dot", "-."),
    ]

    LINEWIDTHS = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]

    def __init__(self, parent, field_name: str, current_style: Dict, on_change_callback=None):
        super().__init__(parent, title=f"Style: {field_name}", size=(420, 320))

        self.result_style = current_style.copy() if current_style else {}
        self.on_change_callback = on_change_callback
        self.custom_color = None
        self.saved = False

        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Color selection with preview
        color_label = wx.StaticText(panel, label="Color:")
        sizer.Add(color_label, 0, wx.LEFT | wx.TOP, 10)

        # Preset color buttons
        color_grid = wx.GridSizer(rows=2, cols=6, hgap=5, vgap=5)
        self.color_buttons = []
        current_color = self.result_style.get("color")

        for name, hex_color in self.PRESET_COLORS:
            btn = wx.Button(panel, label="", size=(40, 25))
            if hex_color:
                btn.SetBackgroundColour(wx.Colour(hex_color))
            else:
                btn.SetLabel("Auto")
            btn.SetToolTip(name)
            btn.Bind(wx.EVT_BUTTON, lambda e, c=hex_color: self._on_preset_color(c))
            color_grid.Add(btn, 0, wx.EXPAND)
            self.color_buttons.append((btn, hex_color))

        sizer.Add(color_grid, 0, wx.EXPAND | wx.ALL, 10)

        # Color picker row
        picker_sizer = wx.BoxSizer(wx.HORIZONTAL)
        picker_sizer.Add(wx.StaticText(panel, label="Custom:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)

        # Initialize color picker with current color or default
        init_color = wx.Colour(current_color) if current_color else wx.Colour("#1f77b4")
        self.color_picker = wx.ColourPickerCtrl(panel, colour=init_color)
        self.color_picker.Bind(wx.EVT_COLOURPICKER_CHANGED, self._on_color_picked)
        picker_sizer.Add(self.color_picker, 0, wx.RIGHT, 10)

        # Current color preview
        self.color_preview = wx.Panel(panel, size=(60, 25))
        self._update_preview(current_color)
        picker_sizer.Add(self.color_preview, 0, wx.ALIGN_CENTER_VERTICAL)

        sizer.Add(picker_sizer, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # Line style selection
        style_sizer = wx.BoxSizer(wx.HORIZONTAL)
        style_sizer.Add(wx.StaticText(panel, label="Line Style:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        self.style_choice = wx.Choice(panel, choices=[s[0] for s in self.LINESTYLES])
        current_ls = self.result_style.get("linestyle", "-")
        style_idx = 0
        for i, (name, val) in enumerate(self.LINESTYLES):
            if val == current_ls:
                style_idx = i
                break
        self.style_choice.SetSelection(style_idx)
        self.style_choice.Bind(wx.EVT_CHOICE, self._on_style_change)
        style_sizer.Add(self.style_choice, 1, wx.EXPAND)
        sizer.Add(style_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # Line width selection
        width_sizer = wx.BoxSizer(wx.HORIZONTAL)
        width_sizer.Add(wx.StaticText(panel, label="Line Width:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        self.width_choice = wx.Choice(panel, choices=[str(w) for w in self.LINEWIDTHS])
        current_lw = self.result_style.get("linewidth", 1.5)
        width_idx = 2  # default 1.5
        for i, w in enumerate(self.LINEWIDTHS):
            if w == current_lw:
                width_idx = i
                break
        self.width_choice.SetSelection(width_idx)
        self.width_choice.Bind(wx.EVT_CHOICE, self._on_width_change)
        width_sizer.Add(self.width_choice, 1, wx.EXPAND)
        sizer.Add(width_sizer, 0, wx.EXPAND | wx.ALL, 10)

        # Buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_defaults = wx.Button(panel, label="Defaults")
        btn_defaults.SetToolTip("Reset to default style")
        btn_defaults.Bind(wx.EVT_BUTTON, self._on_defaults)
        btn_sizer.Add(btn_defaults, 0, wx.RIGHT, 10)
        btn_sizer.AddStretchSpacer()
        btn_cancel = wx.Button(panel, wx.ID_CANCEL, "Cancel")
        btn_cancel.SetToolTip("Discard changes")
        btn_sizer.Add(btn_cancel, 0, wx.RIGHT, 5)
        btn_save = wx.Button(panel, wx.ID_OK, "Save")
        btn_save.SetToolTip("Save style changes")
        btn_sizer.Add(btn_save, 0)
        sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 10)

        panel.SetSizer(sizer)

        btn_save.Bind(wx.EVT_BUTTON, self._on_save)

    def _update_preview(self, color):
        """Update the color preview panel."""
        if color:
            self.color_preview.SetBackgroundColour(wx.Colour(color))
        else:
            self.color_preview.SetBackgroundColour(wx.Colour("#cccccc"))
        self.color_preview.Refresh()

    def _on_preset_color(self, color):
        """Handle preset color button click."""
        self.result_style["color"] = color
        self._update_preview(color)
        self._notify_change()

    def _on_color_picked(self, event):
        """Handle color picker change."""
        color = self.color_picker.GetColour()
        hex_color = color.GetAsString(wx.C2S_HTML_SYNTAX)
        self.result_style["color"] = hex_color
        self._update_preview(hex_color)
        self._notify_change()

    def _on_style_change(self, event):
        """Handle line style change."""
        style_idx = self.style_choice.GetSelection()
        self.result_style["linestyle"] = self.LINESTYLES[style_idx][1]
        self._notify_change()

    def _on_width_change(self, event):
        """Handle line width change."""
        width_idx = self.width_choice.GetSelection()
        self.result_style["linewidth"] = self.LINEWIDTHS[width_idx]
        self._notify_change()

    def _notify_change(self):
        """Notify parent of style change for live preview."""
        if self.on_change_callback:
            self.on_change_callback(self.result_style)

    def _on_save(self, event):
        """Save the current style and close."""
        # Ensure final values are captured
        if "linestyle" not in self.result_style:
            style_idx = self.style_choice.GetSelection()
            self.result_style["linestyle"] = self.LINESTYLES[style_idx][1]

        if "linewidth" not in self.result_style:
            width_idx = self.width_choice.GetSelection()
            self.result_style["linewidth"] = self.LINEWIDTHS[width_idx]

        self.saved = True
        self.EndModal(wx.ID_OK)

    def _on_defaults(self, event):
        """Reset to default style and close."""
        self.result_style = {}
        self.saved = True
        self._notify_change()
        self.EndModal(wx.ID_OK)

    def get_style(self) -> Dict:
        return self.result_style


class ShotViewerFrame(wx.Frame):
    """Main application frame."""

    def __init__(self):
        super().__init__(None, title="Shot Viewer", size=(1400, 900))

        self.shot1: Optional[ShotData] = None
        self.shot2: Optional[ShotData] = None
        self.shot1_settings: Dict = {}
        self.shot2_settings: Dict = {}
        self.field_checkboxes: Dict[str, wx.CheckBox] = {}
        self.field_secondary: Dict[str, wx.CheckBox] = {}
        self.field_styles: Dict[str, Dict] = {}  # {key: {color, linestyle, linewidth}}

        # Data for hover display
        self.plot_data: Dict = {}  # Stores current plot data for hover lookup

        self._setup_ui()
        self._auto_load_json_files()

    def _setup_ui(self):
        # Main splitter
        splitter = wx.SplitterWindow(self, style=wx.SP_LIVE_UPDATE)

        # Left panel: controls
        left_panel = wx.Panel(splitter)
        left_sizer = wx.BoxSizer(wx.VERTICAL)

        # Session save/load section
        session_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_save_session = wx.Button(left_panel, label="Save Session", size=(100, -1))
        btn_save_session.Bind(wx.EVT_BUTTON, lambda e: self._save_session())
        session_sizer.Add(btn_save_session, 1, wx.RIGHT, 5)
        btn_load_session = wx.Button(left_panel, label="Load Session", size=(100, -1))
        btn_load_session.Bind(wx.EVT_BUTTON, lambda e: self._load_session())
        session_sizer.Add(btn_load_session, 1)
        left_sizer.Add(session_sizer, 0, wx.EXPAND | wx.ALL, 5)

        # File loading section
        file_box = wx.StaticBox(left_panel, label="Files")
        file_sizer = wx.StaticBoxSizer(file_box, wx.VERTICAL)

        # Shot 1 row
        shot1_sizer = wx.BoxSizer(wx.HORIZONTAL)
        shot1_sizer.Add(wx.StaticText(left_panel, label="Shot 1:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.shot1_label = wx.StaticText(left_panel, label="(none)", size=(120, -1))
        shot1_sizer.Add(self.shot1_label, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        btn_load1 = wx.Button(left_panel, label="Load", size=(50, -1))
        btn_load1.Bind(wx.EVT_BUTTON, lambda e: self._load_file(1))
        shot1_sizer.Add(btn_load1, 0, wx.RIGHT, 2)
        btn_clear1 = wx.Button(left_panel, label="Clear", size=(50, -1))
        btn_clear1.Bind(wx.EVT_BUTTON, lambda e: self._clear_file(1))
        shot1_sizer.Add(btn_clear1, 0, wx.RIGHT, 2)
        self.btn_settings1 = wx.Button(left_panel, label="\u2699", size=(36, -1))
        self.btn_settings1.SetToolTip("File settings (trim, etc.)")
        self.btn_settings1.Bind(wx.EVT_BUTTON, lambda e: self._open_file_settings(1))
        self.btn_settings1.Enable(False)
        shot1_sizer.Add(self.btn_settings1, 0)
        file_sizer.Add(shot1_sizer, 0, wx.EXPAND | wx.ALL, 5)

        # Shot 2 row
        shot2_sizer = wx.BoxSizer(wx.HORIZONTAL)
        shot2_sizer.Add(wx.StaticText(left_panel, label="Shot 2:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.shot2_label = wx.StaticText(left_panel, label="(none)", size=(120, -1))
        shot2_sizer.Add(self.shot2_label, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        btn_load2 = wx.Button(left_panel, label="Load", size=(50, -1))
        btn_load2.Bind(wx.EVT_BUTTON, lambda e: self._load_file(2))
        shot2_sizer.Add(btn_load2, 0, wx.RIGHT, 2)
        btn_clear2 = wx.Button(left_panel, label="Clear", size=(50, -1))
        btn_clear2.Bind(wx.EVT_BUTTON, lambda e: self._clear_file(2))
        shot2_sizer.Add(btn_clear2, 0, wx.RIGHT, 2)
        self.btn_settings2 = wx.Button(left_panel, label="\u2699", size=(36, -1))
        self.btn_settings2.SetToolTip("File settings (trim, etc.)")
        self.btn_settings2.Bind(wx.EVT_BUTTON, lambda e: self._open_file_settings(2))
        self.btn_settings2.Enable(False)
        shot2_sizer.Add(self.btn_settings2, 0)
        file_sizer.Add(shot2_sizer, 0, wx.EXPAND | wx.ALL, 5)

        # Compare checkbox
        self.compare_cb = wx.CheckBox(left_panel, label="Compare mode (overlay)")
        self.compare_cb.Bind(wx.EVT_CHECKBOX, lambda e: self._update_plot())
        file_sizer.Add(self.compare_cb, 0, wx.ALL, 5)

        left_sizer.Add(file_sizer, 0, wx.EXPAND | wx.ALL, 5)

        # Data selection section (scrollable)
        select_box = wx.StaticBox(left_panel, label="Data Series")
        select_sizer = wx.StaticBoxSizer(select_box, wx.VERTICAL)

        self.scroll_panel = scrolled.ScrolledPanel(left_panel, size=(-1, 400))
        self.scroll_panel.SetupScrolling(scroll_x=False)
        scroll_sizer = wx.BoxSizer(wx.VERTICAL)

        self._create_checkboxes(scroll_sizer)

        self.scroll_panel.SetSizer(scroll_sizer)
        select_sizer.Add(self.scroll_panel, 1, wx.EXPAND | wx.ALL, 5)

        left_sizer.Add(select_sizer, 1, wx.EXPAND | wx.ALL, 5)

        # Quick select buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_all = wx.Button(left_panel, label="All", size=(50, -1))
        btn_all.Bind(wx.EVT_BUTTON, lambda e: self._select_all())
        btn_sizer.Add(btn_all, 0, wx.RIGHT, 2)

        btn_none = wx.Button(left_panel, label="None", size=(50, -1))
        btn_none.Bind(wx.EVT_BUTTON, lambda e: self._select_none())
        btn_sizer.Add(btn_none, 0, wx.RIGHT, 2)

        btn_shot = wx.Button(left_panel, label="Shot", size=(50, -1))
        btn_shot.Bind(wx.EVT_BUTTON, lambda e: self._select_shot())
        btn_sizer.Add(btn_shot, 0, wx.RIGHT, 2)

        btn_temps = wx.Button(left_panel, label="Temps", size=(50, -1))
        btn_temps.Bind(wx.EVT_BUTTON, lambda e: self._select_temps())
        btn_sizer.Add(btn_temps, 0)

        left_sizer.Add(btn_sizer, 0, wx.ALL, 5)

        # Update and Export buttons
        btn_update = wx.Button(left_panel, label="Update Plot")
        btn_update.Bind(wx.EVT_BUTTON, lambda e: self._update_plot())
        left_sizer.Add(btn_update, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 5)

        btn_export = wx.Button(left_panel, label="Export PNG")
        btn_export.Bind(wx.EVT_BUTTON, lambda e: self._export_png())
        left_sizer.Add(btn_export, 0, wx.EXPAND | wx.ALL, 5)

        left_panel.SetSizer(left_sizer)

        # Right panel: plot
        right_panel = wx.Panel(splitter)
        right_sizer = wx.BoxSizer(wx.VERTICAL)

        self.fig = Figure(figsize=(10, 7), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvas(right_panel, -1, self.fig)

        self.toolbar = NavigationToolbar(self.canvas)
        self.toolbar.Realize()

        # Hover values panel (using HtmlWindow for colored squares)
        self.hover_html = wx.html.HtmlWindow(right_panel, size=(-1, 80),
                                              style=wx.html.HW_SCROLLBAR_AUTO | wx.BORDER_SIMPLE)
        self.hover_html.SetBackgroundColour(wx.Colour(250, 250, 250))
        self._set_hover_html("<span style='color: #666;'>Hover over plot to see values</span>")

        # Connect mouse motion event
        self.canvas.mpl_connect('motion_notify_event', self._on_mouse_move)

        right_sizer.Add(self.toolbar, 0, wx.EXPAND)
        right_sizer.Add(self.canvas, 1, wx.EXPAND)
        right_sizer.Add(self.hover_html, 0, wx.EXPAND)

        right_panel.SetSizer(right_sizer)

        # Configure splitter
        splitter.SplitVertically(left_panel, right_panel, 380)
        splitter.SetMinimumPaneSize(350)

        main_sizer = wx.BoxSizer(wx.HORIZONTAL)
        main_sizer.Add(splitter, 1, wx.EXPAND)
        self.SetSizer(main_sizer)

    def _create_checkboxes(self, parent_sizer: wx.BoxSizer):
        """Create checkboxes organized by category."""
        categories: Dict[str, List[Tuple]] = {}
        for field in DATA_FIELDS:
            cat = field[2]
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(field)

        for cat_name, fields in categories.items():
            # Category header
            header = wx.StaticText(self.scroll_panel, label=cat_name)
            header.SetFont(header.GetFont().Bold())
            parent_sizer.Add(header, 0, wx.TOP | wx.BOTTOM, 5)

            for path, name, _, unit in fields:
                key = ".".join(path)
                label = f"{name}" + (f" ({unit})" if unit else "")

                # Row with checkbox, secondary axis toggle, and style button
                row_sizer = wx.BoxSizer(wx.HORIZONTAL)

                cb = wx.CheckBox(self.scroll_panel, label=label)
                cb.Bind(wx.EVT_CHECKBOX, lambda e: self._update_plot())
                self.field_checkboxes[key] = cb
                row_sizer.Add(cb, 1, wx.ALIGN_CENTER_VERTICAL)

                cb2 = wx.CheckBox(self.scroll_panel, label="2nd")
                cb2.SetToolTip("Plot on secondary Y-axis")
                cb2.Bind(wx.EVT_CHECKBOX, lambda e: self._update_plot())
                self.field_secondary[key] = cb2
                row_sizer.Add(cb2, 0, wx.LEFT | wx.ALIGN_CENTER_VERTICAL, 5)

                # Style button
                btn_style = wx.Button(self.scroll_panel, label="\u2699", size=(36, -1))
                btn_style.SetToolTip("Customize line style")
                btn_style.Bind(wx.EVT_BUTTON, lambda e, k=key, n=name: self._open_style_dialog(k, n))
                row_sizer.Add(btn_style, 0, wx.LEFT | wx.ALIGN_CENTER_VERTICAL, 3)

                parent_sizer.Add(row_sizer, 0, wx.EXPAND | wx.LEFT, 15)

        # Default selections
        defaults = ["shot.pressure", "shot.flow", "shot.weight"]
        for key in defaults:
            if key in self.field_checkboxes:
                self.field_checkboxes[key].SetValue(True)

    def _auto_load_json_files(self):
        """Auto-load the 2 most recent JSON files based on datetime inside JSON."""
        script_dir = Path(__file__).parent
        json_files = list(script_dir.glob("*.shot.json"))

        # Read time from each JSON and sort by it (most recent first)
        files_with_time = []
        for path in json_files:
            try:
                with path.open("r", encoding="utf-8") as f:
                    doc = json.load(f)
                shot_time = doc.get("time", 0)
                files_with_time.append((path, shot_time))
            except Exception as e:
                print(f"Failed to read time from {path}: {e}")

        # Sort by time descending (most recent first)
        files_with_time.sort(key=lambda x: x[1], reverse=True)

        if len(files_with_time) >= 1:
            try:
                self.shot1 = ShotData(files_with_time[0][0])
                self.shot1_label.SetLabel(self.shot1.get_date_label())
                self.btn_settings1.Enable(True)
                self.shot1_settings = {}
            except Exception as e:
                print(f"Failed to load {files_with_time[0][0]}: {e}")

        if len(files_with_time) >= 2:
            try:
                self.shot2 = ShotData(files_with_time[1][0])
                self.shot2_label.SetLabel(self.shot2.get_date_label())
                self.btn_settings2.Enable(True)
                self.shot2_settings = {}
            except Exception as e:
                print(f"Failed to load {files_with_time[1][0]}: {e}")

        self._update_plot()

    def _load_file(self, slot: int):
        """Load a JSON file into slot 1 or 2."""
        with wx.FileDialog(
            self,
            f"Load Shot {slot}",
            wildcard="Shot JSON (*.shot.json)|*.shot.json|JSON files (*.json)|*.json|All files (*.*)|*.*",
            defaultDir=str(Path(__file__).parent),
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST
        ) as dlg:
            if dlg.ShowModal() == wx.ID_CANCEL:
                return

            path = Path(dlg.GetPath())

        try:
            shot = ShotData(path)
            if slot == 1:
                self.shot1 = shot
                self.shot1_label.SetLabel(shot.get_date_label())
                self.btn_settings1.Enable(True)
                self.shot1_settings = {}
            else:
                self.shot2 = shot
                self.shot2_label.SetLabel(shot.get_date_label())
                self.btn_settings2.Enable(True)
                self.shot2_settings = {}
            self._update_plot()
        except Exception as e:
            wx.MessageBox(f"Failed to load file:\n{e}", "Error", wx.OK | wx.ICON_ERROR)

    def _clear_file(self, slot: int):
        """Clear a loaded file."""
        if slot == 1:
            self.shot1 = None
            self.shot1_label.SetLabel("(none)")
            self.btn_settings1.Enable(False)
            self.shot1_settings = {}
        else:
            self.shot2 = None
            self.shot2_label.SetLabel("(none)")
            self.btn_settings2.Enable(False)
            self.shot2_settings = {}
        self._update_plot()

    def _open_file_settings(self, slot: int):
        """Open file settings dialog for trim, etc."""
        if slot == 1:
            shot = self.shot1
            current_settings = self.shot1_settings
        else:
            shot = self.shot2
            current_settings = self.shot2_settings

        if not shot:
            return

        original_settings = current_settings.copy() if current_settings else {}

        def on_settings_change(new_settings):
            """Live preview callback."""
            if slot == 1:
                self.shot1_settings = new_settings
            else:
                self.shot2_settings = new_settings
            self._update_plot()

        dlg = FileSettingsDialog(self, shot, current_settings, on_change_callback=on_settings_change)
        dlg.ShowModal()

        if dlg.saved:
            new_settings = dlg.get_settings()
            if slot == 1:
                self.shot1_settings = new_settings
            else:
                self.shot2_settings = new_settings
        else:
            # Cancelled - restore original
            if slot == 1:
                self.shot1_settings = original_settings
            else:
                self.shot2_settings = original_settings

        self._update_plot()
        dlg.Destroy()

    def _open_style_dialog(self, key: str, name: str):
        """Open dialog to customize line style."""
        current_style = self.field_styles.get(key, {})
        original_style = current_style.copy() if current_style else {}

        def on_style_change(new_style):
            """Live preview callback."""
            if new_style:
                self.field_styles[key] = new_style
            elif key in self.field_styles:
                del self.field_styles[key]
            self._update_plot()

        dlg = StyleDialog(self, name, current_style, on_change_callback=on_style_change)
        dlg.ShowModal()

        if dlg.saved:
            # Save or Defaults was clicked - apply final style
            new_style = dlg.get_style()
            if new_style:
                self.field_styles[key] = new_style
            elif key in self.field_styles:
                del self.field_styles[key]
        else:
            # Cancelled or closed - restore original style
            if original_style:
                self.field_styles[key] = original_style
            elif key in self.field_styles:
                del self.field_styles[key]

        self._update_plot()
        dlg.Destroy()

    def _select_all(self):
        for cb in self.field_checkboxes.values():
            cb.SetValue(True)
        self._update_plot()

    def _select_none(self):
        for cb in self.field_checkboxes.values():
            cb.SetValue(False)
        self._update_plot()

    def _select_shot(self):
        for cb in self.field_checkboxes.values():
            cb.SetValue(False)
        for key in ["shot.pressure", "shot.flow", "shot.weight", "shot.gravimetric_flow",
                    "shot.setpoints.pressure", "shot.setpoints.flow", "shot.setpoints.power"]:
            if key in self.field_checkboxes:
                self.field_checkboxes[key].SetValue(True)
        self._update_plot()

    def _select_temps(self):
        for cb in self.field_checkboxes.values():
            cb.SetValue(False)
        for key, cb in self.field_checkboxes.items():
            if "temp" in key.lower() or key.startswith("sensors.external") or key.startswith("sensors.bar") or key == "sensors.tube":
                cb.SetValue(True)
        self._update_plot()

    def _get_selected_fields(self) -> List[Tuple[List[str], str, str, bool]]:
        """Get list of selected fields as (path, name, unit, is_secondary)."""
        selected = []
        for path, name, _, unit in DATA_FIELDS:
            key = ".".join(path)
            if self.field_checkboxes.get(key, wx.CheckBox()).GetValue():
                is_secondary = self.field_secondary.get(key, wx.CheckBox()).GetValue()
                selected.append((path, name, unit, is_secondary))
        return selected

    def _update_plot(self):
        """Redraw the plot."""
        self.fig.clear()
        self.ax = self.fig.add_subplot(111)

        if not self.shot1 and not self.shot2:
            self.ax.set_title("No data loaded")
            self.plot_data = {}
            self.canvas.draw()
            return

        selected = self._get_selected_fields()
        if not selected:
            self.ax.set_title("No data series selected")
            self.plot_data = {}
            self.canvas.draw()
            return

        compare = self.compare_cb.GetValue() and self.shot1 and self.shot2

        # Check if we need secondary axis
        has_secondary = any(is_sec for _, _, _, is_sec in selected)
        ax2 = self.ax.twinx() if has_secondary else None

        # Color cycle
        colors = plt.cm.tab10.colors

        # Helper to get trimmed data
        def get_trimmed_data(shot, settings):
            trim_duration = settings.get("trim_duration", shot.time_s[-1] if shot.time_s else 0)
            # Find index where time exceeds trim_duration
            trim_idx = len(shot.time_s)
            for i, t in enumerate(shot.time_s):
                if t > trim_duration:
                    trim_idx = i
                    break
            return trim_idx

        if compare:
            # Get trim indices
            trim1 = get_trimmed_data(self.shot1, self.shot1_settings)
            trim2 = get_trimmed_data(self.shot2, self.shot2_settings)
            time1 = self.shot1.time_s[:trim1]
            time2 = self.shot2.time_s[:trim2]

            # Store data for hover
            self.plot_data = {
                "compare": True,
                "shot1_name": self.shot1.get_short_name(),
                "shot2_name": self.shot2.get_short_name(),
                "time1": time1,
                "time2": time2,
                "series1": {},
                "series2": {},
                "fields": []
            }

            # Overlay mode: same field, different shots
            for i, (path, name, unit, is_secondary) in enumerate(selected):
                key = ".".join(path)
                style = self.field_styles.get(key, {})
                color = style.get("color") or colors[i % len(colors)]
                linestyle = style.get("linestyle", "-")
                linewidth = style.get("linewidth", 1.5)
                target_ax = ax2 if is_secondary else self.ax

                # Shot 1 (solid style from settings)
                series1 = self.shot1.get_series(path)[:trim1]
                label1 = f"{name} ({self.shot1.get_short_name()})" + (" [2nd]" if is_secondary else "")
                target_ax.plot(time1, series1, label=label1, color=color,
                               linewidth=linewidth, linestyle=linestyle)

                # Shot 2 (dashed version)
                series2 = self.shot2.get_series(path)[:trim2]
                label2 = f"{name} ({self.shot2.get_short_name()})" + (" [2nd]" if is_secondary else "")
                # For comparison, shot2 uses dashed if shot1 is solid, or dotted if shot1 is already dashed
                ls2 = "--" if linestyle == "-" else ":"
                target_ax.plot(time2, series2, label=label2, color=color,
                               linewidth=linewidth, linestyle=ls2)

                # Store for hover (include color for display)
                # Convert matplotlib color to hex
                if isinstance(color, tuple):
                    hex_color = '#%02x%02x%02x' % tuple(int(c * 255) for c in color[:3])
                else:
                    hex_color = color
                self.plot_data["series1"][key] = series1
                self.plot_data["series2"][key] = series2
                self.plot_data["fields"].append((key, name, unit, hex_color))

            self.ax.set_title(f"Comparison: {self.shot1.get_short_name()} vs {self.shot2.get_short_name()}")
        else:
            # Single shot mode
            shot = self.shot1 or self.shot2
            settings = self.shot1_settings if self.shot1 else self.shot2_settings
            trim_idx = get_trimmed_data(shot, settings)
            time_trimmed = shot.time_s[:trim_idx]

            # Store data for hover
            self.plot_data = {
                "compare": False,
                "time": time_trimmed,
                "series": {},
                "fields": []
            }

            for i, (path, name, unit, is_secondary) in enumerate(selected):
                key = ".".join(path)
                style = self.field_styles.get(key, {})
                color = style.get("color") or colors[i % len(colors)]
                linestyle = style.get("linestyle", "-")
                linewidth = style.get("linewidth", 1.5)
                target_ax = ax2 if is_secondary else self.ax

                series = shot.get_series(path)[:trim_idx]
                label = f"{name}" + (f" ({unit})" if unit else "") + (" [2nd]" if is_secondary else "")
                target_ax.plot(time_trimmed, series, label=label, color=color,
                               linewidth=linewidth, linestyle=linestyle)

                # Store for hover (include color for display)
                if isinstance(color, tuple):
                    hex_color = '#%02x%02x%02x' % tuple(int(c * 255) for c in color[:3])
                else:
                    hex_color = color
                self.plot_data["series"][key] = series
                self.plot_data["fields"].append((key, name, unit, hex_color))

            self.ax.set_title(shot.get_title())

        self.ax.set_xlabel("Time (s)")
        self.ax.set_ylabel("Primary Axis")
        self.ax.grid(True, alpha=0.3)

        if ax2:
            ax2.set_ylabel("Secondary Axis")
            align_yaxis_zero(self.ax, ax2)

        # Combined legend at bottom
        lines1, labels1 = self.ax.get_legend_handles_labels()
        if ax2:
            lines2, labels2 = ax2.get_legend_handles_labels()
            all_lines = lines1 + lines2
            all_labels = labels1 + labels2
        else:
            all_lines = lines1
            all_labels = labels1

        # Place legend below the plot, full width
        ncol = min(len(all_lines), 4)  # Up to 4 columns
        self.fig.legend(all_lines, all_labels, loc='lower center', bbox_to_anchor=(0.5, 0),
                        ncol=ncol, fontsize=8, frameon=True)

        # Adjust layout to make room for legend
        self.fig.tight_layout()
        self.fig.subplots_adjust(bottom=0.15 + 0.03 * ((len(all_lines) - 1) // ncol))
        self.canvas.draw()

    def _set_hover_html(self, content):
        """Set HTML content in the hover panel."""
        html = f"""
        <html><body style="background-color: #fafafa; margin: 5px;">
        <font size="3" face="Arial, sans-serif">{content}</font>
        </body></html>
        """
        self.hover_html.SetPage(html)

    def _on_mouse_move(self, event):
        """Handle mouse movement over the plot to show values."""
        if not event.inaxes or not self.plot_data:
            self._set_hover_html("<span style='color: #666;'>Hover over plot to see values</span>")
            return

        x = event.xdata  # Time value
        if x is None:
            return

        def find_nearest_idx(time_array, target):
            """Find index of nearest time value."""
            if not time_array:
                return None
            best_idx = 0
            best_diff = abs(time_array[0] - target)
            for i, t in enumerate(time_array):
                diff = abs(t - target)
                if diff < best_diff:
                    best_diff = diff
                    best_idx = i
            return best_idx

        def format_value(val, unit):
            """Format a value with its unit."""
            if val is None or (isinstance(val, float) and (val != val)):  # NaN check
                return "N/A"
            return f"{val:.2f} {unit}" if unit else f"{val:.2f}"

        def color_square(hex_color):
            """Create an HTML colored square."""
            return f'<span style="background-color: {hex_color}; color: {hex_color}; border: 1px solid #333;">\u2588\u2588</span>'

        # Build HTML content
        lines = [f"<b>Time: {x:.2f}s</b>"]

        if self.plot_data.get("compare"):
            # Compare mode: show values from both shots
            idx1 = find_nearest_idx(self.plot_data["time1"], x)
            idx2 = find_nearest_idx(self.plot_data["time2"], x)
            s1_name = self.plot_data["shot1_name"]
            s2_name = self.plot_data["shot2_name"]

            for key, name, unit, hex_color in self.plot_data["fields"]:
                val1 = self.plot_data["series1"][key][idx1] if idx1 is not None and idx1 < len(self.plot_data["series1"][key]) else None
                val2 = self.plot_data["series2"][key][idx2] if idx2 is not None and idx2 < len(self.plot_data["series2"][key]) else None
                lines.append(
                    f"{color_square(hex_color)} <b>{name}:</b> "
                    f"{format_value(val1, unit)} ({s1_name}) | {format_value(val2, unit)} ({s2_name})"
                )
        else:
            # Single shot mode
            idx = find_nearest_idx(self.plot_data["time"], x)
            if idx is not None:
                for key, name, unit, hex_color in self.plot_data["fields"]:
                    series = self.plot_data["series"][key]
                    val = series[idx] if idx < len(series) else None
                    lines.append(f"{color_square(hex_color)} <b>{name}:</b> {format_value(val, unit)}")

        self._set_hover_html("<br>".join(lines))

    def _export_png(self):
        """Export current plot to PNG."""
        with wx.FileDialog(
            self,
            "Export PNG",
            wildcard="PNG files (*.png)|*.png",
            defaultDir=str(Path(__file__).parent),
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT
        ) as dlg:
            if dlg.ShowModal() == wx.ID_CANCEL:
                return

            path = dlg.GetPath()
            if not path.endswith(".png"):
                path += ".png"

        self.fig.savefig(path, dpi=200, bbox_inches="tight")
        wx.MessageBox(f"Saved to:\n{path}", "Export", wx.OK | wx.ICON_INFORMATION)

    def _save_session(self):
        """Save current session configuration to a JSON file."""
        with wx.FileDialog(
            self,
            "Save Session",
            wildcard="Session files (*.session.json)|*.session.json",
            defaultDir=str(Path(__file__).parent),
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT
        ) as dlg:
            if dlg.ShowModal() == wx.ID_CANCEL:
                return

            path = dlg.GetPath()
            if not path.endswith(".session.json"):
                path += ".session.json"

        # Build session state
        session = {
            "shot1_path": str(self.shot1.path) if self.shot1 else None,
            "shot2_path": str(self.shot2.path) if self.shot2 else None,
            "shot1_settings": self.shot1_settings,
            "shot2_settings": self.shot2_settings,
            "compare_mode": self.compare_cb.GetValue(),
            "field_checkboxes": {key: cb.GetValue() for key, cb in self.field_checkboxes.items()},
            "field_secondary": {key: cb.GetValue() for key, cb in self.field_secondary.items()},
            "field_styles": self.field_styles,
        }

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(session, f, indent=2)
            wx.MessageBox(f"Session saved to:\n{path}", "Save Session", wx.OK | wx.ICON_INFORMATION)
        except Exception as e:
            wx.MessageBox(f"Failed to save session:\n{e}", "Error", wx.OK | wx.ICON_ERROR)

    def _load_session(self):
        """Load session configuration from a JSON file."""
        with wx.FileDialog(
            self,
            "Load Session",
            wildcard="Session files (*.session.json)|*.session.json",
            defaultDir=str(Path(__file__).parent),
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST
        ) as dlg:
            if dlg.ShowModal() == wx.ID_CANCEL:
                return

            path = Path(dlg.GetPath())

        try:
            with path.open("r", encoding="utf-8") as f:
                session = json.load(f)
        except Exception as e:
            wx.MessageBox(f"Failed to read session file:\n{e}", "Error", wx.OK | wx.ICON_ERROR)
            return

        # Load shot files
        shot1_path = session.get("shot1_path")
        if shot1_path and Path(shot1_path).exists():
            try:
                self.shot1 = ShotData(Path(shot1_path))
                self.shot1_label.SetLabel(self.shot1.get_date_label())
                self.btn_settings1.Enable(True)
            except Exception as e:
                wx.MessageBox(f"Failed to load shot 1:\n{e}", "Warning", wx.OK | wx.ICON_WARNING)
                self.shot1 = None
                self.shot1_label.SetLabel("(none)")
                self.btn_settings1.Enable(False)
        else:
            self.shot1 = None
            self.shot1_label.SetLabel("(none)")
            self.btn_settings1.Enable(False)

        shot2_path = session.get("shot2_path")
        if shot2_path and Path(shot2_path).exists():
            try:
                self.shot2 = ShotData(Path(shot2_path))
                self.shot2_label.SetLabel(self.shot2.get_date_label())
                self.btn_settings2.Enable(True)
            except Exception as e:
                wx.MessageBox(f"Failed to load shot 2:\n{e}", "Warning", wx.OK | wx.ICON_WARNING)
                self.shot2 = None
                self.shot2_label.SetLabel("(none)")
                self.btn_settings2.Enable(False)
        else:
            self.shot2 = None
            self.shot2_label.SetLabel("(none)")
            self.btn_settings2.Enable(False)

        # Restore settings
        self.shot1_settings = session.get("shot1_settings", {})
        self.shot2_settings = session.get("shot2_settings", {})

        # Restore compare mode
        self.compare_cb.SetValue(session.get("compare_mode", False))

        # Restore checkbox states
        for key, value in session.get("field_checkboxes", {}).items():
            if key in self.field_checkboxes:
                self.field_checkboxes[key].SetValue(value)

        for key, value in session.get("field_secondary", {}).items():
            if key in self.field_secondary:
                self.field_secondary[key].SetValue(value)

        # Restore field styles
        self.field_styles = session.get("field_styles", {})

        # Update plot
        self._update_plot()


def main():
    app = wx.App()
    frame = ShotViewerFrame()
    frame.Show()
    app.MainLoop()


if __name__ == "__main__":
    main()
