from dotenv import load_dotenv
import os
import httpx

# load file .env
load_dotenv()

# ambil API key
API_KEY = os.getenv("OPENWEATHER_API_KEY")
print(API_KEY)

async def get_weather(city="Jakarta"):
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={API_KEY}"

    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        return response.json()