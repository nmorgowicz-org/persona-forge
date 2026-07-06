from __future__ import annotations

from typing import Any, List, Optional

import numpy as np


class FakeInput:
    """Matches OpenVINO input descriptor used by export/runtime code."""

    def __init__(
        self,
        name: str = "input",
        shape: tuple[int, ...] = (1, 1, 768),
        precision: str = "FP32",
    ) -> None:
        self.name = name
        self.shape = shape
        self.precision = precision


class FakeOutput:
    """Matches OpenVINO output descriptor used by export/runtime code."""

    def __init__(
        self,
        name: str = "output",
        shape: tuple[int, ...] = (1, 1, 768),
        precision: str = "FP32",
    ) -> None:
        self.name = name
        self.shape = shape
        self.precision = precision


class FakeOVModel:
    """Fake OpenVINO model with inputs/outputs used by export and runtime tests."""

    def __init__(
        self,
        inputs: Optional[List[FakeInput]] = None,
        outputs: Optional[List[FakeOutput]] = None,
    ) -> None:
        self.inputs = inputs or [FakeInput()]
        self.outputs = outputs or [FakeOutput()]


class FakeCompiledModel:
    """Fake compiled model exposing create_infer_request()."""

    def __init__(
        self,
        model: Optional[FakeOVModel] = None,
    ) -> None:
        self._model = model or FakeOVModel()
        self.inputs = self._model.inputs
        self.outputs = self._model.outputs

    def create_infer_request(self) -> "FakeInferRequest":
        return FakeInferRequest(self.outputs)


class FakeInferRequest:
    """Fake infer request: no-op infer() returning plausible outputs."""

    def __init__(
        self,
        outputs: Optional[List[FakeOutput]] = None,
    ) -> None:
        self._outputs = outputs or [FakeOutput()]
        self._tensors: dict[str, np.ndarray] = {}

    def set_input(self, tensor: np.ndarray, port_id: Optional[int] = None) -> None:
        key = f"input_{port_id}" if port_id is not None else "input_0"
        self._tensors[key] = np.asarray(tensor)

    def infer(self) -> None:
        for o in self._outputs:
            key = f"output_{o.name}"
            if key not in self._tensors:
                self._tensors[key] = np.zeros(o.shape, dtype=np.float32)

    def get_tensor(self, port_id: int) -> np.ndarray:
        for key, arr in self._tensors.items():
            if "output_" in key:
                return arr
        return np.zeros((1, 1, 768), dtype=np.float32)


class FakeCore:
    """Fake openvino.Core for read_model / compile_model without the runtime."""

    def read_model(self, model_path: str | None = None) -> FakeOVModel:
        return FakeOVModel()

    def compile_model(
        self,
        model: FakeOVModel | str | None = None,
        device: str | None = None,
        config: Optional[dict[str, Any]] = None,
    ) -> FakeCompiledModel:
        if isinstance(model, FakeOVModel):
            return FakeCompiledModel(model)
        return FakeCompiledModel()
