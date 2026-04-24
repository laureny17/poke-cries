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
FEATURE_VERSION = 4


def _l2_norm(v: np.ndarray) -> np.ndarray:
    """Return v scaled to unit length, or v unchanged if it is essentially zero."""
    norm = np.linalg.norm(v)
    return v / norm if norm > 1e-8 else v


def _center_and_norm(v: np.ndarray) -> np.ndarray:
    """Mean-center a feature group before L2 normalization."""
    centered = v - np.mean(v)
    return _l2_norm(centered)


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
        texture_group = np.concatenate(
            [
                _summary_stats(contrast),
                _summary_stats(centroid),
                _summary_stats(bandwidth),
                _summary_stats(rolloff),
                _summary_stats(flatness),
                _summary_stats(zcr),
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
            _center_and_norm(texture_group) * 1.85,
            _center_and_norm(pitch_group) * 0.9,
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
