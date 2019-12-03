# -*- coding: utf-8 -*-

import logging
import requests, json

from kalliope.core.NeuronModule import (NeuronModule,
                                        MissingParameterException,
                                        InvalidParameterException)

logging.basicConfig()
logger = logging.getLogger("kalliope")

_BASE_URL = "https://api.netatmo.com/"
_AUTH_REQ = _BASE_URL + "oauth2/token"
_SET_THERM_MODE = _BASE_URL + "/api/setthermmode"
_HOME_STATUS = _BASE_URL + "api/homestatus"
_HOME_DATA = _BASE_URL + "api/homesdata"
_SET_ROOM_THERMPOINT = _BASE_URL + "api/setroomthermpoint"
_SWITCH_HOME_SCHEDULE = _BASE_URL + "api/switchhomeschedule"

_WEATHER_GET_STATION_DATA = _BASE_URL + "/api/getstationsdata"

THERMMODE = ("schedule", "away", "hg")

ACTIONS_UNIVERSE = {
    "GET_STATUS": "ENERGY",
    "SET_TEMP": "ENERGY",
    "CANCEL_SET_TEMP": "ENERGY",
    "CHANGE_MODE": "ENERGY",
    "SWITCH_SCHEDULE": "ENERGY",
    "WEATHER_DATA": "WEATHER"
}

WEATHER_DATA_TYPE = [
    "Temperature",
    "CO2",
    "Humidity",
    "Noise",
    "Pressure"
]

