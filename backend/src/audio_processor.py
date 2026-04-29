"""
Audio processing utilities for extracting perceptual features from Pokemon cries.
"""

import os

os.environ.setdefault("LIBROSA_CACHE_LEVEL", "0")
os.environ.setdefault("NUMBA_CACHE_DIR", "/tmp/numba_cache")

import numpy as np
import librosa
import subprocess
from scipy import signal
from pathlib import Path
from typing import Optional


# Informational only - no longer encoded in filenames.
# Increment when the feature layout changes; use `manage.py build --force`
# (which clears the vectors directory) to pick up the new format.
FEATURE_VERSION = 8

SHAPE_BANDS = 40
SHAPE_TIME_BINS = 24
SHAPE_AUTOCORR_LAGS = 18
AXIS_FEATURES = (
    "pitch_height",
    "pitch_stability",
    "tonality",
    "noisiness",
    "brightness",
    "attack",
    "sustain",
    "modulation",
    "sparkle",
    "duration",
)


def _l2_norm(v: np.ndarray) -> np.ndarray:
    """Return v scaled to unit length, or v unchanged if it is essentially zero."""
    norm = np.linalg.norm(v)
    return v / norm if norm > 1e-8 else v


def _center_and_norm(v: np.ndarray) -> np.ndarray:
    """Mean-center a feature group before L2 normalization."""
    centered = v - np.mean(v)
    return _l2_norm(centered)


def _feature_slices(n_mfcc: int = 16) -> dict[str, slice]:
    """Return the fixed slice layout used by the extracted feature vector."""
    mfcc_len = 10 * n_mfcc
    texture_len = 65
    pitch_len = 90
    pitch_contour_len = 6
    envelope_len = 11
    duration_len = 2
    axis_len = len(AXIS_FEATURES)
    shape_len = SHAPE_AUTOCORR_LAGS * SHAPE_TIME_BINS + SHAPE_TIME_BINS

    offset = 0
    slices = {
        "mfcc": slice(offset, offset + mfcc_len),
    }
    offset += mfcc_len
    slices["texture"] = slice(offset, offset + texture_len)
    offset += texture_len
    slices["pitch"] = slice(offset, offset + pitch_len)
    offset += pitch_len
    slices["pitch_contour"] = slice(offset, offset + pitch_contour_len)
    offset += pitch_contour_len
    slices["envelope"] = slice(offset, offset + envelope_len)
    offset += envelope_len
    slices["duration"] = slice(offset, offset + duration_len)
    offset += duration_len
    slices["axis"] = slice(offset, offset + axis_len)
    offset += axis_len
    slices["shape"] = slice(offset, offset + shape_len)
    return slices


def project_melodic_complexity_axes(
    vector: np.ndarray, n_mfcc: int = 16
) -> tuple[float, float]:
    """Project a feature vector into buzz/chirp and sustained/punchy axes."""
    values = np.asarray(vector, dtype=float).ravel()
    slices = _feature_slices(n_mfcc)

    if values.size < slices["duration"].stop:
        return 0.0, 0.0

    if values.size >= slices["axis"].stop:
        axis_values = values[slices["axis"]]
        axis = dict(zip(AXIS_FEATURES, axis_values))
        buzz_vs_chirp = (
            0.34 * axis["pitch_height"]
            + 0.28 * axis["pitch_stability"]
            + 0.24 * axis["tonality"]
            + 0.22 * axis["brightness"]
            + 0.12 * axis["attack"]
            - 0.34 * axis["noisiness"]
            - 0.12 * axis["sustain"]
        )
        sustained_vs_punchy = (
            0.44 * axis["attack"]
            + 0.18 * axis["pitch_height"]
            + 0.12 * axis["brightness"]
            - 0.42 * axis["sustain"]
            - 0.14 * axis["duration"]
        )
        return float(buzz_vs_chirp), float(sustained_vs_punchy)

    def _slice_energy(name: str) -> float:
        group = values[slices[name]]
        return float(np.mean(np.abs(group)))

    melodic_vs_rough = (
        1.15 * _slice_energy("pitch")
        + 0.8 * _slice_energy("pitch_contour")
        - 1.0 * _slice_energy("texture")
        - 0.35 * _slice_energy("envelope")
    )
    simple_vs_complex = (
        1.05 * _slice_energy("mfcc")
        + 0.95 * _slice_energy("texture")
        + 0.7 * _slice_energy("pitch_contour")
        + 0.45 * _slice_energy("envelope")
        + 0.2 * _slice_energy("duration")
    )

    return melodic_vs_rough, simple_vs_complex


