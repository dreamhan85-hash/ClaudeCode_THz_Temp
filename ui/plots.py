"""Plotly figure-building functions for THz-TDS visualization."""

from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from thztds.types import (
    THzTimeDomainData,
    THzFrequencyDomainData,
    OpticalProperties,
)


# ── Shared layout ────────────────────────────────────────────────────────────

_GRID = dict(showgrid=True, gridcolor="rgba(0,0,0,0.12)", gridwidth=1)
_FONT = dict(family="Arial, sans-serif", size=13)
_TITLE_FONT = dict(size=14)

def _apply_common_layout(fig: go.Figure, **overrides) -> go.Figure:
    """Apply unified grid, tick, and font settings to a figure."""
    base = dict(
        template="plotly_white",
        font=_FONT,
        title_font=_TITLE_FONT,
        margin=dict(l=60, r=20, t=40, b=50),
        legend=dict(
            font=dict(size=11),
            bordercolor="rgba(0,0,0,0.15)",
            borderwidth=1,
        ),
        xaxis=dict(
            **_GRID,
            showline=True, linecolor="black", linewidth=1,
            mirror=True,
            ticks="outside", ticklen=4,
            minor=dict(showgrid=True, gridcolor="rgba(0,0,0,0.06)", griddash="dot"),
        ),
        yaxis=dict(
            **_GRID,
            showline=True, linecolor="black", linewidth=1,
            mirror=True,
            ticks="outside", ticklen=4,
            minor=dict(showgrid=True, gridcolor="rgba(0,0,0,0.06)", griddash="dot"),
        ),
    )
    base.update(overrides)
    fig.update_layout(**base)
    return fig


# ── Color helper ─────────────────────────────────────────────────────────────

def _temp_color(temp: float, temp_min: float = 20, temp_max: float = 110) -> str:
    t = (temp - temp_min) / max(temp_max - temp_min, 1)
    t = max(0.0, min(1.0, t))
    r = int(255 * t)
    b = int(255 * (1 - t))
    return f"rgb({r}, 50, {b})"


# ── Time-domain plots ────────────────────────────────────────────────────────

def plot_time_domain(
    ref: THzTimeDomainData,
    sample: THzTimeDomainData,
    title: str = "Time-Domain Signals",
) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=ref.time_ps, y=ref.signal,
        name="Reference", line=dict(color="blue"),
    ))
    fig.add_trace(go.Scatter(
        x=sample.time_ps, y=sample.signal,
        name="Sample", line=dict(color="red"),
    ))
    _apply_common_layout(fig,
        title=title,
        xaxis_title="Time [ps]",
        yaxis_title="THz Signal [a.u.]",
    )
    return fig


# ── Frequency-domain plots ───────────────────────────────────────────────────

def plot_frequency_amplitude(
    ref: THzFrequencyDomainData,
    sample: THzFrequencyDomainData,
    freq_max_thz: float = 5.0,
) -> go.Figure:
    mask = ref.freq_thz <= freq_max_thz
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=ref.freq_thz[mask], y=ref.amplitude[mask],
        name="Reference", line=dict(color="blue"),
    ))
    fig.add_trace(go.Scatter(
        x=sample.freq_thz[mask], y=sample.amplitude[mask],
        name="Sample", line=dict(color="red"),
    ))
    _apply_common_layout(fig,
        title="Frequency-Domain Amplitude",
        xaxis_title="Frequency [THz]",
        yaxis_title="Amplitude",
        xaxis_dtick=0.5,
    )
    return fig


def plot_frequency_phase(
    ref: THzFrequencyDomainData,
    sample: THzFrequencyDomainData,
    freq_max_thz: float = 5.0,
) -> go.Figure:
    mask = ref.freq_thz <= freq_max_thz
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=ref.freq_thz[mask], y=ref.phase[mask],
        name="Reference", line=dict(color="blue"),
    ))
    fig.add_trace(go.Scatter(
        x=sample.freq_thz[mask], y=sample.phase[mask],
        name="Sample", line=dict(color="red"),
    ))
    _apply_common_layout(fig,
        title="Frequency-Domain Phase (Unwrapped)",
        xaxis_title="Frequency [THz]",
        yaxis_title="Phase [rad]",
        xaxis_dtick=0.5,
    )
    return fig


# ── Transfer function plots ──────────────────────────────────────────────────

