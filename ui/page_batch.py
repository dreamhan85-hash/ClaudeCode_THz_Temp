"""Batch / temperature comparison analysis page."""

from __future__ import annotations

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

from thztds.types import ExtractionConfig, THzTimeDomainData, OpticalProperties
from thztds.optical_properties import (
    process_temperature_series,
    process_temperature_series_matched_ref,
    compute_temperature_averages,
)
from ui.plots import (
    _apply_common_layout,
    plot_temperature_comparison,
    plot_property_vs_temperature,
)


def render_batch_analysis(
    ref_data: THzTimeDomainData | None,
    sample_dict: dict[tuple[int, int], THzTimeDomainData],
    config: ExtractionConfig,
    analysis_method: str = "method2",
    ref_dict: dict[int, THzTimeDomainData] | None = None,
):
    """Render the batch / temperature comparison page."""
    st.header("Temperature Comparison Analysis")

    if analysis_method == "matched_ref":
        ref_temps = sorted(ref_dict.keys()) if ref_dict else []
        st.caption(f"📊 Matched Ref: H = E_sam(T)/E_ref(T) — 온도별 Ref 매칭 ({len(ref_temps)}개: {ref_temps}°C)")
    elif analysis_method == "method3":
        st.caption("📊 Method 3: Differential — H = E_sam(T)/E_sam(T_base), 상대 변화량 추출")
    else:
        st.caption("📊 Method 2: Air Ref + Correction — H = E_sam(T)/E_ref(20°C), 절대 물성 추출")

    # Get available temperatures
    all_temps = sorted(set(t for t, _ in sample_dict.keys()))

    if not all_temps:
        st.warning("No sample data loaded.")
        return

    st.info(
        f"Available: {len(sample_dict)} samples across "
        f"{len(all_temps)} temperatures ({min(all_temps)}°C - {max(all_temps)}°C)"
    )

    # Temperature selection
    selected_temps = st.multiselect(
        "Select Temperatures",
        all_temps,
        default=all_temps,
        format_func=lambda t: f"{t}°C",
    )

    if not selected_temps:
        st.warning("Please select at least one temperature.")
        return

    # Filter samples
    filtered_samples = {
        (t, r): d
        for (t, r), d in sample_dict.items()
        if t in selected_temps
    }

    show_mode = st.radio(
        "Display Mode",
        ["Average of replicates", "Individual replicates"],
        horizontal=True,
    )
    show_error = st.checkbox("Show error bars (std dev)", value=True)

    # Time-domain comparison (before extraction)
    st.subheader("Time-Domain Signals (Temperature Comparison)")

    # Pick a representative ref for time-domain plots
    td_ref = ref_data
    if td_ref is None and ref_dict:
        td_ref = ref_dict[min(ref_dict.keys())]

    if td_ref is not None:
        col_td1, col_td2 = st.columns(2)
        with col_td1:
            fig_td = _plot_time_domain_comparison(td_ref, filtered_samples)
            st.plotly_chart(fig_td, use_container_width=True)
        with col_td2:
            fig_td_delta = _plot_time_domain_delta(td_ref, filtered_samples)
            st.plotly_chart(fig_td_delta, use_container_width=True)

    # Run batch analysis
    if st.button("Run Batch Analysis", key="run_batch"):
        progress_bar = st.progress(0)
        status_text = st.empty()

        def progress_cb(current, total):
            progress_bar.progress(current / total)
            status_text.text(f"Processing sample {current}/{total}...")

        with st.spinner("Processing all samples..."):
            if analysis_method == "matched_ref" and ref_dict:
                results = process_temperature_series_matched_ref(
                    ref_dict, filtered_samples, config,
                    progress_callback=progress_cb,
                )
            else:
                results = process_temperature_series(
                    ref_data, filtered_samples, config,
                    progress_callback=progress_cb,
                    analysis_method=analysis_method,
                )

        progress_bar.progress(1.0)
        status_text.text("Batch processing complete!")

        st.session_state["batch_results"] = results
        st.session_state["batch_averages"] = compute_temperature_averages(results)
        st.session_state["batch_method"] = analysis_method

    # Display results
    if "batch_results" not in st.session_state:
        return

    results = st.session_state["batch_results"]
    averages = st.session_state["batch_averages"]
    used_method = st.session_state.get("batch_method", "method2")
    is_differential = (used_method == "method3")

    ref_temp = min(averages.keys())

    if is_differential:
        # Method 3: results are already relative (Δn, Δκ, Δα)
        st.info(f"Differential mode: values are relative to {ref_temp}°C sample baseline")

        st.subheader("Δn(f) — Refractive Index Change")
        if show_mode == "Average of replicates":
            fig_n = _plot_delta_to_air(averages, "n", show_error)
        else:
            fig_n = _plot_individual_delta_to_air(results, "n")
        st.plotly_chart(fig_n, use_container_width=True)

        st.subheader("Δκ(f) — Extinction Coefficient Change")
        if show_mode == "Average of replicates":
            fig_k = plot_temperature_comparison(averages, "kappa", show_error)
        else:
            fig_k = _plot_individual_comparison(results, "kappa")
        st.plotly_chart(fig_k, use_container_width=True)

        st.subheader("Δα(f) — Absorption Coefficient Change")
        if show_mode == "Average of replicates":
            fig_a = plot_temperature_comparison(averages, "alpha", show_error)
        else:
            fig_a = _plot_individual_comparison(results, "alpha")
        st.plotly_chart(fig_a, use_container_width=True)

    else:
        # Method 2: absolute values with delta toggle
        show_delta = st.checkbox(
            "Show Δ values (relative to air: Δn = n − 1, Δκ = κ, Δα = α)",
            value=False,
            key="batch_show_delta",
        )

        if show_delta:
            st.subheader("Δn(f) = n − 1")
            if show_mode == "Average of replicates":
                fig_n = _plot_delta_to_air(averages, "n", show_error)
            else:
                fig_n = _plot_individual_delta_to_air(results, "n")
            st.plotly_chart(fig_n, use_container_width=True)
        else:
            st.subheader("n(f) - Refractive Index")
            if show_mode == "Average of replicates":
                fig_n = plot_temperature_comparison(averages, "n", show_error)
            else:
                fig_n = _plot_individual_comparison(results, "n")
            st.plotly_chart(fig_n, use_container_width=True)

        st.subheader("κ(f) - Extinction Coefficient")
        if show_mode == "Average of replicates":
            fig_k = plot_temperature_comparison(averages, "kappa", show_error)
        else:
            fig_k = _plot_individual_comparison(results, "kappa")
        st.plotly_chart(fig_k, use_container_width=True)

        st.subheader("α(f) - Absorption Coefficient")
        if show_mode == "Average of replicates":
            fig_a = plot_temperature_comparison(averages, "alpha", show_error)
        else:
            fig_a = _plot_individual_comparison(results, "alpha")
        st.plotly_chart(fig_a, use_container_width=True)

    # Delta (change from reference temperature) plots
    st.markdown("---")
    st.subheader("Δ Values (Change from Reference Temperature)")
    st.caption(f"Reference temperature: {ref_temp}°C")

    if ref_temp in averages:
        col1, col2, col3 = st.columns(3)
        with col1:
            fig_dn = _plot_delta_comparison(averages, "n", ref_temp)
            st.plotly_chart(fig_dn, use_container_width=True)
        with col2:
            fig_dk = _plot_delta_comparison(averages, "kappa", ref_temp)
            st.plotly_chart(fig_dk, use_container_width=True)
        with col3:
            fig_da = _plot_delta_comparison(averages, "alpha", ref_temp)
            st.plotly_chart(fig_da, use_container_width=True)

    # Property vs Temperature at selected frequency
    st.markdown("---")
    st.subheader("Property vs Temperature (at selected frequency)")

    freq_options = averages[list(averages.keys())[0]].freq_thz
    freq_target = st.slider(
        "Select Frequency [THz]",
        float(freq_options[0]),
        float(freq_options[-1]),
        value=1.0,
        step=0.01,
        format="%.2f",
    )

    col1, col2 = st.columns(2)
    with col1:
        fig_n_t = plot_property_vs_temperature(averages, freq_target, "n")
        st.plotly_chart(fig_n_t, use_container_width=True)
    with col2:
        fig_a_t = plot_property_vs_temperature(averages, freq_target, "alpha")
        st.plotly_chart(fig_a_t, use_container_width=True)

    # Export
    st.markdown("---")
    st.subheader("Export Results")

    export_rows = []
    for (temp, rep), props in sorted(results.items()):
        for i in range(len(props.freq_hz)):
            export_rows.append(
                {
                    "temperature_c": temp,
                    "replicate": rep,
                    "frequency_thz": props.freq_thz[i],
                    "n": props.n[i],
                    "kappa": props.kappa[i],
                    "alpha_per_cm": props.alpha[i],
                }
            )
    df_export = pd.DataFrame(export_rows)
    csv = df_export.to_csv(index=False)
    st.download_button(
        "Download All Results (CSV)",
        csv,
        file_name="thz_batch_results.csv",
        mime="text/csv",
    )


