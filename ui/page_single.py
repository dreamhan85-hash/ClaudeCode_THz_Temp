"""Single sample analysis page."""

from __future__ import annotations

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

from thztds.types import ExtractionConfig, THzTimeDomainData
from thztds.signal import apply_window, compute_fft
from thztds.transfer_function import compute_measured_transfer_function
from thztds.optical_properties import process_single_measurement
from ui.plots import (
    _apply_common_layout,
    plot_time_domain,
    plot_frequency_amplitude,
    plot_frequency_phase,
    plot_transfer_function,
    plot_refractive_index,
    plot_extinction_coefficient,
    plot_absorption_coefficient,
)


def _plot_delta_time_domain(
    ref_data: THzTimeDomainData, sample_data: THzTimeDomainData
) -> go.Figure:
    """Plot ΔSignal = sample - reference in time domain."""
    delta = sample_data.signal - ref_data.signal
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=sample_data.time_ps,
            y=delta,
            name="ΔSignal",
            line=dict(color="green"),
        )
    )
    fig.add_hline(y=0, line_dash="dash", line_color="gray", line_width=1)
    _apply_common_layout(fig,
        title="ΔSignal (Sample − Reference)",
        xaxis_title="Time [ps]",
        yaxis_title="ΔSignal [a.u.]",
    )
    return fig


def render_single_analysis(
    ref_data: THzTimeDomainData,
    sample_data: THzTimeDomainData,
    config: ExtractionConfig,
):
    """Render the single sample analysis page."""
    st.header("Single Sample Analysis")

    sample_name = sample_data.metadata.get("filename", "Sample")
    st.info(f"Sample: **{sample_name}**")

    # Time-domain plot
    st.subheader("Time Domain")
    col_td1, col_td2 = st.columns(2)
    with col_td1:
        fig_td = plot_time_domain(ref_data, sample_data)
        st.plotly_chart(fig_td, use_container_width=True)
    with col_td2:
        fig_td_delta = _plot_delta_time_domain(ref_data, sample_data)
        st.plotly_chart(fig_td_delta, use_container_width=True)

    # Frequency-domain plots
    st.subheader("Frequency Domain")
    ref_windowed = apply_window(ref_data, config.window_type)
    sample_windowed = apply_window(sample_data, config.window_type)
    ref_freq = compute_fft(ref_windowed, config.zero_pad_factor)
    sample_freq = compute_fft(sample_windowed, config.zero_pad_factor)

    col1, col2 = st.columns(2)
    with col1:
        fig_amp = plot_frequency_amplitude(ref_freq, sample_freq)
        st.plotly_chart(fig_amp, use_container_width=True)
    with col2:
        fig_phase = plot_frequency_phase(ref_freq, sample_freq)
        st.plotly_chart(fig_phase, use_container_width=True)

    # Transfer function
    st.subheader("Transfer Function")
    H_meas = compute_measured_transfer_function(ref_freq, sample_freq)
    fig_h_amp, fig_h_phase = plot_transfer_function(ref_freq.freq_thz, H_meas)

    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(fig_h_amp, use_container_width=True)
    with col2:
        st.plotly_chart(fig_h_phase, use_container_width=True)

    # Optical property extraction
    st.subheader("Optical Property Extraction")

    if st.button("Run Extraction", key="run_single"):
        progress_bar = st.progress(0)
        status_text = st.empty()

        def progress_cb(current, total):
            progress_bar.progress(current / total)
            status_text.text(f"Processing frequency {current}/{total}...")

        with st.spinner("Extracting optical properties..."):
            props = process_single_measurement(
                ref_data, sample_data, config, progress_callback=progress_cb
            )

        progress_bar.progress(1.0)
        status_text.text("Extraction complete!")
        st.session_state["single_result"] = props

    if "single_result" in st.session_state:
        props = st.session_state["single_result"]

        # Toggle: absolute values vs delta (relative to n_air=1, kappa=0)
        show_delta = st.checkbox(
            "Show Δ values (relative to air: Δn = n − 1, Δκ = κ, Δα = α)",
            value=False,
            key="single_show_delta",
        )

        if show_delta:
            # Delta: n relative to air (n_air = 1)
            delta_n = props.n - 1.0
            col1, col2 = st.columns(2)
            with col1:
                fig_dn = go.Figure()
                fig_dn.add_trace(go.Scatter(
                    x=props.freq_thz, y=delta_n,
                    name="Δn = n − 1", line=dict(color="darkblue"),
                ))
                fig_dn.add_hline(y=0, line_dash="dash", line_color="gray")
                _apply_common_layout(fig_dn,
                    title="Δn (n − 1)",
                    xaxis_title="Frequency [THz]",
                    yaxis_title="Δn",
                    xaxis_dtick=0.5,
                )
                st.plotly_chart(fig_dn, use_container_width=True)
            with col2:
                fig_kappa = plot_extinction_coefficient(props)
                st.plotly_chart(fig_kappa, use_container_width=True)

            fig_alpha = plot_absorption_coefficient(props)
            st.plotly_chart(fig_alpha, use_container_width=True)
        else:
            col1, col2 = st.columns(2)
            with col1:
                fig_n = plot_refractive_index(props)
                st.plotly_chart(fig_n, use_container_width=True)
            with col2:
                fig_kappa = plot_extinction_coefficient(props)
                st.plotly_chart(fig_kappa, use_container_width=True)

            fig_alpha = plot_absorption_coefficient(props)
            st.plotly_chart(fig_alpha, use_container_width=True)

        # Summary table
        st.subheader("Results Table")
        df = pd.DataFrame(
            {
                "Frequency [THz]": props.freq_thz,
                "n": props.n,
                "Δn (n−1)": props.n - 1.0,
                "κ": props.kappa,
                "α [1/cm]": props.alpha,
            }
        )
        st.dataframe(df, use_container_width=True)

        # Export
        csv = df.to_csv(index=False)
        st.download_button(
            "Download CSV",
            csv,
            file_name=f"thz_results_{sample_name}.csv",
            mime="text/csv",
        )
