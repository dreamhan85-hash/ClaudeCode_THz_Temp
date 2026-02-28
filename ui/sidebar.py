"""Sidebar controls for THz-TDS analyzer."""

from __future__ import annotations

import streamlit as st
from pathlib import Path
from io import StringIO
import numpy as np

from thztds.types import ExtractionConfig, THzTimeDomainData
from thztds.io import parse_menlo_file, parse_filename_metadata


def _parse_uploaded_file(uploaded_file) -> THzTimeDomainData:
    """Parse a Streamlit UploadedFile into THzTimeDomainData."""
    content = uploaded_file.getvalue().decode("utf-8")
    lines = content.splitlines()

    metadata = {}
    data_lines = []

    for line in lines:
        if line.startswith("#"):
            # Parse metadata (simplified)
            pass
        else:
            data_lines.append(line)

    # Parse data using numpy
    import re

    time_ps = []
    signal = []
    for line in data_lines:
        parts = line.strip().split("\t")
        if len(parts) >= 2:
            try:
                time_ps.append(float(parts[0]))
                signal.append(float(parts[1]))
            except ValueError:
                continue

    metadata["filename"] = uploaded_file.name
    file_meta = parse_filename_metadata(uploaded_file.name)
    metadata.update(file_meta)

    return THzTimeDomainData(
        time_ps=np.array(time_ps),
        signal=np.array(signal),
        metadata=metadata,
    )


