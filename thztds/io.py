"""File parsing and export for Menlo Systems THz-TDS data."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
from numpy.typing import NDArray
import pandas as pd

from .types import THzTimeDomainData, OpticalProperties


def parse_menlo_file(filepath: str | Path) -> THzTimeDomainData:
    """Parse a Menlo Systems ScanControl .txt file."""
    filepath = Path(filepath)
    metadata = {}

    with open(filepath, "r", encoding="utf-8") as f:
        header_lines = []
        for line in f:
            if line.startswith("#"):
                header_lines.append(line.strip())
            else:
                break

    # Extract metadata from headers
    for line in header_lines:
        match_ts = re.search(
            r"Start:\s*([-\d.]+)\s*ps.*Average over\s*(\d+)\s*waveforms.*Timestamp:\s*(\S+)",
            line,
        )
        if match_ts:
            metadata["start_ps"] = float(match_ts.group(1))
            metadata["n_averages"] = int(match_ts.group(2))
            metadata["timestamp"] = match_ts.group(3)

        match_shift = re.search(r"User time axis shift:\s*([-\d.]+)\s*ps", line)
        if match_shift:
            metadata["user_shift_ps"] = float(match_shift.group(1))

        match_offset = re.search(r"Time axis offset:\s*([-\d.]+)\s*ps", line)
        if match_offset:
            metadata["time_offset_ps"] = float(match_offset.group(1))

    # Load data
    data = np.loadtxt(filepath, comments="#")
    time_ps = data[:, 0]
    signal = data[:, 1]

    metadata["filename"] = filepath.name

    return THzTimeDomainData(time_ps=time_ps, signal=signal, metadata=metadata)


def parse_filename_metadata(filename: str) -> dict:
    """Extract temperature and replicate info from filename."""
    result = {"filename": filename, "is_reference": False}

    # Reference pattern: Ref_{temperature}.txt
    ref_match = re.match(r"Ref_(\d+)\.txt", filename)
    if ref_match:
        result["temperature_c"] = int(ref_match.group(1))
        result["is_reference"] = True
        return result

    # Sample pattern: PE20_{temperature}-{replicate}.txt
    sample_match = re.match(r"(\w+)_(\d+)-(\d+)\.txt", filename)
    if sample_match:
        result["material"] = sample_match.group(1)
        result["temperature_c"] = int(sample_match.group(2))
        result["replicate"] = int(sample_match.group(3))
        return result

    return result


def load_measurement_set(
    directory: str | Path,
) -> tuple[THzTimeDomainData | None, dict[tuple[int, int], THzTimeDomainData]]:
    """Load all files from a measurement directory.

    Returns:
        reference: THzTimeDomainData for Ref_*.txt (or None if not found)
            If multiple Ref files exist, returns the lowest-temperature one.
        samples: dict mapping (temperature, replicate) -> THzTimeDomainData
    """
    directory = Path(directory)
    references: dict[int, THzTimeDomainData] = {}
    samples: dict[tuple[int, int], THzTimeDomainData] = {}

    for filepath in sorted(directory.glob("*.txt")):
        if "_fft" in filepath.name:
            continue
        meta = parse_filename_metadata(filepath.name)
        if meta.get("is_reference"):
            data = parse_menlo_file(filepath)
            data.metadata.update(meta)
            references[meta["temperature_c"]] = data
        elif "temperature_c" in meta and "replicate" in meta:
            data = parse_menlo_file(filepath)
            data.metadata.update(meta)
            key = (meta["temperature_c"], meta["replicate"])
            samples[key] = data

    # Return lowest-temperature reference for backward compatibility
    reference = None
    if references:
        lowest_temp = min(references.keys())
        reference = references[lowest_temp]

    return reference, samples


def load_measurement_set_with_refs(
    directory: str | Path,
    exclude_temps: list[int] | None = None,
) -> tuple[dict[int, THzTimeDomainData], dict[tuple[int, int], THzTimeDomainData]]:
    """Load all files with per-temperature references.

    Args:
        directory: Path to measurement directory.
        exclude_temps: Temperatures to exclude (e.g., [20] if Ref_20 missing).

    Returns:
        references: dict mapping temperature -> THzTimeDomainData
        samples: dict mapping (temperature, replicate) -> THzTimeDomainData
    """
    directory = Path(directory)
    exclude = set(exclude_temps or [])
    references: dict[int, THzTimeDomainData] = {}
    samples: dict[tuple[int, int], THzTimeDomainData] = {}

    for filepath in sorted(directory.glob("*.txt")):
        if "_fft" in filepath.name:
            continue
        meta = parse_filename_metadata(filepath.name)
        temp = meta.get("temperature_c")

        if temp is not None and temp in exclude:
            continue

        if meta.get("is_reference"):
            data = parse_menlo_file(filepath)
            data.metadata.update(meta)
            references[temp] = data
        elif temp is not None and "replicate" in meta:
            data = parse_menlo_file(filepath)
            data.metadata.update(meta)
            key = (temp, meta["replicate"])
            samples[key] = data

    return references, samples


def export_results_csv(
    results: list[OpticalProperties], filepath: str | Path
) -> None:
    """Export optical properties to CSV."""
    rows = []
    for props in results:
        for i in range(len(props.freq_hz)):
            row = {
                "frequency_thz": props.freq_hz[i] / 1e12,
                "n": props.n[i],
                "kappa": props.kappa[i],
                "alpha_per_cm": props.alpha[i],
                "thickness_mm": props.thickness_mm,
            }
            if props.temperature_c is not None:
                row["temperature_c"] = props.temperature_c
            if props.replicate is not None:
                row["replicate"] = props.replicate
            rows.append(row)

    df = pd.DataFrame(rows)
    df.to_csv(filepath, index=False)
