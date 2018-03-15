import argparse
import os
import requests
import time

from csv import DictReader, DictWriter
from datetime import datetime
from geopy.distance import distance
from io import StringIO
from lxml import etree

DARK_SKY_API_KEY = os.environ.get('DARK_SKY_API_KEY', '')
DARK_SKY_FORECAST_BASE = 'https://api.darksky.net/forecast/{api_key}/{latitude},{longitude}'
GOOGLE_MAPS_DIRECTIONS_API_KEY = os.environ.get('GOOGLE_MAPS_DIRECTIONS_API_KEY', '')

def get_forecast_for_coords(lat, lon, num_days_past_today):
  url = DARK_SKY_FORECAST_BASE.format(api_key=DARK_SKY_API_KEY, latitude=lat, longitude=lon)
  try:
    response = requests.get(url).json()
  except:
    print('Error getting URL {}'.format(url))
    return {
      'forecast_date_for': '',
      'forecast_timestamp': 0,
      'forecast_text': '',
      'cloud_cover': 1
    }
  forecast = response['daily']['data'][num_days_past_today]
  forecast_date_for = datetime.fromtimestamp(int(forecast['time'])).strftime('%a, %b %d, %Y')
  forecast_text = generate_text_from_forecast(forecast)
  return {
    'forecast_date_for': forecast_date_for,
    'forecast_timestamp': int(forecast['time']),
    'forecast_text': forecast_text,
    'cloud_cover': float(forecast['cloudCover'])
  }

def generate_text_from_forecast(forecast):
  forecast['cloudCoverPct'] = 100. * forecast['cloudCover']
  time_fmt = '%H:%M:%S'
  forecast['sunriseParsedTime'] = datetime.fromtimestamp(
    int(forecast['sunriseTime'])).strftime(time_fmt)
  forecast['sunsetParsedTime'] = datetime.fromtimestamp(
    int(forecast['sunsetTime'])).strftime(time_fmt)
  try:
    forecast['precipMaxParsedTime'] = datetime.fromtimestamp(
      int(forecast['precipIntensityMaxTime'])).strftime(time_fmt)
  except:
    forecast['precipMaxParsedTime'] = '(no max time)'
  if not forecast.get('precipAccumulation', None):
    forecast['precipAccumulation'] = 0
  forecast['precipChance'] = 100. * forecast['precipProbability']
  forecast['precipString'] = ''
  if forecast.get('precipType', None):
    forecast['precipString'] = (
      '\n{precipChance:.1f}% chance of {precipType}; maximum intensity at'.format(**forecast) +
      ' {precipMaxParsedTime}, with {precipAccumulation} inches of snow expected all day'.format(
        **forecast))
  if not forecast.get('visibility', None):
    forecast['visibility'] = ''
  forecast['summary'] = forecast['summary'].encode('utf-8', 'ignore')

  return """{summary}
High: will feel like {apparentTemperatureHigh} degrees F
Low: will feel like {apparentTemperatureLow} degrees F{precipString}
Cloud cover will be {cloudCoverPct:.0f}%
UV will be {uvIndex} out of 12
Wind speed will be {windSpeed} mph
Visibility will be {visibility} miles
Sun will rise at {sunriseParsedTime} and set at {sunsetParsedTime}
""".format(**forecast)

def extract_info_from_wta_result(fetch_result):
  parser = etree.HTMLParser()
  tree = etree.parse(StringIO(fetch_result), parser)
  lat = tree.xpath('//*[@id="trailhead-map"]/div[3]/span[1]')
  lon = tree.xpath('//*[@id="trailhead-map"]/div[3]/span[2]')
  name = tree.xpath('//*[@id="hike-top"]/h1')
  region = tree.xpath('//*[@id="hike-region"]/span')
  length = tree.xpath('//*[@id="distance"]/span')
  rating = tree.xpath('//*[@id="rating-stars-view-trail-rating"]/div/div[1]/div')
  height_gain = tree.xpath('//*[@id="hike-stats"]/div[3]/div[1]/span')
  return {
    'lat': float(lat[0].text) if lat else None,
    'lon': float(lon[0].text) if lon else None,
    'name': name[0].text if name else '',
    'region': region[0].text if region else '',
    'length': length[0].text if length else '',
    'rating': rating[0].text if rating else '',
    'height_gain': height_gain[0].text if height_gain else ''
  }

def get_travel_time_from_point_to_point(start_coords, end_coords, depart_time, verbose):
  url = ('https://maps.googleapis.com/maps/api/directions/json?' +
         'origin={0},{1}&'.format(start_coords['lat'], start_coords['lon']) +
         'destination={0},{1}&'.format(end_coords['lat'], end_coords['lon']) +
         'units=imperial&departure_time={0}&'.format(depart_time) +
         'traffic_model=best_guess&key={0}'.format(GOOGLE_MAPS_DIRECTIONS_API_KEY))
  response = requests.get(url).json()

  try:
    distance_meters = response['routes'][0]['legs'][0]['distance']['value']
    duration_seconds = response['routes'][0]['legs'][0]['duration_in_traffic']['value']
  except Exception as e:
    if verbose:
      print('Error fetching route: {0} - URL was {1}'.format(e, url))
    return {'distance': None, 'duration': None, 'duration_seconds': None}

  # First, grab number of hours and remainder in seconds
  divmod_hours = divmod(duration_seconds, 60*60)

  # Now, convert remainder in seconds into minutes and seconds
  divmod_minutes = divmod(divmod_hours[1], 60)

  return {
    'distance': distance_meters * 0.000621371,
    'duration': '{0}:{1}:{2}'.format(
      str(divmod_hours[0]).zfill(2),
      str(divmod_minutes[0]).zfill(2),
      str(divmod_minutes[1]).zfill(2)),
    'duration_seconds': duration_seconds
  }

