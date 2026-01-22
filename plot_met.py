#!/usr/bin/env python3
"""
shot_plot.py — Plot espresso shot actuals + setpoint goals from a *.shot.json file.

Default behavior matches the latest graphic we made:
- X: time delta from first point (seconds)
- Left Y: pressure, flow, motor_speed + pressure/flow goals (if present)
- Right Y: motor_power + motor_power goal (if present)
- Goals are plotted whenever present in setpoints (multiple goals can coexist)

Input: JSON
Output: PNG at high resolution (default: 14x7 inches, 200 DPI)

Example:
  python shot_plot.py /path/to/07_27_36.shot.json -o out.png
"""

from __future__ import annotations

import argparse
import json
import math
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def _align_yaxis_zero(ax1, ax2):
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
        return
    if y1_min == 0 and y2_min == 0:
        return

    # Calculate negative/positive ratios
    ratio1 = -y1_min / y1_max if y1_max > 0 else float('inf')
    ratio2 = -y2_min / y2_max if y2_max > 0 else float('inf')

    # Use the larger ratio for both
    target_ratio = max(ratio1, ratio2)

    if y1_max > 0:
        ax1.set_ylim(-target_ratio * y1_max, y1_max)
    if y2_max > 0:
        ax2.set_ylim(-target_ratio * y2_max, y2_max)


