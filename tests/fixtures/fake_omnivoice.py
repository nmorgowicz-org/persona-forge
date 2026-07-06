from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

import numpy as np


class FakeOmniVoiceModel:
    """Stands in for omnivoice.OmniVoice.

    Two modes (both are valid and supported):

    1) Script mode (plan §7.4 canonical):
       - script: list[dict] with items {audio, drone, fail, text}
       - generate(segment, instruct, ...) -> Dict["audio", "is_drone", "text"]

    2) Draws mode (legacy from tests/test_omnivoice_engine.py pattern):
       - draws: list[np.ndarray]
       - generate(**kwargs) -> [np.ndarray]
       - tracks calls as list[dict[kwargs]]
    """

    def __init__(
        self,
        script: Optional[List[Dict[str, Any]]] = None,
        always_drone: bool = False,
        fail_on: Optional[int] = None,
        sr: int = 24000,
        default_dur: float = 1.0,
        draws: Optional[List[np.ndarray]] = None,
    ) -> None:
        # Canonical fields (§7.4)
        self.script: List[Dict[str, Any]] = list(script or [])
        self.always_drone: bool = always_drone
        self.fail_on: Optional[int] = fail_on
        self.sr: int = sr
        self.default_dur: float = default_dur

        # Legacy "draws" mode (used by existing tests).
        self.draws: List[np.ndarray] = list(draws or [])
        self.calls: List[Dict[str, Any]] = []

    def generate(
        self,
        segment: str = "",
        instruct: str = "",
        **kwargs: Any,
    ) -> Union[Dict[str, Any], List[np.ndarray]]:
        call_index = len(self.calls)
        self.calls.append({
            "segment": segment,
            "instruct": instruct,
            **{k: v for k, v in kwargs.items()},
        })

        # Legacy "draws" mode: match test_omnivoice_engine.py interface.
        if self.draws:
            if self.fail_on is not None and (call_index + 1) == self.fail_on:
                raise RuntimeError(
                    f"FakeOmniVoiceModel: fail_on={self.fail_on}"
                )
            audio = self.draws.pop(0)
            return [audio]

        # Fail_on check for script mode.
        if self.fail_on is not None and (call_index + 1) == self.fail_on:
            raise RuntimeError(
                f"FakeOmniVoiceModel: fail_on={self.fail_on}"
            )

        # Script mode: pop from queue or default.
        if self.script:
            draw = self.script.pop(0)
        else:
            draw = {}

        is_drone: bool = draw.get("drone", self.always_drone)
        text: str = draw.get("text", "Fake OmniVoice output.")

        if "audio" in draw:
            audio = np.asarray(draw["audio"], dtype=np.float32)
        else:
            frames = int(self.sr * self.default_dur)
            audio = np.zeros(frames, dtype=np.float32)

        return {
            "audio": audio,
            "is_drone": is_drone,
            "text": text,
        }


def create_fake_omnivoice(
    script: Optional[List[Dict[str, Any]]] = None,
    **kwargs: Any,
) -> FakeOmniVoiceModel:
    return FakeOmniVoiceModel(script=script, **kwargs)