def plot_transfer_function(
    freq_thz: np.ndarray, H_meas: np.ndarray
) -> tuple[go.Figure, go.Figure]:
    valid = ~np.isnan(H_meas)
    freq_v = freq_thz[valid]

    fig_amp = go.Figure()
    fig_amp.add_trace(go.Scatter(
        x=freq_v, y=np.abs(H_meas[valid]),
        name="|H_meas|", line=dict(color="green"),
    ))
    _apply_common_layout(fig_amp,
        title="Transfer Function Amplitude",
        xaxis_title="Frequency [THz]",
        yaxis_title="|H(\u03c9)|",
        xaxis_dtick=0.5,
    )

    fig_phase = go.Figure()
    fig_phase.add_trace(go.Scatter(
        x=freq_v, y=np.unwrap(np.angle(H_meas[valid])),
        name="\u2220H_meas", line=dict(color="green"),
    ))
    _apply_common_layout(fig_phase,
        title="Transfer Function Phase",
        xaxis_title="Frequency [THz]",
        yaxis_title="Phase [rad]",
        xaxis_dtick=0.5,
    )
    return fig_amp, fig_phase


# ── Single-sample optical property plots ─────────────────────────────────────

def plot_refractive_index(props: OpticalProperties) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=props.freq_thz, y=props.n,
        name="n", line=dict(color="darkblue"),
    ))
    _apply_common_layout(fig,
        title="Refractive Index n(f)",
        xaxis_title="Frequency [THz]",
        yaxis_title="n",
        xaxis_dtick=0.5,
    )
    return fig


def plot_extinction_coefficient(props: OpticalProperties) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=props.freq_thz, y=props.kappa,
        name="\u03ba", line=dict(color="darkred"),
    ))
    _apply_common_layout(fig,
        title="Extinction Coefficient \u03ba(f)",
        xaxis_title="Frequency [THz]",
        yaxis_title="\u03ba",
        xaxis_dtick=0.5,
    )
    return fig


def plot_absorption_coefficient(props: OpticalProperties) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=props.freq_thz, y=props.alpha,
        name="\u03b1", line=dict(color="darkgreen"),
    ))
    _apply_common_layout(fig,
        title="Absorption Coefficient \u03b1(f)",
        xaxis_title="Frequency [THz]",
        yaxis_title="\u03b1 [1/cm]",
        xaxis_dtick=0.5,
    )
    return fig


# ── Temperature comparison plots ─────────────────────────────────────────────

def plot_temperature_comparison(
    results: dict[int, OpticalProperties],
    property_name: str,
    show_error: bool = False,
) -> go.Figure:
    """Overlay curves for multiple temperatures."""
    fig = go.Figure()
    temps = sorted(results.keys())
    temp_min, temp_max = min(temps), max(temps)

    for temp in temps:
        props = results[temp]
        y_data = getattr(props, property_name)
        y_std = getattr(props, f"{property_name}_std", None)
        color = _temp_color(temp, temp_min, temp_max)

        fig.add_trace(go.Scatter(
            x=props.freq_thz, y=y_data,
            name=f"{temp}\u00b0C", line=dict(color=color),
        ))

        if show_error and y_std is not None:
            fig.add_trace(go.Scatter(
                x=np.concatenate([props.freq_thz, props.freq_thz[::-1]]),
                y=np.concatenate([y_data + y_std, (y_data - y_std)[::-1]]),
                fill="toself",
                fillcolor=color.replace("rgb", "rgba").replace(")", ", 0.15)"),
                line=dict(width=0),
                showlegend=False, hoverinfo="skip",
            ))

    labels = {
        "n": "Refractive Index n",
        "kappa": "Extinction Coefficient \u03ba",
        "alpha": "Absorption Coefficient \u03b1 [1/cm]",
    }
    _apply_common_layout(fig,
        title=f"{labels.get(property_name, property_name)} vs Temperature",
        xaxis_title="Frequency [THz]",
        yaxis_title=labels.get(property_name, property_name),
        xaxis_dtick=0.5,
    )
    return fig


def plot_property_vs_temperature(
    results: dict[int, OpticalProperties],
    freq_thz_target: float,
    property_name: str,
) -> go.Figure:
    """Plot a single-frequency property against temperature."""
    temps = []
    values = []
    errors = []

    for temp in sorted(results.keys()):
        props = results[temp]
        idx = np.argmin(np.abs(props.freq_thz - freq_thz_target))
        y_data = getattr(props, property_name)
        y_std = getattr(props, f"{property_name}_std", None)

        temps.append(temp)
        values.append(y_data[idx])
        errors.append(y_std[idx] if y_std is not None else 0)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=temps, y=values,
        mode="lines+markers",
        name=f"{property_name} @ {freq_thz_target:.2f} THz",
        error_y=dict(type="data", array=errors, visible=True)
            if any(e > 0 for e in errors) else None,
        line=dict(color="darkblue"),
        marker=dict(size=8),
    ))

    labels = {"n": "n", "kappa": "\u03ba", "alpha": "\u03b1 [1/cm]"}
    _apply_common_layout(fig,
        title=f"{labels.get(property_name, property_name)} @ {freq_thz_target:.2f} THz vs Temperature",
        xaxis_title="Temperature [\u00b0C]",
        yaxis_title=labels.get(property_name, property_name),
        xaxis_dtick=10,
    )
    return fig
