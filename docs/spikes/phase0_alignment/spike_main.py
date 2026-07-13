from __future__ import annotations

import argparse
import json
import re
import resource
import time

import numpy as np
import onnxruntime as ort
import soundfile as sf
from scipy.signal import resample_poly
from scipy.special import log_softmax


VOCAB = {
    "<blank>": 0, "<pad>": 1, "</s>": 2, "<unk>": 3,
    "a": 4, "i": 5, "e": 6, "n": 7, "o": 8, "u": 9, "t": 10,
    "s": 11, "r": 12, "m": 13, "k": 14, "l": 15, "d": 16,
    "g": 17, "h": 18, "y": 19, "b": 20, "p": 21, "w": 22,
    "c": 23, "v": 24, "j": 25, "z": 26, "f": 27, "'": 28,
    "q": 29, "x": 30, "<star>": 31,
}


def load_audio(path: str) -> np.ndarray:
    wav, sr = sf.read(path, dtype="float32", always_2d=False)
    if wav.ndim > 1:
        wav = wav.mean(axis=1)
    if sr != 16000:
        wav = resample_poly(wav, 16000, sr).astype(np.float32)
    mean = float(wav.mean())
    std = float(wav.std())
    return ((wav - mean) / np.sqrt(std * std + 1e-7)).astype(np.float32)


def tokenize(text: str):
    words = re.findall(r"[a-z']+", text.lower())
    ids = [VOCAB["<star>"]]
    ranges = []
    for word in words:
        start = len(ids)
        ids.extend(VOCAB.get(char, VOCAB["<unk>"]) for char in word)
        ranges.append((word, start, len(ids) - 1))
    ids.append(VOCAB["<star>"])
    return words, np.asarray(ids, dtype=np.int64), ranges


def forced_align(log_probs: np.ndarray, targets: np.ndarray, blank: int = 0):
    # Viterbi over the standard CTC blank-interleaved state graph.
    t_count = log_probs.shape[0]
    states = np.empty(2 * len(targets) + 1, dtype=np.int64)
    states[0::2] = blank
    states[1::2] = targets
    neg = -np.inf
    scores = np.full((t_count, len(states)), neg, dtype=np.float32)
    back = np.zeros((t_count, len(states)), dtype=np.int8)
    scores[0, 0] = log_probs[0, blank]
    scores[0, 1] = log_probs[0, targets[0]]
    for t in range(1, t_count):
        for s, label in enumerate(states):
            candidates = [(scores[t - 1, s], 0)]
            if s:
                candidates.append((scores[t - 1, s - 1], 1))
            if s > 1 and label != blank and label != states[s - 2]:
                candidates.append((scores[t - 1, s - 2], 2))
            previous, step = max(candidates, key=lambda item: item[0])
            scores[t, s] = previous + log_probs[t, label]
            back[t, s] = step
    state = len(states) - 1 if scores[-1, -1] >= scores[-1, -2] else len(states) - 2
    state_path = np.empty(t_count, dtype=np.int64)
    for t in range(t_count - 1, -1, -1):
        state_path[t] = state
        if t:
            state -= int(back[t, state])
    labels = states[state_path]
    frame_scores = log_probs[np.arange(t_count), labels]
    return state_path, frame_scores


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("model")
    parser.add_argument("audio")
    parser.add_argument("transcript")
    args = parser.parse_args()
    before_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    started = time.perf_counter()
    session = ort.InferenceSession(args.model, providers=["CPUExecutionProvider"])
    loaded = time.perf_counter()
    wav = load_audio(args.audio)
    logits = session.run(["logits"], {"input_values": wav[None, :]})[0][0]
    inferred = time.perf_counter()
    emissions = log_softmax(logits.astype(np.float32), axis=-1)
    # Upstream ctc-forced-aligner defines <star> as an added zero-log-score class.
    emissions = np.concatenate(
        [emissions, np.zeros((emissions.shape[0], 1), dtype=np.float32)], axis=1
    )
    words, targets, ranges = tokenize(args.transcript)
    state_path, frame_scores = forced_align(emissions, targets)
    stride_seconds = len(wav) / 16000.0 / emissions.shape[0]
    boundaries = []
    for word, first_target, last_target in ranges:
        target_states = np.arange(first_target * 2 + 1, last_target * 2 + 2, 2)
        frames = np.flatnonzero(np.isin(state_path, target_states))
        if not len(frames):
            continue
        mean_log_score = float(frame_scores[frames].mean())
        boundaries.append({
            "text": word,
            "start": round(float(frames[0] * stride_seconds), 3),
            "end": round(float((frames[-1] + 1) * stride_seconds), 3),
            "mean_log_score": round(mean_log_score, 4),
            "geometric_mean_probability": round(float(np.exp(mean_log_score)), 4),
        })
    after_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    print(json.dumps({
        "providers": session.get_providers(),
        "audio_seconds": round(len(wav) / 16000.0, 3),
        "frames": int(emissions.shape[0]),
        "stride_ms": round(stride_seconds * 1000, 3),
        "session_load_seconds": round(loaded - started, 3),
        "inference_seconds": round(inferred - loaded, 3),
        "total_seconds": round(time.perf_counter() - started, 3),
        "max_rss_before_kib": before_rss,
        "max_rss_after_kib": after_rss,
        "boundaries": boundaries,
    }, indent=2))


if __name__ == "__main__":
    main()
