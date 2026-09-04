"""Test persona_forge.frontend: override/package/checkout/API-only resolution order (Phase 3)."""

from __future__ import annotations

from pathlib import Path

from persona_forge import frontend


def _touch_index(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "index.html").write_text("<html></html>")


class TestResolveFrontendDir:
    def test_override_wins_even_if_it_does_not_exist(self, tmp_path):
        override = tmp_path / "does-not-exist"
        package_static = tmp_path / "pkg-static"
        _touch_index(package_static)
        result = frontend.resolve_frontend_dir(
            {"FRONTEND_DIST_DIR": str(override)},
            package_static_dir=package_static,
            checkout_dist_dir=tmp_path / "checkout",
        )
        assert result == override

    def test_checkout_wins_over_package_local_staging_assets(self, tmp_path):
        package_static = tmp_path / "pkg-static"
        checkout = tmp_path / "checkout"
        _touch_index(package_static)
        _touch_index(checkout)
        result = frontend.resolve_frontend_dir(
            {}, package_static_dir=package_static, checkout_dist_dir=checkout
        )
        assert result == checkout

    def test_falls_back_to_checkout_when_package_local_absent(self, tmp_path):
        package_static = tmp_path / "pkg-static"  # never created
        checkout = tmp_path / "checkout"
        _touch_index(checkout)
        result = frontend.resolve_frontend_dir(
            {}, package_static_dir=package_static, checkout_dist_dir=checkout
        )
        assert result == checkout

    def test_falls_back_to_checkout_when_package_local_has_no_index_html(self, tmp_path):
        package_static = tmp_path / "pkg-static"
        package_static.mkdir()  # exists but incomplete/stale — no index.html
        checkout = tmp_path / "checkout"
        _touch_index(checkout)
        result = frontend.resolve_frontend_dir(
            {}, package_static_dir=package_static, checkout_dist_dir=checkout
        )
        assert result == checkout

    def test_api_only_when_neither_present(self, tmp_path):
        package_static = tmp_path / "pkg-static"
        checkout = tmp_path / "checkout"
        result = frontend.resolve_frontend_dir(
            {}, package_static_dir=package_static, checkout_dist_dir=checkout
        )
        assert result == checkout
        assert not result.is_dir()


class TestFrontendEnabled:
    def test_defaults_enabled(self):
        assert frontend.frontend_enabled({}) is True

    def test_explicit_zero_disables(self):
        assert frontend.frontend_enabled({"FRONTEND_ENABLED": "0"}) is False

    def test_explicit_false_disables(self):
        assert frontend.frontend_enabled({"FRONTEND_ENABLED": "false"}) is False
