"""
Audio processing utilities for extracting perceptual features from Pokémon cries.
"""

import numpy as np
import librosa
from pathlib import Path
from typing import Optional


# Informational only — no longer encoded in filenames.
# Increment when the feature layout changes; use `manage.py build --force`
# (which clears the vectors directory) to pick up the new format.
FEATURE_VERSION = 3


def _l2_norm(v: np.ndarray) -> np.ndarray:
    """Return v scaled to unit length, or v unchanged if it is essentially zero."""
    norm = np.linalg.norm(v)
    return v / norm if norm > 1e-8 else v


def extract_audio_features(audio_path: Path, n_mfcc: int = 13) -> Optional[np.ndarray]:
    """
    Extract a combined perceptual feature vector that captures both timbre and pitch.

    Feature groups (each L2-normalised independently before concatenation):
      - MFCCs mean + std  (26 values)  — timbre / spectral texture,  weight 1.0
      - Chroma mean + std (24 values)  — pitch-class content,         weight 1.5
      - Spectral centroid + rolloff
        mean + std         (4 values)  — brightness / pitch height,   weight 1.5

    Weighting explanation
    ─────────────────────
    Standard MFCCs are *deliberately* pitch-invariant (great for speech
    recognition, bad for perceptual cry similarity). By down-weighting the
    MFCC group and up-weighting the pitch-sensitive groups, the cosine
    similarity score will better match what you hear:

        cos(A,B) ≈ 0.24 · timbre_sim + 0.38 · pitch_class_sim + 0.38 · brightness_sim
    """
    try:
        y, sr = librosa.load(audio_path, sr=22050)
        if len(y) == 0:
            return None

        # Pick the largest power-of-2 FFT window that actually fits in the signal.
        # This avoids "n_fft too large" warnings for very short cries (~6–40 ms).
        # Floor at 32 so we always have something to work with.
        n_fft = int(2 ** np.floor(np.log2(max(len(y), 32))))
        n_fft = min(n_fft, 2048)          # cap at 2048 for normal-length cries
        hop_length = max(1, n_fft // 4)

        # --- Timbre: MFCCs (pitch-invariant spectral envelope) ---
        mfccs = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=n_mfcc,
                                     n_fft=n_fft, hop_length=hop_length)
        mfcc_stats = np.concatenate([np.mean(mfccs, axis=1), np.std(mfccs, axis=1)])

        # --- Pitch class: chroma STFT (more robust than CQT for short signals) ---
        chroma = librosa.feature.chroma_stft(y=y, sr=sr,
                                             n_fft=n_fft, hop_length=hop_length)
        chroma_stats = np.concatenate([np.mean(chroma, axis=1), np.std(chroma, axis=1)])

        # --- Pitch height / brightness: spectral centroid + rolloff ---
        centroid = librosa.feature.spectral_centroid(y=y, sr=sr,
                                                     n_fft=n_fft, hop_length=hop_length)
        rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr, roll_percent=0.85,
                                                   n_fft=n_fft, hop_length=hop_length)
        spectral_stats = np.array([
            float(np.mean(centroid)), float(np.std(centroid)),
            float(np.mean(rolloff)),  float(np.std(rolloff)),
        ])

        # Normalise each group so scale differences don't drown anything out,
        # then apply weights so pitch features matter more than timbre.
        return np.concatenate([
            _l2_norm(mfcc_stats)     * 1.0,
            _l2_norm(chroma_stats)   * 1.5,
            _l2_norm(spectral_stats) * 1.5,
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
