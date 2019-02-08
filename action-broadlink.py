#!/usr/bin/env python2
# -*- coding: utf-8 -*-
from snipsTools import SnipsConfigParser
from hermes_python.hermes import Hermes
from hermes_python.ontology import *
import os
import broadlink
import random
from pathlib2 import Path
import unicodedata
import time

CONFIG_INI = "config.ini"

MQTT_IP_ADDR = "localhost"
MQTT_PORT = 1883
MQTT_ADDR = "{}:{}".format(MQTT_IP_ADDR, str(MQTT_PORT))

ACK = ["Trait bien", "OK", "daccord", "sait fait", "Pas de problaime", "entendu"]

allRooms = {}
allAppliances = {}

def findAppliances(path, room):
    global allAppliances
    global allRooms
    appliances = []

    for appliance in os.listdir(path):
        if os.path.isdir(path + "/" + appliance):
            appliances.append(appliance)

            if appliance in allAppliances:
                allAppliances[appliance]["count"] += 1
                allAppliances[appliance]["rooms"].append(room)
            else:
                allAppliances[appliance] = {"count": 1, "rooms": [room]}

        elif os.path.isfile(path + "/" + appliance):
            if appliance == "ip.txt":
                allRooms[room]["ip"] = Path(path + "/" + appliance).read_text().encode("utf-8")
            elif appliance == "mac.txt":
                allRooms[room]["mac"] = Path(path + "/" + appliance).read_text().encode("utf-8")

    return appliances

def findRooms(dir):
    global allRooms

    for room in os.listdir(dir):
        if os.path.isdir(dir + "/" + room):
            if room not in allRooms:
                allRooms[room] = {"appliances":[], "ip": None, "mac": None}

            appliances = findAppliances(dir + "/" + room, room)
            allRooms[room]["appliances"] = appliances

findRooms("./remotes")

print allRooms

print allAppliances

def remove_accents(input_str):
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    only_ascii = nfkd_form.encode('ASCII', 'ignore')
    return only_ascii

class Broadlink(object):
    """Class used to wrap action code with mqtt connection

        Please change the name refering to your application
    """
    def __init__(self):
        # get the configuration if needed
        try:
            self.config = SnipsConfigParser.read_configuration_file(CONFIG_INI)
        except :
            self.config = None


        # start listening to MQTT
        self.start_blocking()


    def extractHouseRooms(self, intent_message):
        house_rooms = []
        if intent_message.slots.house_room:
            for room in intent_message.slots.house_room.all():
                cleanEntity = remove_accents(room.value).encode("utf-8")
                print cleanEntity
                house_rooms.append(cleanEntity)

        return house_rooms
    
    def extractAppliances(self, intent_message):
        appliances = []
        if intent_message.slots.appliance:
            for appliance in intent_message.slots.appliance.all():
                cleanEntity = remove_accents(appliance.value).encode("utf-8")
                print cleanEntity
                appliances.append(cleanEntity)

        return appliances


    def sendIrCode(self, hermes, intent_message, code):
        house_rooms = self.extractHouseRooms(intent_message)
        appliances = self.extractAppliances(intent_message)

        global allAppliances
        global allRooms

        if len(house_rooms) == 0:
            house_rooms.append(None)

        for appliance in appliances:
            for room in house_rooms:

                if appliance not in allAppliances:
                    hermes.publish_start_session_notification(intent_message.site_id, "Cet appareil nexiste pas", "")
                    return False

                if room == None and allAppliances[appliance]["count"] == 1:
                    room = allAppliances[appliance]["rooms"][0]

                if room == None:
                    hermes.publish_start_session_notification(intent_message.site_id, "Veuillez preciser la piece", "")
                    return False

                print "[Room]: " + room
                print "[Appliance]: " + appliance

                cmd = "./remotes/" + room + "/" + appliance + "/" + code

                if not os.path.isfile(cmd):
                    hermes.publish_start_session_notification(intent_message.site_id, "Cet appareil nexiste pas", "")
                    return False

                contents = Path(cmd).read_text()
                data = bytearray.fromhex(''.join(contents))

                dev = broadlink.gendevice(0x2737, (allRooms[room]["ip"], 80), allRooms[room]["mac"])
                dev.auth()
                dev.send_data(data)

        return True

    def irGenericDeviceOnOffCallback(self, hermes, intent_message):
        hermes.publish_end_session(intent_message.session_id, "")
        print '[Received] intent: {}'.format(intent_message.intent.intent_name)
        success = self.sendIrCode(hermes, intent_message, "power")

        if success:
            hermes.publish_start_session_notification(intent_message.site_id, ACK[random.randint(0, len(ACK) - 1)], "")

    def master_intent_callback(self,hermes, intent_message):
        intent_name = intent_message.intent.intent_name
        if ':' in intent_name:
            intent_name = intent_name.split(":")[1]
        if intent_name == 'irGenericDeviceOn':
            self.irGenericDeviceOnOffCallback(hermes, intent_message)
        if intent_name == 'irGenericDeviceOff':
            self.irGenericDeviceOnOffCallback(hermes, intent_message)

    # --> Register callback function and start MQTT
    def start_blocking(self):
        with Hermes(MQTT_ADDR) as h:
            h.subscribe_intents(self.master_intent_callback).start()

if __name__ == "__main__":
    Broadlink()