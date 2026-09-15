import httpx
import asyncio

async def fetch_current_weather(lat: float, lon: float) -> dict:
    """
    Fetches real-time weather from Open-Meteo for the given coordinates.
    Returns a dict containing 'temperature_c' and 'humidity_pct', or None if failed.
    """
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            
            current = data.get("current", {})
            if "temperature_2m" in current:
                return {
                    "temperature_c": float(current["temperature_2m"]),
                    "humidity_pct": float(current.get("relative_humidity_2m", 50.0))
                }
    except Exception as e:
        print(f"[WeatherService] Failed to fetch live weather for ({lat}, {lon}): {e}")
    
    return None