def _resample_1d(values: np.ndarray, target_length: int) -> np.ndarray:
    """Resample a 1D array to a fixed length using linear interpolation."""
    values = np.asarray(values, dtype=float).ravel()
    if values.size == 0:
        return np.zeros(target_length, dtype=float)
    if values.size == target_length:
        return values

    source_x = np.linspace(0.0, 1.0, values.size)
    target_x = np.linspace(0.0, 1.0, target_length)
    return np.interp(target_x, source_x, values)


def _shape_autocorr_fingerprint(
    magnitude: np.ndarray,
    frequencies: np.ndarray,
    band_count: int = SHAPE_BANDS,
    time_bins: int = SHAPE_TIME_BINS,
    autocorr_lags: int = SHAPE_AUTOCORR_LAGS,
) -> np.ndarray:
    """
    Build a pitch-tolerant time-shape fingerprint.

    Classic Pokemon cries are often the same noisy gesture with pitch/speed
    offsets. A frequency-band autocorrelation preserves that gesture while
    being less brittle to exact pitch than a raw spectrogram image.
    """
    if magnitude.size == 0:
        return np.zeros(autocorr_lags * time_bins + time_bins, dtype=float)

    max_frequency = max(float(np.max(frequencies)), 1000.0)
    high_frequency = min(9000.0, max_frequency)
    low_frequency = min(90.0, high_frequency * 0.5)
    edges = np.geomspace(low_frequency, high_frequency, band_count + 1)

    band_energy = []
    for low, high in zip(edges[:-1], edges[1:]):
        mask = (frequencies >= low) & (frequencies < high)
        if np.any(mask):
            band_energy.append(np.mean(magnitude[mask], axis=0))
        else:
            band_energy.append(np.zeros(magnitude.shape[1], dtype=float))

    bands = np.log1p(np.asarray(band_energy) * 30.0)
    bands = (bands - np.mean(bands, axis=0, keepdims=True)) / (
        np.std(bands, axis=0, keepdims=True) + 1e-6
    )

    lag_rows = []
    for lag in range(autocorr_lags):
        if lag == 0:
            autocorr = np.mean(bands * bands, axis=0)
        else:
            autocorr = np.mean(bands[:-lag] * bands[lag:], axis=0)
        lag_rows.append(_resample_1d(autocorr, time_bins))

    envelope = np.sqrt(np.mean(magnitude * magnitude, axis=0))
    envelope = np.log1p(_resample_1d(envelope, time_bins) * 30.0)
    envelope = (envelope - np.mean(envelope)) / (np.std(envelope) + 1e-6)

    shape = np.concatenate([np.asarray(lag_rows).ravel(), envelope * 0.5])
    return _center_and_norm(shape)


def _summary_stats(matrix: np.ndarray) -> np.ndarray:
    """
    Summarize a frame-wise feature matrix with robust descriptive statistics.
    """
    if matrix.ndim == 1:
        matrix = matrix[np.newaxis, :]

    q25 = np.percentile(matrix, 25, axis=1)
    q50 = np.percentile(matrix, 50, axis=1)
    q75 = np.percentile(matrix, 75, axis=1)
    return np.concatenate(
        [
            np.mean(matrix, axis=1),
            np.std(matrix, axis=1),
            q25,
            q50,
            q75,
        ]
    )


