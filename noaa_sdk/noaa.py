"""
API Wrapper for NOAA API V3
===========================
For more detailed information about NOAA API,
visit: https://www.weather.gov/documentation/services-web-api


"""

import json
import math
from urllib.parse import urlencode
import pgeocode
from uszipcode import SearchEngine

from noaa_sdk.util import UTIL
from noaa_sdk.accept import ACCEPT
from noaa_sdk.errors import InvalidZipCodeError

class NOAA(UTIL):
    """Main class for getting data from NOAA."""

    DEFAULT_END_POINT = 'api.weather.gov'
    DEFAULT_USER_AGENT = 'Test (your@email.com)'

    def __init__(self, user_agent=None, accept=None, show_uri=False):
        """Constructor.

        Args:
            user_agent (str[optional]): user agent specified in the header.
            accept (str[optional]): accept string specified in the header.
            show_uri (boolean[optional]): True for showing the
                actual url with query string being sent for requesting data.
        """
        if not user_agent:
            user_agent = self.DEFAULT_USER_AGENT
        if not accept:
            accept = ACCEPT.GEOJSON

        super().__init__(
            user_agent=user_agent, accept=accept,
            show_uri=show_uri)

    def get_lat_lon_by_postalcode_country(self, postal_code, country='US', return_result_object=False):
        if country == "US":
            search = SearchEngine(simple_zipcode=True)
            zipcode = search.by_zipcode(postal_code)

            if zipcode.lat is None or zipcode.lng is None:
                raise InvalidZipCodeError('Invalid ZIP Code')
            
            if return_result_object:
                return zipcode.lat, zipcode.lng, zipcode
            
            return zipcode.lat, zipcode.lng
        else:
            nomi = pgeocode.Nominatim(country)
            query_results = nomi.query_postal_code(postal_code)

            if math.isnan(query_results.latitude) or math.isnan(query_results.longitude):
                raise InvalidZipCodeError('Invalid ZIP Code')
            
            if return_result_object:
                return query_results.latitude, query_results.longitude, query_results

            return query_results.latitude, query_results.longitude

    def get_forecasts(self, postal_code, country, data_type="grid", return_result_object=False):
        """Get forecasts by postal code and country code.

        Args:
            postalcode (str): postal code.
            country (str): 2 letter country code.
            hourly (boolean[optional]): True for getting hourly forecast.
        Returns:
            list: list of weather forecasts.
        """

        postalcode_search_result = self.get_lat_lon_by_postalcode_country(postal_code, country, return_result_object)
        
        if return_result_object:
            lat, lon, result_object = postalcode_search_result
        else:
            lat, lon = postalcode_search_result
        
        if type(data_type) is not list:
            data_type = [data_type]
        
        results = self.points_forecast(lat, lon, data_type=data_type)

        to_return = []
        for dtype, res in zip(data_type, results):
            if 'status' in res and res['status'] == 503 and 'detail' in res:
                raise Exception('Status: {}, NOAA API Error Response: {}'.format(
                    res['status'], res['detail']))
            elif 'properties' not in res:
                raise Exception(
                    '"properties" attribute not found. Possible response json changes')
            elif 'properties' in res and 'periods' not in res['properties'] and dtype != "grid":
                raise Exception(
                    '"periods" attribute not found. Possible response json changes')
            if dtype == "grid":
                to_return.append(res['properties'])
            else:
                to_return.append(res['properties']['periods'])
        
        if return_result_object:
            return to_return, result_object
        return to_return

    def get_observations(
            self, postalcode, country, start=None, end=None, num_of_stations=1):
        """Get all nearest station observations by postalcode and
        country code.

           This is an extensive functionality, aligning data
           from Open Street Map to enable postal code and country code
           params for weather observation data.

        Args:
            postalcode (str): postal code.
            country (str): 2 letter country code.
            start (str[optional]): start date of observation
                (eg. '%Y-%m-%dT%H:%M:%SZ' | '%Y-%m-%d' | '%Y-%m-%d %H:%M:%S').
            end (str[optional]): end date of observation
                (eg. '%Y-%m-%dT%H:%M:%SZ' | '%Y-%m-%d' | '%Y-%m-%d %H:%M:%S').
            num_of_stations (int[optional]): get observations from the
                nearest x stations. (Put -1 of wants to get all stations.)
        Returns:
            generator: generator of dictionaries of observations with the
            following variables: 'relativeHumidity', 'presentWeather',
            'minTemperatureLast24Hours', 'windGust', 'precipitationLast6Hours',
            'cloudLayers', 'dewpoint', 'temperature', 'windDirection',
            'rawMessage', '@type', 'precipitationLast3Hours',
            'visibility', 'icon', 'barometricPressure', 'windChill',
            'station', 'textDescription', 'seaLevelPressure', '@id',
            'timestamp', 'maxTemperatureLast24Hours', 'precipitationLastHour',
            'heatIndex', 'windSpeed', 'elevation'
        """

        lat, lon = self.get_lat_lon_by_postalcode_country(
            postalcode, country)
        
        return self.get_observations_by_lat_lon(lat, lon, start, end, num_of_stations)
        
    def get_observations_by_lat_lon(
            self, lat, lon, start=None, end=None, num_of_stations=1):
        "Same as get_observations() but uses Lat and Lon instead of Postalcode and Country"

        stations_observations_params = {}
        if start:
            stations_observations_params['start'] = start
        if end:
            stations_observations_params['end'] = end

        points_res = self.points(
            '{},{}'.format(round(lat, 4), round(lon, 4)))

        if 'properties' not in points_res or 'observationStations' not in points_res['properties']:
            raise Exception('Error: No Observation Stations found.')
        stations = self.make_get_request(
            uri=points_res['properties']['observationStations'],
            end_point=self.DEFAULT_END_POINT)['observationStations']

        for index, station in enumerate(stations):
            if num_of_stations > 0 and num_of_stations <= index:
                break
            station_id = station.split('/')[-1]
            response = self.stations_observations(
                station_id=station_id, **stations_observations_params)

            observations = response
            if type(response) == dict:
                observations = response['features']
            for observation in observations:
                yield observation.get('properties')

    def get_observations_by_postalcode_country(
            self, postalcode, country, start=None, end=None, num_of_stations=1):
        """Deprecated. Please use method get_observations."""
        return self.get_observations(postalcode, country, start, end, num_of_stations)

    def points(self, point, stations=False):
        """Metadata about a point.
        This is the primary endpoint for forecast information for a location.
        It contains linked data for the forecast, the hourly forecast,
        observation and other information. It also shows stations nearest to a point
        in order of distance.

        Response in this method should not be modified.
        In this way, we can keep track of changes made by NOAA through
        functional tests @todo(paulokuong) later on.

        Args:
            point (str): lat,long.
            stations (boolean): True for finding stations.
        Returns:
            json: json response from api.
        """

        if stations:
            return self.make_get_request(
                "/points/{point}/stations".format(point=point),
                end_point=self.DEFAULT_END_POINT)
        return self.make_get_request(
            "/points/{point}".format(point=point),
            end_point=self.DEFAULT_END_POINT)

    def points_forecast(self, lat, long, data_type=None):
        """Get observation data from a weather station.

        Response in this method should not be modified.
        In this way, we can keep track of changes made by NOAA through
        functional tests @todo(paulokuong) later on.

        Args:
            lat (float): latitude of the weather station coordinate.
            long (float): longitude of the weather station coordinate.
            hourly (boolean[optional]): True for getting hourly forecast.
        Returns:
            json: json response from api.
        """
        if type(data_type) is not list:
            data_type = [data_type]

        for dtype in data_type:
            assert dtype in ["hourly", "grid", None]

        points = self.make_get_request(
            "/points/{lat},{long}".format(
                lat=lat, long=long), end_point=self.DEFAULT_END_POINT)
        
        responses = []
        for dtype in data_type:
            uri = points['properties']['forecast']
            if dtype == "hourly":
                uri = points['properties']['forecastHourly']
            elif dtype == "grid":
                uri = points['properties']['forecastGridData']
            response = self.make_get_request(uri=uri, end_point=self.DEFAULT_END_POINT)
            responses.append(response)
        
        return responses

    def stations(self, **params):
        """Get list of US weather stations and their metadata.

        Response in this method should not be modified.
        In this way, we can keep track of changes made by NOAA through
        functional tests @todo(paulokuong) later on.

        Args:
            station_id (str[optional]): station id.
            state (str[optional]): 2 letters state code.
            limit (int[optional]): limit of results.
        Returns:
            json: json response from api.
        """
        if len(params) > 0:
            if 'station_id' in params:
                params['id'] = params['station_id']
                del params['station_id']
            return self.make_get_request(
                "/stations?{query_string}".format(
                    query_string=urlencode(params)),
                end_point=self.DEFAULT_END_POINT)
        return self.make_get_request(
            "/stations", end_point=self.DEFAULT_END_POINT)

    def stations_observations(self, station_id, **params):
        """Get observation data from specific station.

        Response in this method should not be modified.
        In this way, we can keep track of changes made by NOAA through
        functional tests @todo(paulokuong) later on.
        (*Note: There is a delay on NOAA's side for "unpopular" stations which
        causes start and end params not enable to query anything sometimes.)

        Args:
            station_id (str): station id.
            start (str[optional]): start date of observation
                (eg. '%Y-%m-%dT%H:%M:%SZ' | '%Y-%m-%d' | '%Y-%m-%d %H:%M:%S').
            end (str[optional]): end date of observation
                (eg. '%Y-%m-%dT%H:%M:%SZ' | '%Y-%m-%d' | '%Y-%m-%d %H:%M:%S').
            limit (int[optional]): limit of results.
            current (bool[optional]): True if needs current observations.
            recordId (str[optional]): recordId, Record Id (ISO8601DateTime)
        Returns:
            json: json response from api.
        """

        if not station_id:
            raise Exception("'station_id' is required.")
        if 'recordId' in params and 'current' in params:
            raise Exception("Cannot have both 'current' and 'recordId'")
        if 'start' in params:
            start = params['start']
            self.parse_param_timestamp(start)
            if len(start) < 19:
                start = '{}T00:00:00Z'.format(start[:10])
            elif len(params['start']) < 20:
                start = start.replace(' ', 'T')
                start = '{}Z'.format(start)
            params['start'] = start
        if 'end' in params:
            end = params['end']
            self.parse_param_timestamp(end)
            if len(end) < 19:
                end = '{}T23:59:59Z'.format(end[:10])
            elif len(params['end']) < 20:
                end = end.replace(' ', 'T')
                end = '{}Z'.format(end)
            params['end'] = end

        request_uri = "/stations/{stationId}/observations".format(
            stationId=station_id)

        if len(params) > 0:
            if 'recordId' in params:
                return self.make_get_request(
                    '{old_request_uri}/{recordId}'.format(
                        old_request_uri=request_uri,
                        recordId=params['recordId']),
                    end_point=self.DEFAULT_END_POINT)
            if 'current' in params:
                return self.make_get_request(
                    '{old_request_uri}/current'.format(
                        old_request_uri=request_uri),
                    end_point=self.DEFAULT_END_POINT)

            if len(params) > 1:
                request_uri = '{old_request_uri}?{query_string}'.format(
                    old_request_uri=request_uri,
                    query_string=urlencode(params))

            observations = self.make_get_request(
                request_uri, end_point=self.DEFAULT_END_POINT)
            if 'features' not in observations:
                raise Exception(observations)
            return observations['features']

        return self.make_get_request(
            "/stations/{stationId}/observations".format(stationId=station_id),
            end_point=self.DEFAULT_END_POINT)

    def products(self, id):
        """Get data of a product.

        Response in this method should not be modified.
        In this way, we can keep track of changes made by NOAA through
        functional tests @todo(paulokuong) later on.

        Args:
            id (str): product id.
        Returns:
            json: json response from api.
        """
        return self.make_get_request(
            "/products/{productId}".format(productId=id),
            end_point=self.DEFAULT_END_POINT)

    def products_types(self, **params):
        """Get a list of product types with an active product.

        Response in this method should not be modified.
        In this way, we can keep track of changes made by NOAA through
        functional tests @todo(paulokuong) later on.

        Args:
            type_id (str): an id of a valid product type
            locations (boolean[optional]): True to get a list of
                locations that have issues products for a type.
            location_id (str): location id.
        Returns:
            json: json response from api.
        """
        if 'type_id' in params and 'locations' not in params:
            return self.make_get_request(
                "/products/types/{type_id}".format(type_id=params['type_id']),
                end_point=self.DEFAULT_END_POINT)
        elif 'locations' in params:
            if 'type_id' not in params:
                raise Exception('Error: Missing type id (type_id=None)')
            if 'location_id' in params:
                return self.make_get_request(
                    ('/products/types/{type_id}/locations/'
                     '{location_id}').format(
                        type_id=params['type_id'],
                        location_id=params['location_id']),
                    end_point=self.DEFAULT_END_POINT)
            else:
                return self.make_get_request(
                    "/products/types/{type_id}/locations".format(
                        type_id=params['type_id']),
                    end_point=self.DEFAULT_END_POINT)
        return self.make_get_request(
            "/products/types",
            end_point=self.DEFAULT_END_POINT)

    def products_locations(self, **params):
        """A list of locations with active products.

        Response in this method should not be modified.
        In this way, we can keep track of changes made by NOAA through
        functional tests @todo(paulokuong) later on.

        Args:
            location_id (str): location id.
        Returns:
            json: json response from api.
        """
        if 'location_id' in params:
            return self.make_get_request(
                "/products/locations/{locationId}/types".format(
                    locationId=params['location_id']),
                end_point=self.DEFAULT_END_POINT)
        return self.make_get_request(
            "/products/locations",
            end_point=self.DEFAULT_END_POINT)

    def offices(self, office_id):
        """Metadata about a Weather Office.

        Response in this method should not be modified.
        In this way, we can keep track of changes made by NOAA through
        functional tests @todo(paulokuong) later on.

        Args:
            office_id (str): office id.
        Returns:
            json: json response from api.
        """
        return self.make_get_request("/offices/{office_id}".format(
            office_id=office_id), end_point=self.DEFAULT_END_POINT)

    def zones(self, type, zone_id, forecast=False):
        """Metadata for a zone and forecast data for zone.

        Response in this method should not be modified.
        In this way, we can keep track of changes made by NOAA through
        functional tests @todo(paulokuong) later on.

        Args:
            type (str): a valid zone type (list forthcoming).
            zone_id (str): a zone id (list forthcoming).
            forecast (bool): True to show forecast data of the zone.
        Returns:
            json: json response from api.
        """
        if forecast:
            return self.make_get_request(
                "/zones/{type}/{zone_id}/forecast".format(
                    type=type, zone_id=zone_id),
                end_point=self.DEFAULT_END_POINT)
        return self.make_get_request("/zones/{type}/{zone_id}".format(
            type=type, zone_id=zone_id), end_point=self.DEFAULT_END_POINT)

    def alerts(self, **params):
        """A list of alerts that can be filtered by parameters.
        If no parameters are provided, then all alerts are returned.
        The ATOM format returns items in CAP-ATOM.

        Response in this method should not be modified.
        In this way, we can keep track of changes made by NOAA through
        functional tests @todo(paulokuong) later on.

        Args:
            alert_id (str): alert id.
            active (int): Active alerts (1 or 0).
            start (str): Start time (ISO8601DateTime).
            end (str): End time (ISO8601DateTime).
            status (str): Event status (alert, update, cancel).
            type (str): Event type (list forthcoming).
            zone_type (str): Zone type (land or marine).
            point (str): Point (latitude,longitude).
            region (str): Region code (list forthcoming).
            state (str): State/marine code (list forthcoming).
            zone (str): Zone Id (forecast or county, list forthcoming).
            urgency (str): Urgency (expected, immediate).
            severity (str): Severity (minor, moderate, severe).
            certainty (str): Certainty (likely, observed).
            limit (int) Limit (an integer).
        Returns:
            json: json response from api.
        """
        if 'alert_id' in params:
            return self.make_get_request(
                "/alerts/{alert_id}".format(alert_id=params['alert_id']),
                end_point=self.DEFAULT_END_POINT)
        return self.make_get_request(
            "/alerts?{query_string}".format(query_string=urlencode(params)),
            end_point=self.DEFAULT_END_POINT)

    def active_alerts(self, count=False, **params):
        """Active alerts endpoints.

        Response in this method should not be modified.
        In this way, we can keep track of changes made by NOAA through
        functional tests @todo(paulokuong) later on.

        Args:
            count (bool): True to hit /alerts/active/count.
            zone_id (str): a valid zone, see list in counts endpoint.
            area (str): a valid area, see list in counts endpoint.
            region (str): a valid region, see list in counts endpoint
        Returns:
            json: json response from api.
        """

        if count:
            return self.make_get_request(
                "/alerts/count",
                end_point=self.DEFAULT_END_POINT)
        if 'zone_id' in params:
            return self.make_get_request(
                "/alerts/active/zone/{zoneId}".format(
                    zoneId=params['zone_id']),
                end_point=self.DEFAULT_END_POINT)
        if 'area' in params:
            return self.make_get_request(
                "/alerts/active/area/{area}".format(
                    area=params['area']),
                end_point=self.DEFAULT_END_POINT)
        if 'region' in params:
            return self.make_get_request(
                "/alerts/active/region/{region}".format(
                    region=params['region']),
                end_point=self.DEFAULT_END_POINT)
        return self.make_get_request(
            "/alerts/active",
            end_point=self.DEFAULT_END_POINT)
