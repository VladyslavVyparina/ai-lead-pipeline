from PIL import Image

from app.services.brand_image_assets import crop_image_asset, dominant_colors
from app.services.rendered_qa import _identity_matches


def test_crop_image_asset_preserves_crop_and_extracts_colour(tmp_path):
    source = tmp_path / "source.png"
    Image.new("RGB", (100, 80), "#5a3018").save(source)
    output = tmp_path / "asset.png"

    asset = crop_image_asset(source, output, box=(10, 10, 90, 70), max_size=(40, 40))

    assert asset.path == output.resolve()
    assert asset.width == 40
    assert asset.height == 30
    assert dominant_colors(output)[0] == "#5a3018"


def test_identity_check_accepts_accessible_logo_label():
    assert _identity_matches(
        "Damrak Thai Yoga Massage",
        ["Preview headline", "Damrak Thai Yoga Massage"],
    )
    assert not _identity_matches("Damrak Thai Yoga Massage", ["Another wellness studio"])
