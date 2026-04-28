def test_api_import():
    import app.api.main  # noqa: F401


def test_inference_import():
    from app.realtime_native import inference  # noqa: F401