def _plot_time_domain_comparison(
    ref_data: THzTimeDomainData,
    samples: dict[tuple[int, int], THzTimeDomainData],
) -> go.Figure:
    """Plot time-domain signals for each temperature (replicate 1 only) with reference."""
    fig = go.Figure()

    # Reference
    fig.add_trace(
        go.Scatter(
            x=ref_data.time_ps,
            y=ref_data.signal,
            name="Reference",
            line=dict(color="black", width=2, dash="dash"),
        )
    )

    temps = sorted(set(t for t, _ in samples.keys()))
    temp_min, temp_max = min(temps) if temps else 0, max(temps) if temps else 1

    for temp in temps:
        # Use replicate 1 for display
        key = (temp, 1)
        if key not in samples:
            key = next((k for k in samples if k[0] == temp), None)
            if key is None:
                continue
        data = samples[key]
        t = (temp - temp_min) / max(temp_max - temp_min, 1)
        r_c = int(255 * t)
        b_c = int(255 * (1 - t))
        color = f"rgb({r_c}, 50, {b_c})"

        fig.add_trace(
            go.Scatter(
                x=data.time_ps,
                y=data.signal,
                name=f"{temp}°C",
                line=dict(color=color, width=1),
            )
        )

    _apply_common_layout(fig,
        title="Time-Domain Signals by Temperature",
        xaxis_title="Time [ps]",
        yaxis_title="THz Signal [a.u.]",
    )
    return fig


