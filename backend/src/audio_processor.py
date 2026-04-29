"""
Audio processing utilities for extracting perceptual features from Pokemon cries.
"""

import numpy as np
import librosa
from pathlib import Path
from typing import Optional


# Informational only - no longer encoded in filenames.
# Increment when the feature layout changes; use `manage.py build --force`
# (which clears the vectors directory) to pick up the new format.
FEATURE_VERSION = 6


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
    return slices


def project_melodic_complexity_axes(
    vector: np.ndarray, n_mfcc: int = 16
) -> tuple[float, float]:
    """Project a feature vector into melodic/rough and simple/complex axes."""
    values = np.asarray(vector, dtype=float).ravel()
    slices = _feature_slices(n_mfcc)

    if values.size < slices["duration"].stop:
        return 0.0, 0.0

    def _slice_norm(name: str) -> float:
        return float(np.linalg.norm(values[slices[name]]))

    melodic_vs_rough = (
        1.15 * _slice_norm("pitch")
        + 0.8 * _slice_norm("pitch_contour")
        - 1.0 * _slice_norm("texture")
        - 0.35 * _slice_norm("envelope")
    )
    simple_vs_complex = (
        1.05 * _slice_norm("mfcc")
        + 0.95 * _slice_norm("texture")
        + 0.7 * _slice_norm("pitch_contour")
        + 0.45 * _slice_norm("envelope")
        + 0.2 * _slice_norm("duration")
    )

    return melodic_vs_rough, simple_vs_complex


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
                fmin=librosa.note_to_hz("C2"),
                fmax=librosa.note_to_hz("C7"),
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

        return np.concatenate([
            _center_and_norm(mfcc_group) * 1.25,
            _center_and_norm(texture_group) * 2.05,
            _center_and_norm(pitch_group) * 0.9,
            _center_and_norm(pitch_contour_group) * 0.75,
            _center_and_norm(envelope_group) * 1.15,
            _center_and_norm(duration_group) * 0.12,
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