def render_sidebar():
    """Render sidebar controls and return configuration and data.

    Returns:
        config: ExtractionConfig
        ref_data: THzTimeDomainData or None
        sample_data_list: list of THzTimeDomainData
        data_source: "upload" or "directory"
    """
    st.sidebar.title("THz-TDS Analyzer")
    st.sidebar.markdown("---")

    # Data input mode
    st.sidebar.subheader("Data Input")
    data_source = st.sidebar.radio(
        "Data Source",
        ["Upload Files", "Local Directory"],
        label_visibility="collapsed",
    )

    ref_data = None
    sample_data_list = []

    if data_source == "Upload Files":
        ref_file = st.sidebar.file_uploader(
            "Reference Signal (.txt)",
            type=["txt"],
            key="ref_upload",
        )
        sample_files = st.sidebar.file_uploader(
            "Sample Signal(s) (.txt)",
            type=["txt"],
            accept_multiple_files=True,
            key="sample_upload",
        )

        if ref_file is not None:
            ref_data = _parse_uploaded_file(ref_file)
        if sample_files:
            for sf in sample_files:
                sample_data_list.append(_parse_uploaded_file(sf))

    else:  # Local Directory
        dir_path = st.sidebar.text_input(
            "Directory Path",
            value="MeaData",
            key="dir_path",
        )
        if dir_path and st.sidebar.button("Load Directory", key="load_dir"):
            from thztds.io import load_measurement_set

            p = Path(dir_path)
            if not p.is_absolute():
                p = Path.cwd() / p
            if p.exists():
                ref, samples = load_measurement_set(p)
                if ref is not None:
                    st.session_state["ref_data"] = ref
                    st.session_state["sample_dict"] = samples
                    st.sidebar.success(
                        f"Loaded reference + {len(samples)} samples"
                    )
                else:
                    st.sidebar.error("No reference file found in directory.")
            else:
                st.sidebar.error(f"Directory not found: {p}")

        # Retrieve from session state if already loaded
        if "ref_data" in st.session_state:
            ref_data = st.session_state["ref_data"]
        if "sample_dict" in st.session_state:
            sample_data_list = list(st.session_state["sample_dict"].values())

    st.sidebar.markdown("---")

    # Parameters
    st.sidebar.subheader("Analysis Parameters")
    thickness_mm = st.sidebar.number_input(
        "Sample Thickness [mm]",
        min_value=0.001,
        max_value=100.0,
        value=0.02,
        step=0.001,
        format="%.3f",
    )
    freq_min = st.sidebar.number_input(
        "Freq Min [THz]",
        min_value=0.01,
        max_value=5.0,
        value=0.2,
        step=0.05,
        format="%.2f",
    )
    freq_max = st.sidebar.number_input(
        "Freq Max [THz]",
        min_value=0.1,
        max_value=15.0,
        value=2.5,
        step=0.1,
        format="%.1f",
    )
    n_fp_echoes = st.sidebar.number_input(
        "Fabry-Perot Echoes (M)",
        min_value=0,
        max_value=10,
        value=0,
        step=1,
    )
    window_type = st.sidebar.selectbox(
        "Window Function",
        ["rectangular", "tukey", "hann", "hamming", "blackman"],
        index=0,
    )
    zp_options = {"No padding": 0, "Next power of 2": 1, "x2": 2, "x4": 4, "x8": 8}
    zp_label = st.sidebar.selectbox(
        "Zero-Padding",
        list(zp_options.keys()),
        index=0,
    )
    zero_pad_factor = zp_options[zp_label]

    st.sidebar.markdown("---")

    # Analysis method
    st.sidebar.subheader("Analysis Method")
    analysis_method = st.sidebar.radio(
        "Transfer Function Reference",
        ["Method 2: Air Ref + Correction", "Method 3: Differential (ΔSample)"],
        index=0,
        help=(
            "Method 2: H = E_sam(T)/E_ref(20°C) × air correction → 절대 물성\n"
            "Method 3: H = E_sam(T)/E_sam(T_base) → 상대 변화량 (공기 영향 상쇄)"
        ),
    )

    st.sidebar.markdown("---")

    # Air temperature correction
    st.sidebar.subheader("Optical Path Settings")
    apply_air_correction = st.sidebar.checkbox(
        "Apply air temperature correction",
        value=True,
        disabled=("Method 3" in analysis_method),
    )
    ref_temp_c = st.sidebar.number_input(
        "Reference Temperature [°C]",
        min_value=-50.0,
        max_value=200.0,
        value=20.0,
        step=1.0,
        format="%.0f",
    )
    chamber_length_cm = st.sidebar.number_input(
        "Chamber Length [cm]",
        min_value=0.1,
        max_value=100.0,
        value=1.0,
        step=0.1,
        format="%.1f",
    )
    total_path_cm = st.sidebar.number_input(
        "Total Optical Path [cm]",
        min_value=1.0,
        max_value=500.0,
        value=30.0,
        step=1.0,
        format="%.0f",
    )

    thin_film = st.sidebar.checkbox(
        "Thin-film approximation (d ≪ λ)",
        value=True,
        help="20μm 박막: Fresnel 반사 무시, n < 1 허용",
    )

    # Advanced settings
    with st.sidebar.expander("Advanced Settings"):
        n_init = st.number_input(
            "n Initial Guess",
            min_value=1.0,
            max_value=5.0,
            value=1.5,
            step=0.1,
            format="%.1f",
            key="n_init",
        )
        kappa_init = st.number_input(
            "κ Initial Guess",
            min_value=0.0,
            max_value=1.0,
            value=0.01,
            step=0.001,
            format="%.3f",
            key="kappa_init",
        )

    config = ExtractionConfig(
        thickness_mm=thickness_mm,
        freq_min_thz=freq_min,
        freq_max_thz=freq_max,
        n_fp_echoes=n_fp_echoes,
        window_type=window_type,
        zero_pad_factor=zero_pad_factor,
        n_initial_guess=n_init,
        kappa_initial_guess=kappa_init,
        thin_film=thin_film,
        ref_temperature_c=ref_temp_c,
        chamber_length_cm=chamber_length_cm,
        total_path_cm=total_path_cm,
        apply_air_correction=apply_air_correction,
    )

    method_key = "method3" if "Method 3" in analysis_method else "method2"
    return config, ref_data, sample_data_list, data_source, method_key