def _plot_time_domain_delta(
    ref_data: THzTimeDomainData,
    samples: dict[tuple[int, int], THzTimeDomainData],
) -> go.Figure:
    """Plot Δ signal (sample - reference) for each temperature."""
    fig = go.Figure()

    temps = sorted(set(t for t, _ in samples.keys()))
    temp_min, temp_max = min(temps) if temps else 0, max(temps) if temps else 1

    for temp in temps:
        key = (temp, 1)
        if key not in samples:
            key = next((k for k in samples if k[0] == temp), None)
            if key is None:
                continue
        data = samples[key]
        delta_signal = data.signal - ref_data.signal

        t = (temp - temp_min) / max(temp_max - temp_min, 1)
        r_c = int(255 * t)
        b_c = int(255 * (1 - t))
        color = f"rgb({r_c}, 50, {b_c})"

        fig.add_trace(
            go.Scatter(
                x=data.time_ps,
                y=delta_signal,
                name=f"{temp}°C",
                line=dict(color=color, width=1),
            )
        )

    fig.add_hline(y=0, line_dash="dash", line_color="gray", line_width=1)
    _apply_common_layout(fig,
        title="ΔSignal (Sample − Reference)",
        xaxis_title="Time [ps]",
        yaxis_title="ΔSignal [a.u.]",
    )
    return fig


def _plot_individual_comparison(
    results: dict[tuple[int, int], OpticalProperties],
    property_name: str,
) -> go.Figure:
    """Plot individual replicates with temperature color coding."""
    fig = go.Figure()
    temps = sorted(set(t for t, _ in results.keys()))
    temp_min, temp_max = min(temps), max(temps)

    for (temp, rep), props in sorted(results.items()):
        t = (temp - temp_min) / max(temp_max - temp_min, 1)
        t = max(0.0, min(1.0, t))
        r_c = int(255 * t)
        b_c = int(255 * (1 - t))
        color = f"rgb({r_c}, 50, {b_c})"

        y_data = getattr(props, property_name)
        fig.add_trace(
            go.Scatter(
                x=props.freq_thz,
                y=y_data,
                name=f"{temp}°C-{rep}",
                line=dict(color=color, width=1),
                opacity=0.7,
            )
        )

    labels = {
        "n": "Refractive Index n",
        "kappa": "Extinction Coefficient κ",
        "alpha": "Absorption Coefficient α [1/cm]",
    }
    _apply_common_layout(fig,
        title=f"{labels.get(property_name, property_name)} (Individual Replicates)",
        xaxis_title="Frequency [THz]",
        yaxis_title=labels.get(property_name, property_name),
        xaxis_dtick=0.5,
    )
    return fig


