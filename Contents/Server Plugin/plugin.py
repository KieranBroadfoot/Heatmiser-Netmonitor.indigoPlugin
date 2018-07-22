#! /usr/bin/env python
# -*- coding: utf-8 -*-
####################
# Copyright (c) 2016, Kieran J. Broadfoot. All rights reserved.
#

import sys
import os
import re
import httplib
import urllib
from time import strftime

class Plugin(indigo.PluginBase):

	def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs): 
		indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)
		self.netLocation = pluginPrefs.get("netmonitorLocation", "127.0.0.1")

	def __del__(self):
		indigo.PluginBase.__del__(self)

	def startup(self):
		self.logger.info("starting heatmiser-netmonitor plugin")
		self.generateDevices()

	def shutdown(self):
		self.logger.info("stopping heatmiser-netmonitor plugin")
		pass

	def validatePrefsConfigUi(self, valuesDict):
		self.netLocation = valuesDict["netmonitorLocation"]
		success, result = self.makeCallToNetmonitor("/quickview.htm", {})
		if success:
			return True
		else:
			errorDict = indigo.Dict()
			errorDict["netmonitorLocation"] = "Invalid location"
			return (False, valuesDict, errorDict)

	def runConcurrentThread(self):
		self.logger.info("starting heatmiser-netmonitor monitoring thread")
		try:
			while True:
				self.sleep(60)
				self.collectStats()
				
		except self.StopThread:
			pass
	
	def generateDevices(self):
		indigo.server.log("generating heatmiser devices")
		devices = self.getDevices()
		for stat in devices.keys():
			device = None
			for dev in indigo.devices.iter("self"):
				if dev.address == stat:
					device = indigo.devices[dev.name]
					
			if device == None:
				self.logger.info("creating heatmiser thermostat for %s" % devices[stat]['name'])
				device = indigo.device.create(protocol=indigo.kProtocol.Plugin,
					address=stat,
					name=devices[stat]['name'], 
					description=devices[stat]['desc'], 
					pluginId="uk.co.l1fe.indigoplugin.Heatmiser-Netmonitor",
					deviceTypeId=devices[stat]['type'],
					props={})
			self.updateStatState(devices[stat], device)
		
	def collectStats(self):
		devices = self.getDevices()
		for stat in devices.keys():
			device = None
			for dev in indigo.devices.iter("self"):
				if dev.address == stat:
					device = indigo.devices[dev.name]	
			if device != None:
				self.updateStatState(devices[stat], device)
				
	def updateStatState(self, device, indigoDevice):
		if device['type'] == "heatmiserThermostatWithHotWater":
			if device['waterOn'] == "1":
				indigoDevice.updateStateOnServer(key='hotWaterOn', value=True)
			else:
				indigoDevice.updateStateOnServer(key='hotWaterOn', value=False)
		if device['heatingOn'] == "1":
			indigoDevice.updateStateOnServer(key='heatingOn', value=True)
			indigoDevice.updateStateOnServer("hvacOperationMode", indigo.kHvacMode.Heat)
		else:
			indigoDevice.updateStateOnServer(key='heatingOn', value=False)
			indigoDevice.updateStateOnServer("hvacOperationMode", indigo.kHvacMode.Off)
		indigoDevice.updateStateOnServer("setpointHeat", device['setTemp'])
		indigoDevice.updateStateOnServer("temperatureInput1", device['currentTemp'])
		
	def getDevices(self):
		params = {'rdbkck': '1'}
		stats = {}
		success, result = self.makeCallToNetmonitor("/quickview.htm", params)
		if success:
			result = ''.join(l[:-1] for l in result.split('\n'))
			statnameString = re.match(".*name=\"statname\"\s+value=\"([\w|\/|\s|\#]*)\".*", result)
			valuesString = re.match(".*name=\"quickview\"\s+value=\"([\w|\d]*)\".*", result)
			if valuesString and statnameString:
				statNames = statnameString.group(1).split("#")
				values = valuesString.group(1)
				# statValue will contain 6 chars.  0-1 is current temp, 2-3 is set temp, 4 is heat status and 5 is water status
				# heat and water status is 0 = off, 1 = on, 2 = Not known, 3 = Not applicable
				count = 0
				while len(values)>0:
					statValues = values[:6]
					values = values[6:]
					if statValues[0:2] != "NC":
						statDesc = "Heatmiser Thermostat"
						statType = "heatmiserThermostat"
						if statValues[5] != "3":
							statDesc = "Heatmiser Thermostat (with Hot Water)"
							statType = "heatmiserThermostatWithHotWater"
						stats["hm"+str(count+1)] = { 'name':statNames[count],
												'currentTemp':statValues[0:2],
												'setTemp':statValues[2:4],
												'heatingOn':statValues[4],
												'waterOn':statValues[5],
												'type':statType,
												'desc':statDesc }
						count = count+1
		return stats

	def makeCallToNetmonitor(self, location, params):
		params = urllib.urlencode(params)
		headers = {"Content-type": "application/x-www-form-urlencoded","Accept": "text/plain"}
		try:
			conn = httplib.HTTPConnection(self.netLocation+":80")
			conn.request("POST", location, params, headers)
			response = conn.getresponse()
			data = response.read()
			conn.close()
			return True, data
		except Exception:
			self.logger.warn("failed to communicate with netmonitor")
			return False, ""

	def accessNetmonitor(self):
		self.browserOpen("http://"+self.netLocation)

	def setTime(self, action, dev):
		self.logger.info("updating heatmiser time")
		params = {'rdbkck': '1', 'timestr':strftime("%H:%M")}
		success, result = self.makeCallToNetmonitor("/networkSetup.htm", params)
		
	def setDate(self, action, dev):
		self.logger.info("updating heatmiser date")
		params = {'rdbkck': '1', 'datestr':strftime("%H:%M")}
		success, result = self.makeCallToNetmonitor("/networkSetup.htm", params)
		
	def heatWater(self, action, device):
		params = {'rdbkck': '1', 'curSelStat':device.name, 'hwBoost': action.props.get("numberOfHours")}
		success, result = self.makeCallToNetmonitor("/right.htm", params)
		if success:
			hoursValue = action.props.get("numberOfHours").lstrip('0')
			if hoursValue == "":
				self.logger.info("heatmiser hot water thermostat \"%s\" was set to off" % (device.name))
			else:
				self.logger.info("heatmiser hot water thermostat \"%s\" set to run for %s hours" % (device.name, hoursValue))

	def updateThermostatTemperature(self, thermostatName, setpoint):
		params = { 'rdbkck':'1', 'selSetTemp':str(int(setpoint)), 'curSelStat':thermostatName }
		success, data = self.makeCallToNetmonitor("/right.htm", params)
		if success:
			return True
		else:
			return False

	def actionControlThermostat(self, action, dev):
		if action.thermostatAction == indigo.kThermostatAction.SetHeatSetpoint:
			newSetpoint = action.actionValue
			if self.updateThermostatTemperature(dev.name, newSetpoint):
				dev.updateStateOnServer("setpointHeat", newSetpoint)
				self.logger.info("heatmiser thermostat \"%s\" set heat point to %s" % (dev.name, newSetpoint))
		elif action.thermostatAction == indigo.kThermostatAction.DecreaseHeatSetpoint:
			newSetpoint = dev.heatSetpoint - action.actionValue
			if self.updateThermostatTemperature(dev.name, newSetpoint):
				dev.updateStateOnServer("setpointHeat", newSetpoint)
				self.logger.info("heatmiser thermostat \"%s\" decreased heat point to %s" % (dev.name, newSetpoint))
		elif action.thermostatAction == indigo.kThermostatAction.IncreaseHeatSetpoint:
			newSetpoint = dev.heatSetpoint + action.actionValue
			if self.updateThermostatTemperature(dev.name, newSetpoint):
				dev.updateStateOnServer("setpointHeat", newSetpoint)
				self.logger.info("heatmiser thermostat \"%s\" increased heat point to %s" % (dev.name, newSetpoint))
		elif action.thermostatAction == indigo.kThermostatAction.SetHvacMode:
			if action.actionMode == 1:
				dev.updateStateOnServer("hvacOperationMode", indigo.kHvacMode.Heat)
				self.logger.info("heatmiser thermostat \"%s\" set to Heat" % (dev.name))
				newSetpoint = dev.states["temperatureInput1"] + 2
				if self.updateThermostatTemperature(dev.name, newSetpoint):
					dev.updateStateOnServer("setpointHeat", newSetpoint)
					self.logger.info("heatmiser thermostat \"%s\" set heat point to %s" % (dev.name, newSetpoint))
			elif action.actionMode == 0 or action.actionMode == 2:
				dev.updateStateOnServer("hvacOperationMode", indigo.kHvacMode.Off)
				self.logger.info("heatmiser thermostat \"%s\" set to Off" % (dev.name))
				if self.updateThermostatTemperature(dev.name, 10):
					dev.updateStateOnServer("setpointHeat", 10)
					self.logger.info("heatmiser thermostat \"%s\" set heat point to %s" % (dev.name, 10))
			else:
				self.logger.info("heatmiser thermostat \"%s\" set to current program mode" % (dev.name))
		elif action.thermostatAction in [indigo.kThermostatAction.RequestStatusAll, indigo.kThermostatAction.RequestMode,
			indigo.kThermostatAction.RequestEquipmentState, indigo.kThermostatAction.RequestTemperatures, indigo.kThermostatAction.RequestHumidities,
			indigo.kThermostatAction.RequestDeadbands, indigo.kThermostatAction.RequestSetpoints]:
			self.logger.warn("status automatically updated every 1 minute")
		elif action.thermostatAction in [indigo.kThermostatAction.DecreaseCoolSetpoint, indigo.kThermostatAction.IncreaseCoolSetpoint, indigo.kThermostatAction.SetCoolSetpoint]:
			self.logger.warn("heatmiser thermostats do not support cooling functions")
		else:
			self.logger.warn("heatmiser action \"%s\" not currently supported" % (action.thermostatAction))