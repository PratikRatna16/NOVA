#!/usr/bin/env python3
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
import urllib.request
import urllib.parse
import urllib.error

CONFIG_FILE = Path.home() / ".weather_config.json"

def load_config():
    """Load configuration from file."""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_config(api_key):
    """Append API key to configuration file."""
    config = load_config()
    config['api_key'] = api_key
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f)

def infer_system_defaults():
    """Infer defaults from system settings."""
    locale = os.getenv('LANG', 'en') or 'en'
    lang = locale.split('.')[0].split('_')[0]
    units = 'imperial' if os.getenv('LANG', '').startswith('en_US') else 'metric'
    return lang, units

def validate_days(days):
    """Validate days parameter within 1-14 range."""
    if not 1 <= days <= 14:
        raise ValueError("--days must be between 1 and 14")
    return days

def build_forecast_url(location, api_key, units, lang):
    """Build API request URL for forecast."""
    params = {
        'q': location,
        'appid': api_key,
        'units': units,
        'lang': lang
    }
    return f"http://api.openweathermap.org/data/2.5/forecast?{urllib.parse.urlencode(params)}"

def fetch_weather_data(url):
    """Fetch data from API."""
    try:
        with urllib.request.urlopen(url) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        return {'error': e.code, 'reason': e.reason}
    except urllib.error.URLError as e:
        return {'error': str(e.reason)}

def process_forecast_data(data, days):
    """Process API response and extract daily forecasts."""
    if 'error' in data:
        return data
    
    daily_data = {}
    for entry in data.get('list', []):
        dt_txt = entry.get('dt_txt', '')
        date = dt_txt[:10]
        if date not in daily_data:
            daily_data[date] = {
                'temps': [],
                'winds': [],
                'humidities': [],
                'descriptions': []
            }
        temp = entry['main']['temp']
        daily_data[date]['temps'].append(temp)
        daily_data[date]['winds'].append(entry['wind']['speed'])
        daily_data[date]['humidities'].append(entry['main']['humidity'])
        daily_data[date]['descriptions'].append(entry['weather'][0]['description'])
    
    forecasts = []
    for date in sorted(daily_data.keys())[:days]:
        day = daily_data[date]
        forecasts.append({
            'date': date,
            'high': max(day['temps']),
            'low': min(day['temps']),
            'description': day['descriptions'][0],
            'wind_speed': sum(day['winds']) / len(day['winds']),
            'humidity': int(sum(day['humidities']) / len(day['humidities']))
        })
    
    return forecasts

def format_forecast(forecast, units):
    """Format forecast for display."""
    unit_symbol = '°C' if units == 'metric' else '°F'
    wind_unit = 'm/s' if units == 'metric' else 'mph'
    
    lines = []
    for day in forecast:
        date_str = datetime.strptime(day['date'], '%Y-%m-%d').strftime('%A, %B %d')
        lines.append(f"{date_str}")
        lines.append(f"  High: {day['high']:.1f}{unit_symbol}")
        lines.append(f"  Low:  {day['low']:.1f}{unit_symbol}")
        lines.append(f"  Wind: {day['wind_speed']:.1f} {wind_unit}")
        lines.append(f"  Humidity: {day['humidity']}%")
        lines.append(f"  {day['description'].capitalize()}")
        lines.append("")
    
    return "\n".join(lines).rstrip()

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Weather CLI Tool')
    parser.add_argument('-k', '--api-key', help='OpenWeatherMap API key')
    parser.add_argument('-l', '--location', help='Location (city/country/zip)')
    parser.add_argument('-u', '--units', choices=['metric', 'imperial'], default=None)
    parser.add_argument('-lang', '--language', default=None)
    parser.add_argument('-d', '--days', type=int, default=7)
    parser.add_argument('location_pos', nargs='*', help='Location as positional argument')
    
    args = parser.parse_args()
    
    # Determine location
    location = args.location or ' '.join(args.location_pos)
    if not location:
        print("Error: Location is required")
        sys.exit(1)
    
    # Determine API key
    api_key = args.api_key or load_config().get('api_key')
    if not api_key:
        print("Error: API key is required. Use --api-key or set it in config")
        sys.exit(1)
    
    # Save API key if provided via CLI
    if args.api_key:
        save_config(args.api_key)
    
    # Infer or use provided units and language
    default_lang, default_units = infer_system_defaults()
    units = args.units or default_units
    lang = args.language or default_lang
    
    try:
        days = validate_days(args.days)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
    
    url = build_forecast_url(location, api_key, units, lang)
    data = fetch_weather_data(url)
    
    if 'error' in data:
        if isinstance(data.get('error'), int):
            print(f"API Error ({data['error']}): {data.get('reason', 'Unknown error')}")
            if data['error'] == 401:
                print("Invalid API key. Get one from https://openweathermap.org/api")
            elif data['error'] == 404:
                print(f"Location '{location}' not found. Try a different location name.")
        else:
            print(f"Network Error: {data['error']}")
        sys.exit(1)
    
    forecast = process_forecast_data(data, days)
    output = format_forecast(forecast, units)
    print(output)

if __name__ == '__main__':
    main()