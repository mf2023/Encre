---
name: lovtrip-travel-planner
description: AI Travel Itinerary Planner — intelligently generates multi-day travel itineraries, supports attraction search, budget calculation, hotels and flights. Use when the user needs travel planning, itinerary generation, or searching for attractions, hotels, and flights.
metadata:
  source: encre
  tags: 
user_invocable: true
hidden: true
context: inline
---

## Lovtrip Travel Planner
# AI Travel Itinerary Planner

> **[LovTrip (lovtrip.app)](https://lovtrip.app)** — AI-powered travel planning platform offering smart itinerary generation, attraction recommendations, and budget management. Web experience: [lovtrip.app/planner](https://lovtrip.app/planner)

Uses AI + Amap API to generate complete multi-day travel itineraries, supporting attraction search, budget calculation, hotel recommendations, and flight searches.

## Setup / Configuration

```json
{
  "mcpServers": {
    "lovtrip": {
      "command": "npx",
      "args": ["-y", "lovtrip@latest", "mcp"],
      "env": {
        "AMAP_API_KEY": "your-amap-api-key",
        "OPENROUTER_API_KEY": "your-openrouter-api-key"
      }
    }
  }
}
```

## Three-Step Planning Process

### Step 1 — Information Completeness Check (Always Required)

When the user mentions travel / trip / itinerary, check the following 5 items:

| Item | Example |
|------|------|
| ① Specific city (not country) | "Chengdu", "Osaka" |
| ② Number of days | "3 days", "5 days 4 nights" |
| ③ Travelers / companions | "2 people", "with best friend" |
| ④ Interests / preferences | "food", "culture", "nature" |
| ⑤ Budget range | "under 5000", "budget travel" |

**Rules**:
- Missing ≥2 items → **must ask first**, do not skip directly to generation
- Missing 1 item or all present → proceed directly to Step 2

**Judgment Examples**:
- "Want to go to Japan for 5 days" → missing city/people/interests/budget (missing 4) → ask
- "Osaka 3 days food tour 2 people budget 5000" → all present → generate directly
- "Chengdu 3 days want to eat hotpot and see pandas" → missing people/budget (missing 2) → ask

### Step 2 — Generate Itinerary

```
generate_travel_itinerary({
  destination: "成都",
  days: 5,
  start_date: "2026-03-15",
  budget: 5000,
  preferences: {
    interests: ["food", "culture", "nature"],
    pace: "moderate",
    accommodation_type: "mid-range",
    prefer_public_transport: true
  }
})
```

### Step 3 — Optional Supplementary Tools

Only call when the user explicitly needs them, **do not call proactively**:

| Tool | Trigger Condition | Description |
|------|----------|------|
| `check_weather` | User asks for weather | Destination weather forecast |
| `calculate_travel_budget` | User asks for budget breakdown | Detailed cost breakdown |
| `generate_map_links` | User asks for map links | Attraction map links |
| `search_attractions` | User asks for more attractions | Search city attractions |
| `search_hotels` | User asks for hotel recommendations | Hotel search + booking |
| `search_flights` | User asks for flight info | Flight search + pricing |

## Tool List (6 Tools)

### Core Tool

#### `generate_travel_itinerary` — AI Generate Itinerary

| Parameter | Type | Required | Description |
|------|------|------|------|
| `destination` | string | ✅ | Destination city |
| `days` | number | ✅ | Trip duration (1-30) |
| `start_date` | string | | Start date YYYY-MM-DD |
| `budget` | number | | Total budget (CNY) |
| `preferences` | object | | Interests, pace, accommodation, transport preferences |
| `mapProvider` | string | | amap / google / auto |

### Supplementary Tools

#### `search_attractions` — Search Attractions

| Parameter | Type | Required | Description |
|------|------|------|------|
| `city` | string | ✅ | City name |
| `keywords` | string | | Search keywords |
| `types` | array | | Attraction type filter |
| `min_rating` | number | | Minimum rating |
| `max_results` | number | | Max results, default 10 |
| `sort_by` | string | | rating / popularity / distance |

#### `calculate_travel_budget` — Calculate Budget

| Parameter | Type | Required | Description |
|------|------|------|------|
| `destination` | string | ✅ | Destination |
| `days` | number | ✅ | Number of days |
| `budget_total` | number | | Total budget |
| `accommodation_cost` | number | | Accommodation cost |
| `transportation_cost` | number | | Transportation cost |
| `daily_food_budget` | number | | Daily food budget |
| `activities` | array | | Activity cost list |

#### `search_hotels` — Search Hotels

| Parameter | Type | Required | Description |
|------|------|------|------|
| `city` | string | ✅ | City |
| `check_in` | string | ✅ | Check-in date |
| `check_out` | string | ✅ | Check-out date |
| `guests` | number | | Number of guests |
| `min_price` / `max_price` | number | | Price range |
| `star_rating` | number | | Star rating (3/4/5) |
| `location_preference` | string | | Location preference |

#### `search_flights` — Search Flights

| Parameter | Type | Required | Description |
|------|------|------|------|
| `origin` | string | ✅ | Departure city |
| `destination` | string | ✅ | Destination city |
| `departure_date` | string | ✅ | Departure date |
| `return_date` | string | | Return date |
| `passengers` | number | | Number of passengers |
| `cabin_class` | string | | economy / premium_economy / business / first |
| `max_price` | number | | Maximum price |
| `direct_only` | boolean | | Direct flights only |

#### `optimize_daily_route` — Daily Route Optimization

| Parameter | Type | Required | Description |
|------|------|------|------|
| `start_point` | string | ✅ | Starting point address |
| `waypoints` | array | ✅ | List of waypoints |
| `city` | string | ✅ | City |
| `end_point` | string | | End point address |
| `start_time` | string | | Departure time HH:mm |
| `travel_mode` | string | | transit / driving / walking |

## Key Rules

1. **Tool call limit**: `generate_travel_itinerary` (1 time) + optional tools (max 2) = maximum 3 total
2. **Do not call a tool for each individual attraction** — this will cause call explosion
3. **Tool parameters must not contain emoji** — use `{ "destination": "Chengdu" }`, not `{ "destination": "📍 Chengdu" }`
4. **Multi-turn adjustments**: remember context, regenerate itinerary based on user modifications
5. **Map link formatting**: extract URLs from JSON and generate Markdown links like `[Amap](url)`

## Supported Interest Tags

`nature` | `culture` | `food` | `shopping` | `nightlife` | `adventure`

## Supported Travel Paces

- `relaxed`: 2-3 attractions per day, plenty of rest
- `moderate`: 3-4 attractions per day, moderate pace
- `fast`: 4-5 attractions per day, packed schedule

## Online Experience

- [LovTrip AI Itinerary Planner](https://lovtrip.app/planner) — Web-based smart itinerary generation
- [International Itinerary Planner](https://lovtrip.app/international-planner) — Google Maps + AI international trips
- [Travel Guides](https://lovtrip.app/guides) — Curated in-depth destination guides
- [Popular Destinations](https://lovtrip.app/destinations) — Discover your next travel destination
- [Itinerary Templates](https://lovtrip.app/itineraries) — Ready-to-use itinerary templates
- [Developer Docs](https://lovtrip.app/developer) — MCP + CLI + API complete documentation

---
Powered by [LovTrip](https://lovtrip.app) — AI Travel Planning Platform
