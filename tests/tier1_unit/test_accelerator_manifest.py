"""Test persona_forge.accelerator_manifest: the Phase 4 native accelerator pin manifest."""

from __future__ import annotations

from persona_forge.accelerator_manifest import (
    ACCELERATOR_PINS,
    pin_for_family,
    select_cuda_pin,
)


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

class TestSelectCudaPin:
    """D23 rule: CC >= (7,5) AND driver CUDA major >= 13 -> cuda13; else cuda12."""

    def test_rtx_5090_blackwell_selects_cuda13(self):
        pin = select_cuda_pin(compute_capability=(12, 0), driver_cuda_major=13)
        assert pin.extra == "cuda13"
        assert pin.index_url == "https://download.pytorch.org/whl/cu130"

    def test_ampere_cuda13_driver_selects_cuda13(self):
        pin = select_cuda_pin(compute_capability=(8, 6), driver_cuda_major=13)
        assert pin.extra == "cuda13"

    def test_turing_cuda13_driver_selects_cuda13(self):
        pin = select_cuda_pin(compute_capability=(7, 5), driver_cuda_major=13)
        assert pin.extra == "cuda13"

    def test_pascal_cuda13_driver_selects_cuda12(self):
        # GTX 1080: CC 6.1 < (7,5) -> cuda12 even with CUDA 13 driver.
        pin = select_cuda_pin(compute_capability=(6, 1), driver_cuda_major=13)
        assert pin.extra == "cuda12"

    def test_blackwell_cuda12_driver_selects_cuda12(self):
        # RTX 5090 but driver only supports CUDA 12.6.
        pin = select_cuda_pin(compute_capability=(12, 0), driver_cuda_major=12)
        assert pin.extra == "cuda12"

    def test_unknown_capability_selects_cuda12(self):
        pin = select_cuda_pin(compute_capability=None, driver_cuda_major=13)
        assert pin.extra == "cuda12"

    def test_unknown_cuda_major_selects_cuda12(self):
        pin = select_cuda_pin(compute_capability=(12, 0), driver_cuda_major=None)
        assert pin.extra == "cuda12"

    def test_both_unknown_selects_cuda12(self):
        pin = select_cuda_pin(compute_capability=None, driver_cuda_major=None)
        assert pin.extra == "cuda12"


class TestPinForFamilyCudaSelection:
    """pin_for_family('cuda') delegates to select_cuda_pin."""

    def test_cuda_with_blackwell_selects_cuda13(self):
        pin = pin_for_family("cuda", compute_capability=(12, 0), driver_cuda_major=13)
        assert pin is not None
        assert pin.extra == "cuda13"

    def test_cuda_without_info_selects_cuda12(self):
        pin = pin_for_family("cuda")
        assert pin is not None
        assert pin.extra == "cuda12"

    def test_cuda_with_old_gpu_selects_cuda12(self):
        pin = pin_for_family("cuda", compute_capability=(6, 1), driver_cuda_major=13)
        assert pin is not None
        assert pin.extra == "cuda12"
