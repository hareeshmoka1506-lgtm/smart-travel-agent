import json
import httpx
#from duckduckgo_search import DDGS
from ddgs import DDGS

try:
    from mcp.server.fastmcp import FastMCP
    mcp = FastMCP("travel-agent-mcp")
except Exception:
    try:
        from mcp.server.mcpserver import MCPServer
        mcp = MCPServer("travel-agent-mcp")
    except Exception:
        class FallbackMCP:
            def tool(self):
                def decorator(f):
                    return f
                return decorator
            def run(self):
                pass
        mcp = FallbackMCP()

@mcp.tool()
def search_travel_web(query: str) -> str:
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
            if not results:
                return "No search results found."
            formatted = []
            for r in results:
                formatted.append(f"Title: {r.get('title')}\nSnippet: {r.get('body')}\nURL: {r.get('href')}")
            return "\n\n".join(formatted)
    except Exception as e:
        return f"Error executing web search: {str(e)}"

@mcp.tool()
def get_weather(city: str) -> str:
    try:
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1&language=en&format=json"
        with httpx.Client(timeout=10.0) as client:
            geo_res = client.get(geo_url).json()
            if not geo_res.get("results"):
                return f"Could not find coordinates for {city}."
            
            lat = geo_res["results"][0]["latitude"]
            lon = geo_res["results"][0]["longitude"]
            country = geo_res["results"][0].get("country", "")

            weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max&timezone=auto"
            weather_res = client.get(weather_url).json()
            
            cw = weather_res.get("current_weather", {})
            temp = cw.get("temperature")
            wind = cw.get("windspeed")
            
            return json.dumps({
                "city": city,
                "country": country,
                "current_temperature_celsius": temp,
                "windspeed_kmh": wind,
                "daily_forecast": weather_res.get("daily", {})
            }, indent=2)
    except Exception as e:
        return f"Error fetching weather for {city}: {str(e)}"

@mcp.tool()
def calculate_budget(destination: str, days: int, travelers: int, travel_style: str = "moderate") -> str:
    # Updated multipliers to reflect realistic global travel costs
    style_multipliers = {
        "budget": 80,
        "moderate": 250,
        "luxury": 1600  # Realistic baseline for ultra-luxury experiences (5-star hotels, private transport, fine dining)
    }
    
    base_per_day = style_multipliers.get(travel_style.lower(), 250)
    
    # Cost allocation breakdown
    hotel_cost = base_per_day * 0.5 * days * ((travelers + 1) // 2)
    food_cost = base_per_day * 0.3 * days * travelers
    activity_cost = base_per_day * 0.2 * days * travelers
    total = hotel_cost + food_cost + activity_cost

    return json.dumps({
        "destination": destination,
        "duration_days": days,
        "travelers": travelers,
        "style": travel_style,
        "estimated_costs_usd": {
            "accommodation": round(hotel_cost, 2),
            "food_and_dining": round(food_cost, 2),
            "activities_and_transport": round(activity_cost, 2),
            "total_estimated_usd": round(total, 2)
        }
    }, indent=2)

if __name__ == "__main__":
    mcp.run()