def load_hike_data(force_refetch=False):
  hikes = []

  if not force_refetch:
    with open('snowshoe_hikes.csv') as fh:
      reader = DictReader(fh)
      [hikes.append(hike) for hike in reader]

  if not len(hikes) or force_refetch:
    with open('snowshoe_urls.txt') as fh:
      for url in fh.readlines():
        response = requests.get(url)

        try:
          info = extract_info_from_wta_result(response.text)
          info['url'] = url
        except Exception as e:
          print('Error processing response for {0} - {1}, skipping'.format(hike, e))
          continue

        hikes.append(info)
  return hikes

def write_hike_data(hikes):
  header = ['lat', 'lon', 'name', 'region', 'height_gain', 'length', 'rating', 'url']

  with open('snowshoe_hikes.csv', 'w+') as fh:
    writer = DictWriter(fh, sorted(header))
    writer.writeheader()
    writer.writerows([{key: h[key] for key in header} for h in hikes])

def format_and_filter_hikes(config):
  results = []
  snowshoe_hikes = load_hike_data()

  if config['save_new_hike_data']:  # Enable to save new hike data
    write_hike_data(snowshoe_hikes)

  if config['verbose']:
    print('Found {0} hikes'.format(len(snowshoe_hikes)))

  distance_cutoff = config['num_hours_to_drive'] * 75.

  for hike in snowshoe_hikes:
    if not hike['lat'] or not hike['lon']:
      continue

    dist = distance(
      (config['depart_lat'], config['depart_lon']), (float(hike['lat']), float(hike['lon']))).miles
    if dist >= distance_cutoff:
      if config['verbose']:
        print('Distance is too far - {0} miles'.format(dist))
      continue

    try:
      forecast = get_forecast_for_coords(hike['lat'], hike['lon'], config['num_days_past_today'])
      hike.update(forecast)
    except Exception as e:
      if config['verbose']:
        print('Error getting forecast for {0} - {1}, skipping'.format(hike, e))
      continue

    depart_time = (
      forecast['forecast_timestamp'] + 60 * 60 * config['num_hours_past_midnight_to_leave'])
    if config['num_days_past_today'] == 0 and config['num_hours_past_midnight_to_leave'] == 0:
      depart_time = int(time.time()) + 60 * 5  # Leave 5 minutes in future so GMaps API call works

    try:
      route_info = get_travel_time_from_point_to_point(
        {'lat': config['depart_lat'], 'lon': config['depart_lon']},
        {'lat': hike['lat'], 'lon': hike['lon']},
        depart_time,
        config['verbose'])
      hike.update(route_info)
    except Exception as e:
      if config['verbose']:
        print('Error getting travel info for {0} - {1}, skipping'.format(hike, e))
      continue

    if route_info['distance']:
      results.append(hike)

  cutoff = 60 * 60 * config['num_hours_to_drive']

  if config['verbose']:
    print('Found {0} hike candidates'.format(len(results)))

  for hike in filter(
      lambda x: x['duration_seconds'] <= cutoff, sorted(
        results, key=lambda k: float(k['cloud_cover']), reverse=False)):
    title_string = 'Forecast for {name} ({region}) for {forecast_date_for}:'.format(**hike)
    info_string = 'Hike is {length}; gains {height_gain} feet; and has {rating} stars'.format(
      **hike)
    route_string = 'Drive will take {duration} to cover {distance:.2f} miles'.format(**hike)
    print('{0}\n{1}\n{2}\n{3}\n{4}\n-----'.format(
      title_string, hike['url'], info_string, route_string, hike['forecast_text']))


if __name__ == '__main__':
  parser = argparse.ArgumentParser()

  parser.add_argument(
    '--depart_lat',
    help='latitude to calculate departure distance and time from',
    type=float,
    default=47.612679)

  parser.add_argument(
    '--depart_lon',
    help='longitude to calculate departure distance and time from',
    type=float,
    default=-122.30115)

  parser.add_argument(
    '--num_days_past_today',
    help="""number of days after today to generate results for. set to 0, along with
num_hours_past_midnight_to_leave, to get results for right now.""",
    type=int,
    default=1)

  parser.add_argument(
    '--num_hours_past_midnight_to_leave',
    help="""number of hours after midnight to generate driving times for. set to 0, along with
num_days_past_today, to get results for right now.""",
    type=int,
    default=9)

  parser.add_argument(
    '--num_hours_to_drive',
    help='maximum number of hours to drive from destination',
    type=float,
    default=1.5)

  parser.add_argument(
    '--save_new_hike_data',
    help='update cached hike data',
    action='store_true',
    default=False)

  parser.add_argument(
    '--verbose',
    help='show verbose logging information',
    action='store_true',
    default=False)

  args = parser.parse_args()
  config = {
    'depart_lat': args.depart_lat,
    'depart_lon': args.depart_lon,
    'num_days_past_today': args.num_days_past_today,
    'num_hours_past_midnight_to_leave': args.num_hours_past_midnight_to_leave,
    'num_hours_to_drive': args.num_hours_to_drive,
    'save_new_hike_data': args.save_new_hike_data,
    'verbose': args.verbose
  }
  format_and_filter_hikes(config)
