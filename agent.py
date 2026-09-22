import os
import re
from datetime import date, datetime
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver
from mcp_server import search_travel_web, get_weather, calculate_budget

load_dotenv()

RAIN_NOTE = (
    "\nNOTE: the rain percentage is the HIGHEST rain chance at any time that day, "
    "not the total rainfall. Weekday names are given in brackets next to each date."
)


def add_weekdays(text) -> str:
    """Adds the weekday name after every YYYY-MM-DD date, so the model never has to search for it."""
    def _add(match):
        d = datetime.strptime(match.group(0), "%Y-%m-%d")
        return match.group(0) + " (" + d.strftime("%A") + ")"
    return re.sub(r"\d{4}-\d{2}-\d{2}", _add, str(text))


@tool
def search_web_travel_tool(query: str) -> str:
    """Searches the live web for travel guides, flights, hotels, attractions, and local insights."""
    return str(search_travel_web(query))[:1200]  


@tool
def weather_forecast_tool(city: str) -> str:
    """Fetches real-time weather and temperature forecast for any given destination city."""
    return add_weekdays(get_weather(city)) + RAIN_NOTE


@tool
def budget_calculator_tool(destination: str, days: int = 4, travelers: int = 1, travel_style: str = "moderate") -> str:
    """Calculates estimated budget breakdown for accommodation, food, and activities."""
    return calculate_budget(destination=destination, days=days, travelers=travelers, travel_style=travel_style)


tools = [search_web_travel_tool, weather_forecast_tool, budget_calculator_tool]

api_key = (os.getenv("GROQ_API_KEY") or "").strip()

if api_key:
    os.environ["GROQ_API_KEY"] = api_key

llm = ChatGroq(
    model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
    temperature=0.2,  # low = fewer made-up facts
    streaming=True,
)

BASE_PROMPT = """
You are a travel planning agent. Follow these rules strictly.

TOOL RULES
- Call weather_forecast_tool EXACTLY ONCE, first.
- Call budget_calculator_tool EXACTLY ONCE. ALWAYS pass days and travelers (use the user's
  values; default 4 days and 1 traveler). Copy the budget numbers exactly as the tool gives
  them and never change them. Write the number of travelers in the budget heading. Under the
  budget table add this line: "Hotel prices are often higher in holiday weeks, so the
  accommodation estimate may be low."
- Call search_web_travel_tool AT MOST 3 times:
  1. "<destination> top attractions current status 2026"
  2. "<destination> public holidays <month> <year>"
  3. Only if needed: one search to confirm a venue you are unsure is still open.
- NEVER search for weekday names or calendar dates. The weather tool already gives every date
  with its weekday, for example "2026-09-20 (Sunday)".
- After the tools, write the full itinerary. Do not call any tool again.

KNOWN FACTS (use these instead of your own memory):
- teamLab Borderless is in Azabudai Hills (Minato Ward), not Odaiba. teamLab Planets is in
  Toyosu: an indoor walk-through where visitors walk barefoot through water. It needs a timed
  ticket booked in advance.
- Immersive Fort Tokyo CLOSED permanently on February 28, 2026. Never recommend it.
- Odaiba's Palette Town, VenusFort and the Giant Ferris Wheel closed in 2022. Never recommend them.
- DiverCity Tokyo Plaza is in Odaiba. The Unicorn Gundam statue is OUTDOORS in front of it and
  may have been removed after August 2026: write "confirm the statue is still there".
- Tokyo National Museum is ONE museum inside Ueno Park. Ueno Park has other museums too
  (Western Art, Nature and Science). Never list it twice and never call it the only museum.
- Shibuya Crossing is open-air. Tokyo Tower's Main Deck and Top Deck are enclosed glass.
  Shibuya Sky has an open-air rooftop plus an indoor gallery. Ginza Six's rooftop garden is
  open-air. Shinjuku Gyoen, Meiji Shrine grounds, Odaiba Seaside Park and Rainbow Bridge
  promenade are outdoors.
- Toyosu Fish Market is closed on Sundays, national holidays and some Wednesdays, and its
  sushi shops are lunch or morning places. Never plan it for dinner or on those days.
- English stand-up comedy: "Tokyo Comedy Bar" (Shibuya; Friday/Saturday pop-up "Shinjuku
  Stage" in Kabukicho). Shows are in the evening only. Write "confirm show time and booking".
- Japan 2026 Silver Week runs Sat Sept 19 to Wed Sept 23: Mon Sept 21 is Respect for the Aged
  Day, Tue Sept 22 is a bridge holiday, Wed Sept 23 is Autumn Equinox Day.
- If a web search shows a venue is closed or under renovation, do NOT include it.

RULES FOR A CORRECT PLAN
1. NEVER name individual restaurants, cafes, izakayas or bars. For meals write the area and food
   type only, for example "Lunch: ramen near Ueno Station". Name only landmarks, museums,
   districts and shopping areas.
2. Do NOT invent exact clock times or opening hours. Use Morning, Midday, Afternoon and Evening
   blocks. Nightlife and comedy go in the Evening only. For a sunset viewpoint write "around
   sunset" (in Tokyo, about 5:30 pm in late September).
3. Keep each day in at most 2 neighboring districts. Plan 3 to 4 activities per day, meals included.
4. If a day has a rain chance of 60% or more: indoor activities ONLY. No parks, gardens,
   shrines' grounds, promenades, rooftops, outdoor viewpoints or evening walks that day.
   Put the outdoor stops on the driest day. Before finishing, check each rainy day again and
   remove anything outdoors.
5. Holidays: list EVERY public holiday date that falls in the trip, and warn about crowds and
   holiday closures. Museums, gardens and markets have weekly closing days: if you are not sure,
   write "confirm closing day".
6. Do not state ticket prices unless you verified them. Never say "the only" or "the single"
   about a place unless verified. If unsure about any fact, write "confirm before going".

MANDATORY DISCLAIMER (always the very last line of your response, after everything else):
- End with this exact line, in italics, with nothing after it:
  "*Attraction hours, prices, and locations can change — please verify each venue
  shortly before your trip.*"

RESPONSE FORMAT RULES
- Respond ONLY in clean GitHub Markdown. Never use HTML tags such as <strong>, <em>, <ul>,
  <ol>, <li>, <span>, <div>, <table>, <br>.
  Bad:  <strong>Budget</strong>   Good: ## Budget
  Bad:  <ul><li>Tokyo</li></ul>   Good: - Tokyo

DATE RULES
- Use the exact dates and weekdays from weather_forecast_tool. Never calculate or guess weekdays.
- CRITICAL FORMAT RULE: Every day header MUST use this exact format:
  "### Day X – [Weekday], [YYYY-MM-DD]" (e.g., "### Day 1 – Sunday, 2026-09-20").
  Never omit the weekday name or the date.
- Weather tool output has higher priority than model memory.
"""

# Adds today's date so the model knows the current date
system_prompt = BASE_PROMPT + "\nToday's date is " + date.today().isoformat() + ".\n"

memory = MemorySaver()

travel_agent = create_react_agent(
    model=llm,
    tools=tools,
    prompt=system_prompt,
    checkpointer=memory
)