class Netatmo(NeuronModule):

    """
    Class used to interact with netatmo system
    """
    def __init__(self, **kwargs):

        super(Netatmo, self).__init__(**kwargs)

        # parameters
        self.username = kwargs.get('username', None)
        self.password = kwargs.get('password', None)
        self.clientId = kwargs.get('clientId', None)
        self.clientSecret = kwargs.get('clientSecret', None)
        self.action = kwargs.get('action', None)
        self.homeId = kwargs.get('homeId', None)
        self.roomId = kwargs.get('roomId', None)
        self.roomName = kwargs.get('roomName', None)
        self.thermMode = kwargs.get('thermoMode', None)
        self.temp = kwargs.get('temperature', None)
        self.scheduleId = kwargs.get('scheduleId', None)
        self.weather_deviceId = kwargs.get('deviceId', None)

        logger.debug("Netatmo launch %s", self.username)

        # check parameters
        if self._is_parameters_ok():

            scope="read_thermostat write_thermostat read_station" 
            payload = {
                "grant_type" : "password",
                "client_id" : self.clientId,
                "client_secret" : self.clientSecret,
                "username" : self.username,
                "password" : self.password,
                "scope" : scope
            }
            headers = { 'content-type': 'application/x-www-form-urlencoded; charset=UTF-8'}

            logger.debug(payload)
            response = requests.post(_AUTH_REQ, headers=headers, data=payload)

            content = response.json()
            self._accessToken = content['access_token']
            self.refreshToken = content['refresh_token']

            logger.debug(self._accessToken)

            if self.action == "GET_STATUS":
                self.homeStatus()
            elif self.action == "SET_TEMP":
                self.changeRoomTemp()
            elif self.action == "CANCEL_SET_TEMP":
                self.cancelBoostMode()
            elif self.action == "CHANGE_MODE":
                self.changeMode()
            elif self.action == "SWITCH_SCHEDULE":
                self.switchSchedule()
            elif self.action == "WEATHER_DATA":
                self.getWeatherData()

    def changeMode(self):
        #thermMode schedule / away / hg
        if self.thermMode not in THERMMODE:
            raise InvalidParameterException("Invalid Therm mode")

        headers = self.getAuthorizedHeader()
        params = {
            "home_id": self.homeId,
            "mode" : self.thermMode
        }
        response = requests.post(_SET_THERM_MODE, headers=headers, params=params)

    def homeData(self):
        headers = self.getAuthorizedHeader()

        response = requests.get(_HOME_DATA, headers=headers)

        content = response.json()
        return content["body"]["homes"][0]

    def homeStatus(self):
        headers = self.getAuthorizedHeader()

        params = {
            "home_id": self.homeId
        }

        homeData = self.homeData()
        
        response = requests.get(_HOME_STATUS, headers=headers, params=params)

        result = dict()
        result["rooms"] = []

        content = response.json()
        rooms = content["body"]["home"]["rooms"]
        for room in rooms:
            roomInfo = dict()
            roomInfo["id"] = room["id"]
            roomInfo["name"] = self._find_room_name_by_id(homeData, room["id"])
            roomInfo["reachable"] = room["reachable"]
            roomInfo["currentTemp"] = room["therm_measured_temperature"]
            roomInfo["mode"] = room["therm_setpoint_mode"]
            roomInfo["wantedTemp"] = room["therm_setpoint_temperature"]
            result["rooms"].append(roomInfo)

        self.say(result)

    def changeRoomTemp(self):
        logger.debug("changeRoomTemp to temp %s", self.temp)

        if self.roomName is not None and self.roomId is None:
            homeData = self.homeData()
            self.roomId = self._find_room_id_by_Name(homeData, self.roomName)
            if self.roomId is None: 
                raise InvalidParameterException("room {} not found".format(self.roomName))
            logger.debug("id of the room %s is %s", self.roomName, self.roomId)

        params = {
            "home_id": self.homeId,
            "room_id": self.roomId,
            "mode": "manual",
            "temp": int(self.temp)
        }
        headers = self.getAuthorizedHeader()
        response = requests.post(_SET_ROOM_THERMPOINT, headers=headers, params=params)

        logger.debug(response.json())

    def cancelBoostMode(self):
        params = {
            "home_id": self.homeId,
            "room_id": self.roomId,
            "mode": "home"
        }
        headers = self.getAuthorizedHeader()
        response = requests.post(_SET_ROOM_THERMPOINT, headers=headers, params=params)

        result = dict()
        result["ok"] = response.json()["status"]
        self.say(result)
        
    def switchSchedule(self):
        params = {
            "home_id": self.homeId,
            "schedule_id": self.scheduleId,
        }
        headers = self.getAuthorizedHeader()
        response = requests.post(_SWITCH_HOME_SCHEDULE, headers=headers, params=params)

    def getWeatherData(self):
        headers = self.getAuthorizedHeader()
        params = {
            "device_id": self.weather_deviceId
        }

        response = requests.get(_WEATHER_GET_STATION_DATA, headers=headers, params=params)

        content = response.json()
        weather_data = content["body"]["devices"][0]

        result = self._get_weather_data(weather_data)

        #Modules info
        for module in weather_data["modules"]:
           module_name = module["module_name"]
           result[module_name] = self._get_weather_data(module)

        self.say(result)

    def getAuthorizedHeader(self): 
        return {
            "Authorization" :  "Bearer " + self._accessToken
        }

    def _get_weather_data(self, data):
        result = dict()
        dashboard_data = data["dashboard_data"]

        for key, value in dashboard_data.items():
            result[key] = value 

        if 'battery_percent' in data.keys():
            result["battery_percent"] = data["battery_percent"]

        return result

    def _find_room_name_by_id(self, homeData, roomId):
        room = next((room for room in homeData["rooms"] if room["id"].lower() == roomId.lower()), None)
        return None if room is None else room["name"]
    
    def _find_room_id_by_Name(self, homeData, roomName):
        room = next((room for room in homeData["rooms"] if room["name"].lower() == roomName.lower()), None)
        return None if room is None else room["id"]

    def _find_schedule_id_by_Name(self, homeData, scheduleName):
        schedule = next((schedule for schedule in homeData["schedules"] if schedule["name"].lower() == scheduleName.lower()), None)
        return None if schedule is None else schedule["id"]

    def _is_parameters_ok(self):
        """
        Check if received parameters are ok to perform operations in the neuron.
        :return: True if parameters are ok, raise an exception otherwise.

        .. raises:: MissingParameterException, InvalidParameterException
        """
        if self.username is None:
            raise MissingParameterException("Netatmo needs a username")
        if self.password is None:
            raise MissingParameterException("Netatmo needs a password")
        if self.clientId is None:
            raise MissingParameterException("Netatmo needs a clientId")
        if self.clientSecret is None:
            raise MissingParameterException("Netatmo needs a clientSecret")
        if self.action is None:
            raise MissingParameterException("Netatmo needs an action")
        if self.action not in ACTIONS_UNIVERSE:
            raise InvalidParameterException("Invalid action")
        if ACTIONS_UNIVERSE[self.action] == "ENERGY":
            raise MissingParameterException("Netatmo needs a homeId")    
        return True