def extract_audio_features(audio_path: Path, n_mfcc: int = 16) -> Optional[np.ndarray]:
    """
    Extract a perceptual feature vector that gives more weight to timbre,
    spectral texture, and envelope shape than raw duration.

    Feature groups (each L2-normalized independently before concatenation):
      - MFCC + delta stats: broad timbre body and contour
      - Spectral texture stats: contrast / flatness / brightness / noisiness
      - Pitch stats: chroma + tonnetz for tonal center and harmonic color
      - Envelope stats: RMS / onset strength / energy-shape landmarks
      - Duration stats: lightly weighted so clip length does not dominate
    """
    try:
        y, sr = librosa.load(audio_path, sr=22050)
        if len(y) == 0:
            return None

        # Normalize level and pad short cries so spectral features remain stable
        # even when the raw sample is only a few milliseconds long.
        y = librosa.util.normalize(y)
        target_len = max(len(y), 1024)
        y = librosa.util.fix_length(y, size=target_len)

        # Pick the largest power-of-2 FFT window that comfortably fits.
        n_fft = int(2 ** np.floor(np.log2(max(len(y), 256))))
        n_fft = min(n_fft, 2048)
        hop_length = max(1, n_fft // 4)

        mfccs = librosa.feature.mfcc(
            y=y,
            sr=sr,
            n_mfcc=n_mfcc,
            n_fft=n_fft,
            hop_length=hop_length,
        )
        mfcc_delta = librosa.feature.delta(mfccs, mode="nearest")
        mfcc_group = np.concatenate(
            [_summary_stats(mfccs), _summary_stats(mfcc_delta)]
        )

        contrast = librosa.feature.spectral_contrast(
            y=y,
            sr=sr,
            n_fft=n_fft,
            hop_length=hop_length,
        )
        centroid = librosa.feature.spectral_centroid(
            y=y,
            sr=sr,
            n_fft=n_fft,
            hop_length=hop_length,
        )
        bandwidth = librosa.feature.spectral_bandwidth(
            y=y,
            sr=sr,
            n_fft=n_fft,
            hop_length=hop_length,
        )
        rolloff = librosa.feature.spectral_rolloff(
            y=y,
            sr=sr,
            roll_percent=0.9,
            n_fft=n_fft,
            hop_length=hop_length,
        )
        flatness = librosa.feature.spectral_flatness(
            y=y,
            n_fft=n_fft,
            hop_length=hop_length,
        )
        zcr = librosa.feature.zero_crossing_rate(y, hop_length=hop_length)
        power = np.abs(
            librosa.stft(y, n_fft=n_fft, hop_length=hop_length),
        ) ** 2
        magnitude = np.sqrt(power)
        frequencies = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
        power_sum = np.sum(power, axis=0, keepdims=True)
        normalized_power = power / np.maximum(power_sum, 1e-12)
        spectral_entropy = -np.sum(
            normalized_power * np.log2(np.maximum(normalized_power, 1e-12)),
            axis=0,
            keepdims=True,
        ) / np.log2(max(power.shape[0], 2))
        texture_group = np.concatenate(
            [
                _summary_stats(contrast),
                _summary_stats(centroid),
                _summary_stats(bandwidth),
                _summary_stats(rolloff),
                _summary_stats(flatness),
                _summary_stats(zcr),
                _summary_stats(spectral_entropy),
            ]
        )

        harmonic, _ = librosa.effects.hpss(y)
        chroma = librosa.feature.chroma_stft(
            y=harmonic,
            sr=sr,
            n_fft=n_fft,
            hop_length=hop_length,
        )
        tonnetz = librosa.feature.tonnetz(chroma=chroma, sr=sr)
        pitch_group = np.concatenate(
            [_summary_stats(chroma), _summary_stats(tonnetz)]
        )

        try:
            f0 = librosa.yin(
                y,
                fmin=65.40639132514966,
                fmax=2093.004522404789,
                sr=sr,
                frame_length=n_fft,
                hop_length=hop_length,
            )
            finite_f0 = f0[np.isfinite(f0) & (f0 > 0)]
            if finite_f0.size:
                log_f0 = np.log2(finite_f0)
                pitch_contour_group = np.array(
                    [
                        float(finite_f0.size / max(f0.size, 1)),
                        float(np.mean(log_f0)),
                        float(np.std(log_f0)),
                        float(np.percentile(log_f0, 10)),
                        float(np.percentile(log_f0, 50)),
                        float(np.percentile(log_f0, 90)),
                    ],
                    dtype=float,
                )
            else:
                pitch_contour_group = np.zeros(6, dtype=float)
        except Exception:
            pitch_contour_group = np.zeros(6, dtype=float)

        rms = librosa.feature.rms(y=y, frame_length=n_fft, hop_length=hop_length)
        onset_env = librosa.onset.onset_strength(
            y=y,
            sr=sr,
            hop_length=hop_length,
        )
        onset_stats = np.array(
            [
                float(np.mean(onset_env)),
                float(np.std(onset_env)),
                float(np.max(onset_env)) if onset_env.size else 0.0,
            ]
        )

        cumulative_energy = np.cumsum(np.square(y))
        if cumulative_energy.size == 0 or cumulative_energy[-1] <= 1e-10:
            energy_shape = np.array([0.0, 0.0, 0.0], dtype=float)
        else:
            cumulative_energy = cumulative_energy / cumulative_energy[-1]
            energy_shape = np.array(
                [
                    float(np.searchsorted(cumulative_energy, 0.2) / len(cumulative_energy)),
                    float(np.searchsorted(cumulative_energy, 0.5) / len(cumulative_energy)),
                    float(np.searchsorted(cumulative_energy, 0.85) / len(cumulative_energy)),
                ],
                dtype=float,
            )

        envelope_group = np.concatenate(
            [
                _summary_stats(rms),
                onset_stats,
                energy_shape,
            ]
        )

        duration = len(y) / sr
        duration_group = np.array(
            [
                float(np.log1p(duration)),
                float(duration),
            ],
            dtype=float,
        )

        finite_f0_ratio = float(pitch_contour_group[0])
        pitch_height = float(pitch_contour_group[4]) if finite_f0_ratio > 0 else 0.0
        pitch_variation = float(pitch_contour_group[2]) if finite_f0_ratio > 0 else 2.0
        pitch_stability = finite_f0_ratio / (1.0 + pitch_variation)
        tonality = finite_f0_ratio + pitch_stability
        noisiness = (
            float(np.mean(flatness)) * 1.25
            + float(np.mean(spectral_entropy)) * 0.9
            + float(np.mean(zcr)) * 0.55
        )
        brightness_score = float(np.log1p(np.mean(centroid)))
        attack_score = float(np.max(onset_env)) if onset_env.size else 0.0
        sustain_score = float(max(energy_shape[2] - energy_shape[0], 0.0))
        modulation_score = (
            float(np.std(mfcc_delta))
            + float(np.std(centroid) / max(float(np.mean(centroid)), 1e-6))
            + float(np.std(onset_env))
        )
        sparkle_score = float(np.mean(contrast[-2:])) if contrast.shape[0] >= 2 else 0.0
        axis_group = np.array(
            [
                pitch_height,
                pitch_stability,
                tonality,
                noisiness,
                brightness_score,
                attack_score,
                sustain_score,
                modulation_score,
                sparkle_score,
                float(np.log1p(duration)),
            ],
            dtype=float,
        )

        shape_group = _shape_autocorr_fingerprint(magnitude, frequencies)

        return np.concatenate([
            _center_and_norm(mfcc_group) * 1.25,
            _center_and_norm(texture_group) * 2.05,
            _center_and_norm(pitch_group) * 0.9,
            _center_and_norm(pitch_contour_group) * 0.75,
            _center_and_norm(envelope_group) * 1.15,
            _center_and_norm(duration_group) * 0.12,
            axis_group,
            shape_group * 2.35,
        ])

    except Exception as e:
        print(f"Error extracting features from {audio_path}: {e}")
        return None


# ── Legacy helpers kept for reference ────────────────────────────────────────

def load_and_preprocess_audio(audio_path: Path, sr: int = 22050,
                               n_mfcc: int = 13) -> Optional[np.ndarray]:
    try:
        y, _ = librosa.load(audio_path, sr=sr)
        return librosa.feature.mfcc(y=y, sr=sr, n_mfcc=n_mfcc) if len(y) else None
    except Exception as e:
        print(f"Error processing audio file {audio_path}: {e}")
        return None


def extract_mfcc_vector(audio_path: Path, n_mfcc: int = 13) -> Optional[np.ndarray]:
    mfccs = load_and_preprocess_audio(audio_path, n_mfcc=n_mfcc)
    if mfccs is None:
        return None
    return np.concatenate([np.mean(mfccs, axis=1), np.std(mfccs, axis=1)])


def get_audio_duration(audio_path: Path) -> Optional[float]:
    """
    Get the duration of an audio file in seconds.

    Args:
        audio_path: Path to the audio file

    Returns:
        Duration in seconds or None if loading failed
    """
    try:
        y, sr = librosa.load(audio_path, sr=None)
        duration = librosa.get_duration(y=y, sr=sr)
        return duration
    except Exception as e:
        print(f"Error getting duration for {audio_path}: {e}")
        return None
