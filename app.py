"""THz-TDS Optical Property Extraction Software - Streamlit Entry Point."""

import streamlit as st

st.set_page_config(
    page_title="THz-TDS Analyzer",
    page_icon="📡",
    layout="wide",
)

from ui.sidebar import render_sidebar
from ui.page_single import render_single_analysis
from ui.page_batch import render_batch_analysis


def main():
    config, ref_data, sample_data_list, data_source, analysis_method, ref_dict = render_sidebar()

    # Main area tabs
    tab_single, tab_batch = st.tabs(["Single Analysis", "Batch / Temperature"])

    with tab_single:
        if ref_data is None:
            st.info("Please load a reference signal from the sidebar.")
        elif not sample_data_list:
            st.info("Please load at least one sample signal from the sidebar.")
        else:
            # Let user select which sample to analyze
            if len(sample_data_list) == 1:
                selected_sample = sample_data_list[0]
            else:
                sample_names = [
                    s.metadata.get("filename", f"Sample {i+1}")
                    for i, s in enumerate(sample_data_list)
                ]
                selected_name = st.selectbox(
                    "Select Sample for Analysis", sample_names
                )
                idx = sample_names.index(selected_name)
                selected_sample = sample_data_list[idx]

            # For single analysis with matched ref, pick the matching temperature ref
            single_ref = ref_data
            if analysis_method == "matched_ref" and ref_dict:
                sam_temp = selected_sample.metadata.get("temperature_c")
                if sam_temp is not None and sam_temp in ref_dict:
                    single_ref = ref_dict[sam_temp]

            render_single_analysis(single_ref, selected_sample, config)

    with tab_batch:
        if ref_data is None and not ref_dict:
            st.info("Please load a reference signal from the sidebar.")
        elif data_source == "Upload Files":
            # Build sample dict from uploaded files
            if len(sample_data_list) < 2:
                st.info(
                    "Upload multiple sample files or use 'Local Directory' mode "
                    "for batch analysis."
                )
            else:
                sample_dict = {}
                for s in sample_data_list:
                    temp = s.metadata.get("temperature_c", 0)
                    rep = s.metadata.get("replicate", 1)
                    sample_dict[(temp, rep)] = s
                render_batch_analysis(
                    ref_data, sample_dict, config, analysis_method, ref_dict,
                )
        else:
            # Directory mode - use session state
            if "sample_dict" in st.session_state:
                render_batch_analysis(
                    ref_data, st.session_state["sample_dict"], config,
                    analysis_method, ref_dict,
                )
            else:
                st.info("Please load data from a directory using the sidebar.")


if __name__ == "__main__":
    main()
