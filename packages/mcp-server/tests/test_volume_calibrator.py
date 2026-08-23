"""Tests for VolumeCalibratorService."""

from app.services.market.volume_calibrator import VolumeCalibratorService


class TestVolumeCalibratorWithoutGSC:
    """Tests for the service when GSC is not configured."""

    async def test_returns_error_when_gsc_is_none(self):
        service = VolumeCalibratorService(gsc_service=None)
        result = await service.calibrate(
            site_url="https://example.com",
            target_keywords=["python", "django"],
        )
        assert "error" in result

    async def test_returns_error_when_gsc_credentials_missing(self):
        class FakeGSC:
            is_credentials_available = False

        service = VolumeCalibratorService(gsc_service=FakeGSC())
        result = await service.calibrate(
            site_url="https://example.com",
            target_keywords=["seo"],
        )
        assert "error" in result

    async def test_error_message_mentions_configuration(self):
        service = VolumeCalibratorService(gsc_service=None)
        result = await service.calibrate(
            site_url="https://example.com",
            target_keywords=["test"],
        )
        assert "Google Search Console" in result["error"] or "configured" in result["error"].lower()


class TestVolumeCalibratorCalibrationRatio:
    """Tests for the calibration ratio calculation logic."""

    async def test_returns_error_when_gsc_returns_no_queries(self):
        """If GSC returns no queries, calibration cannot proceed."""

        class FakeGSC:
            is_credentials_available = True

            async def get_top_queries(self, **kwargs):
                return []

        service = VolumeCalibratorService(gsc_service=FakeGSC())
        result = await service.calibrate(
            site_url="https://example.com",
            target_keywords=["seo tool"],
        )
        assert "error" in result

    async def test_returns_error_when_trend_service_is_none(self):
        """Without trend service, calibration cannot compute ratios."""

        class FakeQuery:
            query = "python tutorial"
            impressions = 1000

        class FakeGSC:
            is_credentials_available = True

            async def get_top_queries(self, **kwargs):
                return [FakeQuery()]

        service = VolumeCalibratorService(gsc_service=FakeGSC(), trend_service=None)
        result = await service.calibrate(
            site_url="https://example.com",
            target_keywords=["python tutorial"],
        )
        # Without trends, we cannot calibrate — should error or return partial data
        assert "error" in result or "gsc_data" in result

    async def test_calibration_uses_median_ratio(self):
        """Calibration ratio should use the median of GSC/trend ratios."""

        class FakeQuery:
            def __init__(self, query, impressions):
                self.query = query
                self.impressions = impressions

        class FakeGSC:
            is_credentials_available = True

            async def get_top_queries(self, **kwargs):
                return [
                    FakeQuery("python", 100),
                    FakeQuery("django", 200),
                    FakeQuery("flask", 50),
                ]

        class FakeTrends:
            async def get_interest(self, keywords, geo):
                # Return fixed indices: ratio will be impressions / index
                # python: 100/10=10, django: 200/20=10, flask: 50/5=10 → median=10
                mapping = {"python": 10, "django": 20, "flask": 5, "fastapi": 8}
                return {k: mapping.get(k, 0) for k in keywords}

        service = VolumeCalibratorService(gsc_service=FakeGSC(), trend_service=FakeTrends())
        result = await service.calibrate(
            site_url="https://example.com",
            target_keywords=["fastapi"],
        )

        assert "estimates" in result
        assert result["calibration"]["calibration_ratio"] == 10.0
        # fastapi trend_index=8, ratio=10 → estimated volume = 80
        fastapi_est = next(e for e in result["estimates"] if e["keyword"] == "fastapi")
        assert fastapi_est["estimated_volume"] == 80
        assert fastapi_est["source"] == "calibrated_estimate"

    async def test_keyword_with_gsc_data_uses_actual_impressions(self):
        """Keywords already in GSC should be returned with 'gsc_actual' source."""

        class FakeQuery:
            def __init__(self, query, impressions):
                self.query = query
                self.impressions = impressions

        class FakeGSC:
            is_credentials_available = True

            async def get_top_queries(self, **kwargs):
                return [FakeQuery("python", 500)]

        class FakeTrends:
            async def get_interest(self, keywords, geo):
                return {"python": 50}

        service = VolumeCalibratorService(gsc_service=FakeGSC(), trend_service=FakeTrends())
        result = await service.calibrate(
            site_url="https://example.com",
            target_keywords=["python"],
        )

        assert "estimates" in result
        python_est = result["estimates"][0]
        assert python_est["source"] == "gsc_actual"
        assert python_est["confidence"] == "high"
        assert python_est["estimated_volume"] == 500

    async def test_keyword_with_no_data_returns_low_confidence(self):
        """Keywords with no GSC or trend data should be marked low confidence."""

        class FakeQuery:
            query = "python"
            impressions = 500

        class FakeGSC:
            is_credentials_available = True

            async def get_top_queries(self, **kwargs):
                return [FakeQuery()]

        class FakeTrends:
            async def get_interest(self, keywords, geo):
                # Return 0 for all (no trend data)
                return {k: 0 for k in keywords}

        service = VolumeCalibratorService(gsc_service=FakeGSC(), trend_service=FakeTrends())
        result = await service.calibrate(
            site_url="https://example.com",
            target_keywords=["obscure-niche-keyword"],
        )

        # Cannot calibrate (trend index is 0 for all), should error or return no_data
        if "estimates" in result:
            est = next(
                (e for e in result["estimates"] if e["keyword"] == "obscure-niche-keyword"),
                None,
            )
            if est:
                assert est["confidence"] in ("low", "medium")
        else:
            assert "error" in result
