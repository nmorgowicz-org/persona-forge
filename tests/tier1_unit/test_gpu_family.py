"""Test persona_forge.gpu_family: family resolution + presence/capability split (Phase A6c)."""

from __future__ import annotations

from persona_forge.gpu_family import Probes, describe_accelerator, resolve_gpu_family


def _probes(
    cuda_node=False,
    nvidia_pci=False,
    rocm_node=False,
    amd_pci=False,
    intel_node=False,
    intel_pci=False,
) -> Probes:
    return Probes(
        cuda_device_node=lambda: cuda_node,
        nvidia_pci=lambda: nvidia_pci,
        rocm_device_node=lambda: rocm_node,
        amd_pci=lambda: amd_pci,
        intel_device_node=lambda: intel_node,
        intel_pci=lambda: intel_pci,
    )


class TestResolveGpuFamily:
    def test_no_hardware_is_cpu(self):
        assert resolve_gpu_family({}, _probes()) == "cpu"

    def test_nvidia_present_and_capable_is_cuda(self):
        probes = _probes(cuda_node=True, nvidia_pci=True)
        assert resolve_gpu_family({}, probes) == "cuda"

    def test_amd_present_and_capable_is_rocm(self):
        probes = _probes(rocm_node=True, amd_pci=True)
        assert resolve_gpu_family({}, probes) == "rocm"

    def test_intel_present_and_capable_is_intel_xpu(self):
        probes = _probes(intel_node=True, intel_pci=True)
        assert resolve_gpu_family({}, probes) == "intel-xpu"

    def test_pci_present_but_no_device_node_stays_cpu(self):
        # Presence without capability (no passthrough yet) must never select the family.
        probes = _probes(nvidia_pci=True)
        assert resolve_gpu_family({}, probes) == "cpu"

    def test_priority_cuda_over_rocm_over_intel(self):
        probes = _probes(
            cuda_node=True, nvidia_pci=True,
            rocm_node=True, amd_pci=True,
            intel_node=True, intel_pci=True,
        )
        assert resolve_gpu_family({}, probes) == "cuda"

    def test_explicit_gpu_family_cpu_wins_regardless_of_probes(self):
        probes = _probes(cuda_node=True, nvidia_pci=True)
        assert resolve_gpu_family({"GPU_FAMILY": "cpu"}, probes) == "cpu"

    def test_explicit_gpu_family_forces_family_even_without_hardware(self):
        assert resolve_gpu_family({"GPU_FAMILY": "intel-xpu"}, _probes()) == "intel-xpu"

    def test_unrecognized_gpu_family_falls_back_to_auto(self):
        probes = _probes(intel_node=True, intel_pci=True)
        assert resolve_gpu_family({"GPU_FAMILY": "bogus"}, probes) == "intel-xpu"


class TestDescribeAccelerator:
    def test_present_true_capable_false_is_the_coach_trigger(self):
        # PCI-present + device-node-absent: this is exactly what should nudge the A7c coach.
        probes = _probes(intel_pci=True)
        info = describe_accelerator({}, probes)
        assert info["present"] is True
        assert info["capable"] is False
        assert info["family"] == "cpu"
        # detected_family names the actual vendor even though auto-resolution fell back to cpu —
        # the coach needs this to pick the right family-specific snippet.
        assert info["detected_family"] == "intel-xpu"

    def test_detected_family_differs_from_family_under_forced_override(self):
        # Forcing GPU_FAMILY away from the detected vendor: family follows the override,
        # detected_family still reports what's physically present.
        probes = _probes(intel_node=True, intel_pci=True)
        info = describe_accelerator({"GPU_FAMILY": "cpu"}, probes)
        assert info["family"] == "cpu"
        assert info["detected_family"] == "intel-xpu"

    def test_present_and_capable_when_fully_mapped(self):
        probes = _probes(intel_node=True, intel_pci=True)
        info = describe_accelerator({}, probes)
        assert info["present"] is True
        assert info["capable"] is True
        assert info["family"] == "intel-xpu"

    def test_no_hardware_present_false_capable_false(self):
        info = describe_accelerator({}, _probes())
        assert info["present"] is False
        assert info["capable"] is False

    def test_present_capable_reflects_real_detection_even_with_explicit_override(self):
        # GPU_FAMILY=cpu forces family='cpu', but present/capable still reflect actual hardware.
        probes = _probes(intel_node=True, intel_pci=True)
        info = describe_accelerator({"GPU_FAMILY": "cpu"}, probes)
        assert info["family"] == "cpu"
        assert info["present"] is True
        assert info["capable"] is True