def _plot_delta_comparison(
    averages: dict[int, OpticalProperties],
    property_name: str,
    ref_temp: int,
) -> go.Figure:
    """Plot Δproperty (change from reference temperature) vs frequency."""
    fig = go.Figure()
    ref_props = averages[ref_temp]
    ref_values = getattr(ref_props, property_name)

    temps = sorted(averages.keys())
    temp_min, temp_max = min(temps), max(temps)

    for temp in temps:
        if temp == ref_temp:
            continue
        props = averages[temp]
        y_data = getattr(props, property_name)
        delta = y_data - ref_values

        t = (temp - temp_min) / max(temp_max - temp_min, 1)
        r_c = int(255 * t)
        b_c = int(255 * (1 - t))
        color = f"rgb({r_c}, 50, {b_c})"

        fig.add_trace(
            go.Scatter(
                x=props.freq_thz,
                y=delta,
                name=f"{temp}°C",
                line=dict(color=color),
            )
        )

    # Add zero line
    fig.add_hline(y=0, line_dash="dash", line_color="gray", line_width=1)

    labels = {
        "n": "Δn",
        "kappa": "Δκ",
        "alpha": "Δα [1/cm]",
    }
    _apply_common_layout(fig,
        title=f"{labels.get(property_name, property_name)} (vs {ref_temp}°C)",
        xaxis_title="Frequency [THz]",
        yaxis_title=labels.get(property_name, property_name),
        xaxis_dtick=0.5,
    )
    return fig


def _plot_delta_to_air(
    averages: dict[int, OpticalProperties],
    property_name: str,
    show_error: bool = False,
) -> go.Figure:
    """Plot Δ values relative to air (Δn = n - 1) for averaged data."""
    fig = go.Figure()
    temps = sorted(averages.keys())
    temp_min, temp_max = min(temps), max(temps)

    for temp in temps:
        props = averages[temp]
        y_data = getattr(props, property_name)
        y_std = getattr(props, f"{property_name}_std", None)

        if property_name == "n":
            y_plot = y_data - 1.0
        else:
            y_plot = y_data

        t = (temp - temp_min) / max(temp_max - temp_min, 1)
        r_c = int(255 * t)
        b_c = int(255 * (1 - t))
        color = f"rgb({r_c}, 50, {b_c})"

        fig.add_trace(
            go.Scatter(
                x=props.freq_thz,
                y=y_plot,
                name=f"{temp}°C",
                line=dict(color=color),
            )
        )

        if show_error and y_std is not None:
            fig.add_trace(
                go.Scatter(
                    x=np.concatenate([props.freq_thz, props.freq_thz[::-1]]),
                    y=np.concatenate([y_plot + y_std, (y_plot - y_std)[::-1]]),
                    fill="toself",
                    fillcolor=color.replace("rgb", "rgba").replace(")", ", 0.15)"),
                    line=dict(width=0),
                    showlegend=False,
                    hoverinfo="skip",
                )
            )

    fig.add_hline(y=0, line_dash="dash", line_color="gray", line_width=1)

    labels = {"n": "Δn (n − 1)", "kappa": "κ", "alpha": "α [1/cm]"}
    _apply_common_layout(fig,
        title=f"{labels.get(property_name, property_name)} vs Temperature",
        xaxis_title="Frequency [THz]",
        yaxis_title=labels.get(property_name, property_name),
        xaxis_dtick=0.5,
    )
    return fig


def _plot_individual_delta_to_air(
    results: dict[tuple[int, int], OpticalProperties],
    property_name: str,
) -> go.Figure:
    """Plot Δ values relative to air for individual replicates."""
    fig = go.Figure()
    temps = sorted(set(t for t, _ in results.keys()))
    temp_min, temp_max = min(temps), max(temps)

    for (temp, rep), props in sorted(results.items()):
        y_data = getattr(props, property_name)
        if property_name == "n":
            y_plot = y_data - 1.0
        else:
            y_plot = y_data

        t = (temp - temp_min) / max(temp_max - temp_min, 1)
        t = max(0.0, min(1.0, t))
        r_c = int(255 * t)
        b_c = int(255 * (1 - t))
        color = f"rgb({r_c}, 50, {b_c})"

        fig.add_trace(
            go.Scatter(
                x=props.freq_thz,
                y=y_plot,
                name=f"{temp}°C-{rep}",
                line=dict(color=color, width=1),
                opacity=0.7,
            )
        )

    fig.add_hline(y=0, line_dash="dash", line_color="gray", line_width=1)

    labels = {"n": "Δn (n − 1)", "kappa": "κ", "alpha": "α [1/cm]"}
    _apply_common_layout(fig,
        title=f"{labels.get(property_name, property_name)} (Individual Replicates)",
        xaxis_title="Frequency [THz]",
        yaxis_title=labels.get(property_name, property_name),
        xaxis_dtick=0.5,
    )
    return fig
