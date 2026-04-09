from app.services.weather_service import get_weather

async def monitor():
    data = await get_weather("Jakarta")

    rain = data.get("weather", [{}])[0].get("main")

    if rain == "Rain":
        status = "SIAGA"
    else:
        status = "NORMAL"

    return {
        "status": status,
        "weather": data
    }