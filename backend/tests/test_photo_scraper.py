from pathlib import Path

from app.services.photo_scraper import _is_property_photo, _normalize_url, extract_photos_from_html

SAMPLE_EMAILS_DIR = Path("/Users/thomas.rosenblatt/Perso/rosen_immo/tests/sample_emails")


# ---------------------------------------------------------------------------
# _is_property_photo
# ---------------------------------------------------------------------------


class TestIsPropertyPhoto:
    def test_seloger_cdn_jpg_is_accepted(self):
        url = "https://mms.seloger.com/photo/abc123.jpg"

        assert _is_property_photo(url) is True

    def test_pap_cdn_jpg_is_accepted(self):
        url = "https://cdn.pap.fr/photos/listings/12345.jpeg"

        assert _is_property_photo(url) is True

    def test_apimo_cdn_webp_is_accepted(self):
        url = "https://media.apimo.pro/cache/images/property-original.webp"

        assert _is_property_photo(url) is True

    def test_non_cdn_url_rejected(self):
        url = "https://example.com/photo.jpg"

        assert _is_property_photo(url) is False

    def test_non_image_extension_rejected(self):
        url = "https://mms.seloger.com/document/file.pdf"

        assert _is_property_photo(url) is False

    def test_logo_on_cdn_rejected(self):
        url = "https://mms.seloger.com/assets/logo.jpg"

        assert _is_property_photo(url) is False

    def test_icon_on_cdn_rejected(self):
        url = "https://mms.seloger.com/ui/icon-home.png"

        assert _is_property_photo(url) is False

    def test_tracking_pixel_on_cdn_rejected(self):
        url = "https://mms.seloger.com/tracking/pixel.png"

        assert _is_property_photo(url) is False

    def test_favicon_on_cdn_rejected(self):
        url = "https://mms.seloger.com/favicon.png"

        assert _is_property_photo(url) is False

    def test_emails_images_path_rejected(self):
        url = "https://mms.seloger.com/emails/images/header.jpg"

        assert _is_property_photo(url) is False


# ---------------------------------------------------------------------------
# _normalize_url
# ---------------------------------------------------------------------------


class TestNormalizeUrl:
    def test_strips_height_param(self):
        url = "https://mms.seloger.com/photo.jpg?h=200&quality=80"
        result = _normalize_url(url)

        assert "h=200" not in result
        assert "quality=80" in result

    def test_strips_width_param(self):
        url = "https://mms.seloger.com/photo.jpg?w=300&quality=80"
        result = _normalize_url(url)

        assert "w=300" not in result
        assert "quality=80" in result

    def test_strips_both_h_and_w(self):
        url = "https://mms.seloger.com/photo.jpg?h=200&w=300"
        result = _normalize_url(url)

        assert "h=200" not in result
        assert "w=300" not in result

    def test_preserves_url_without_size_params(self):
        url = "https://mms.seloger.com/photo.jpg?quality=80"
        result = _normalize_url(url)

        assert result == url

    def test_cleans_trailing_ampersand(self):
        url = "https://mms.seloger.com/photo.jpg?h=200"
        result = _normalize_url(url)

        assert not result.endswith("&")
        assert not result.endswith("?")


# ---------------------------------------------------------------------------
# extract_photos_from_html
# ---------------------------------------------------------------------------


class TestExtractPhotosFromHtml:
    def test_seloger_sample_email_extracts_photos(self):
        html = SAMPLE_EMAILS_DIR.joinpath("seloger.html").read_text()

        photos = extract_photos_from_html(html, source="seloger")

        assert len(photos) > 0
        for url in photos:
            assert "mms.seloger.com" in url

    def test_empty_html_returns_empty_list(self):
        photos = extract_photos_from_html("", source="seloger")

        assert photos == []

    def test_html_without_images_returns_empty_list(self):
        html = "<html><body><p>No images here</p></body></html>"

        photos = extract_photos_from_html(html, source="seloger")

        assert photos == []

    def test_html_with_non_cdn_images_returns_empty_list(self):
        html = '<html><body><img src="https://example.com/photo.jpg"></body></html>'

        photos = extract_photos_from_html(html, source="seloger")

        assert photos == []

    def test_deduplicates_same_base_url(self):
        html = """
        <html><body>
            <img src="https://mms.seloger.com/photo/abc.jpg?w=200">
            <img src="https://mms.seloger.com/photo/abc.jpg?w=800">
        </body></html>
        """

        photos = extract_photos_from_html(html, source="seloger")

        assert len(photos) == 1

    def test_extracts_from_background_style(self):
        html = """
        <html><body>
            <div style="background-image: url('https://mms.seloger.com/photo/bg.jpg')"></div>
        </body></html>
        """

        photos = extract_photos_from_html(html, source="seloger")

        assert len(photos) == 1
        assert "mms.seloger.com" in photos[0]
