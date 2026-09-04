"""Test persona_forge.accelerator_manifest: the Phase 4 native accelerator pin manifest."""

from __future__ import annotations

from persona_forge.accelerator_manifest import ACCELERATOR_PINS, pin_for_family


class TestAcceleratorPins:
    def test_every_pin_maps_to_a_valid_gpu_family(self):
        # cpu is deliberately absent — it has no dedicated wheel index/pin.
        assert {pin.gpu_family for pin in ACCELERATOR_PINS.values()} <= {"cuda", "rocm", "intel-xpu"}

    def test_extra_key_matches_pin_extra_field(self):
        for extra, pin in ACCELERATOR_PINS.items():
            assert pin.extra == extra

    def test_rocm_is_linux_only(self):
        assert ACCELERATOR_PINS["rocm"].platforms == ("linux",)

    def test_no_pin_targets_darwin(self):
        # No accelerator wheel family (cuda/rocm/xpu) publishes a macOS build — mps is out of
        # scope for this manifest (native macOS install uses the base torch pin, unaccelerated
        # by this manifest).
        for pin in ACCELERATOR_PINS.values():
            assert "darwin" not in pin.platforms

    def test_cuda12_and_cuda13_share_the_cuda_family(self):
        assert ACCELERATOR_PINS["cuda12"].gpu_family == "cuda"
        assert ACCELERATOR_PINS["cuda13"].gpu_family == "cuda"


class TestPinForFamily:
    def test_cuda_family_resolves_to_a_cuda_pin(self):
        pin = pin_for_family("cuda")
        assert pin is not None
        assert pin.gpu_family == "cuda"

    def test_rocm_family_resolves(self):
        pin = pin_for_family("rocm")
        assert pin is not None
        assert pin.gpu_family == "rocm"

    def test_intel_xpu_family_resolves(self):
        pin = pin_for_family("intel-xpu")
        assert pin is not None
        assert pin.gpu_family == "intel-xpu"

    def test_cpu_family_has_no_pin(self):
        assert pin_for_family("cpu") is None

    def test_unknown_family_has_no_pin(self):
        assert pin_for_family("bogus") is None