def _safe_get(d: Dict[str, Any], path: List[str], default=float("nan")):
    cur: Any = d
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def _infer_time_scale_ms_to_s(times_raw: List[float]) -> float:
    """
    Returns multiplier to convert (t - t0) into seconds.
    Most shot files have 'time' in milliseconds.
    We'll infer based on typical step sizes.
    """
    if len(times_raw) < 2:
        return 1.0  # fallback

    # Use median delta to infer units
    deltas = [abs(times_raw[i] - times_raw[i - 1]) for i in range(1, len(times_raw))]
    deltas = [d for d in deltas if d > 0]
    if not deltas:
        return 1.0

    deltas_sorted = sorted(deltas)
    med = deltas_sorted[len(deltas_sorted) // 2]

    # Heuristic:
    # - If median delta is > ~5, likely milliseconds (e.g., 100–200ms ticks)
    # - If median delta is small fractional (<1), could already be seconds
    # - If time values are large epoch seconds, deltas might be 0.1–1.0 etc.
    if med >= 5:
        return 1.0 / 1000.0
    return 1.0  # assume already seconds


def load_shot_json(path: Path) -> Tuple[List[Dict[str, Any]], str, Optional[float]]:
    with path.open("r", encoding="utf-8") as f:
        doc = json.load(f)
    if "data" not in doc or not isinstance(doc["data"], list):
        raise ValueError("JSON does not contain top-level key 'data' as a list.")
    profile_name = doc.get("profile_name", "Unknown Profile")
    shot_time = doc.get("time", None)
    return doc["data"], profile_name, shot_time


def build_series(records: List[Dict[str, Any]]) -> Dict[str, List[float]]:
    times_raw = [float(r.get("time", 0.0)) for r in records]
    t0 = times_raw[0] if times_raw else 0.0
    to_seconds = _infer_time_scale_ms_to_s(times_raw)

    x = [(t - t0) * to_seconds for t in times_raw]

    # Actuals
    pressure = [float(_safe_get(r, ["shot", "pressure"])) for r in records]
    flow = [float(_safe_get(r, ["shot", "flow"])) for r in records]
    motor_speed = [float(_safe_get(r, ["sensors", "motor_speed"])) for r in records]
    motor_power = [float(_safe_get(r, ["sensors", "motor_power"])) for r in records]

    # Goals: plot whenever present (not just active), allow multiple
    goal_pressure = []
    goal_flow = []
    goal_power = []
    active = []

    for r in records:
        sp = _safe_get(r, ["shot", "setpoints"], default={})
        sp = sp if isinstance(sp, dict) else {}
        active.append(sp.get("active", None))

        goal_pressure.append(float(sp["pressure"]) if "pressure" in sp and sp["pressure"] is not None else float("nan"))
        goal_flow.append(float(sp["flow"]) if "flow" in sp and sp["flow"] is not None else float("nan"))
        goal_power.append(float(sp["power"]) if "power" in sp and sp["power"] is not None else float("nan"))

    return {
        "time_s": x,
        "pressure": pressure,
        "flow": flow,
        "motor_speed": motor_speed,
        "motor_power": motor_power,
        "goal_pressure": goal_pressure,
        "goal_flow": goal_flow,
        "goal_power": goal_power,
        "active": active,
    }


def plot_shot(
    series: Dict[str, List[float]],
    title: str,
    out_path: Path,
    dpi: int = 200,
    figsize: Tuple[float, float] = (14, 7),
    show_grid: bool = True,
    include_pressure: bool = True,
    include_flow: bool = True,
    include_motor_speed: bool = True,
    include_pressure_goal: bool = True,
    include_flow_goal: bool = True,
    include_motor_power: bool = True,
    include_motor_power_goal: bool = True,
) -> None:
    x = series["time_s"]

    fig, ax1 = plt.subplots(figsize=figsize, dpi=dpi)

    # Left axis: actuals
    if include_pressure:
        ax1.plot(x, series["pressure"], label="Pressure (actual)", linewidth=2)
    if include_flow:
        ax1.plot(x, series["flow"], label="Flow (actual)", linewidth=2)
    if include_motor_speed:
        ax1.plot(x, series["motor_speed"], label="Motor speed (actual)", linewidth=2)

    # Left axis: goals (as setpoints, whenever present)
    if include_pressure_goal:
        ax1.plot(x, series["goal_pressure"], label="Pressure goal (setpoint)", linestyle=":", linewidth=2)
    if include_flow_goal:
        ax1.plot(x, series["goal_flow"], label="Flow goal (setpoint)", linestyle=":", linewidth=2)

    ax1.set_xlabel("Time (s)")
    ax1.set_ylabel("Pressure / Flow / Motor speed")
    if show_grid:
        ax1.grid(True, alpha=0.3)

    # Right axis: motor power
    ax2 = ax1.twinx()
    if include_motor_power:
        ax2.plot(x, series["motor_power"], label="Motor power (actual)", linestyle="--", linewidth=2)
    if include_motor_power_goal:
        ax2.plot(x, series["goal_power"], label="Motor power goal (setpoint)", linestyle=":", linewidth=2)
    ax2.set_ylabel("Motor power")
    _align_yaxis_zero(ax1, ax2)

    # Legend combined
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="best", fontsize=9)

    plt.title(title)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, bbox_inches="tight")
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Plot shot JSON actuals + goals to a high-res PNG.")
    p.add_argument("json_path", type=Path, help="Path to *.shot.json file")
    p.add_argument(
        "-o",
        "--out",
        type=Path,
        default=None,
        help="Output PNG path. Default: <input_stem>_actuals_vs_goals.png in same folder.",
    )
    p.add_argument("--dpi", type=int, default=200, help="PNG DPI (default: 200)")
    p.add_argument("--width", type=float, default=14.0, help="Figure width in inches (default: 14)")
    p.add_argument("--height", type=float, default=7.0, help="Figure height in inches (default: 7)")
    p.add_argument("--title", type=str, default=None, help="Plot title override")
    p.add_argument("--no-grid", action="store_true", help="Disable grid")

    # Quick toggles (easy customization)
    p.add_argument("--no-pressure", action="store_true", help="Hide pressure (actual)")
    p.add_argument("--no-flow", action="store_true", help="Hide flow (actual)")
    p.add_argument("--no-motor-speed", action="store_true", help="Hide motor speed (actual)")
    p.add_argument("--no-pressure-goal", action="store_true", help="Hide pressure goal")
    p.add_argument("--no-flow-goal", action="store_true", help="Hide flow goal")
    p.add_argument("--no-motor-power", action="store_true", help="Hide motor power (actual)")
    p.add_argument("--no-motor-power-goal", action="store_true", help="Hide motor power goal")

    return p.parse_args()


def main() -> None:
    args = parse_args()
    records, profile_name, shot_time = load_shot_json(args.json_path)
    series = build_series(records)

    out_path = args.out
    if out_path is None:
        out_path = args.json_path.with_name(f"{args.json_path.stem}_actuals_vs_goals.png")

    if args.title:
        title = args.title
    else:
        if shot_time is not None:
            dt = datetime.fromtimestamp(shot_time)
            time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
        else:
            time_str = "Unknown Time"
        title = f"{profile_name} – {time_str}"

    plot_shot(
        series=series,
        title=title,
        out_path=out_path,
        dpi=args.dpi,
        figsize=(args.width, args.height),
        show_grid=not args.no_grid,
        include_pressure=not args.no_pressure,
        include_flow=not args.no_flow,
        include_motor_speed=not args.no_motor_speed,
        include_pressure_goal=not args.no_pressure_goal,
        include_flow_goal=not args.no_flow_goal,
        include_motor_power=not args.no_motor_power,
        include_motor_power_goal=not args.no_motor_power_goal,
    )

    print(f"Wrote: {out_path}")


if __name__ == "__main__":
    main()

