"""
cli interface for DECT heating controllers of AVM
You need to configure a smarthome user in your Fritz Box

This is not PEP formatted by purpose
"""

import sys
import os
import re
import logging

from typing         import Dict,List,Optional,Union
from xml.etree      import ElementTree as ET
from requests       import Session
from datetime       import datetime
from datetime       import timedelta

try:
    import hashlib
except Exception as ImportExeception:
    print (f"Can't import hashlib, please install it: Error: {str(ImportExeception)}")
    exit(0)

def ToInt(vValue:Union[str,float]) -> int:
    """
    converts a (unicode) string into an integer
    (0) in case of an error

    :rtype: int
    :param string|float vValue: The string representation of an integer number
    :return: The integer value
    """
    try:
        return int(vValue)
    except Exception:
        print (f"Wrong parameter, can't be converted to a number: {vValue}")
        return 0


class cXMLToDic(dict):
    """
    Converts a Elementree xml node into a dictionary
    """

    def __init__(self, oParentElement: ET.Element):
        super().__init__()
        self.XML_Attributes:Element = oParentElement
        self.addAttributes(self.XML_Attributes,self)
        oChild:Element
        for oChild in list(oParentElement):
            oChild.text = oChild.text if (oChild.text is not None) else ' '
            if len(oChild) == 0:
                self.update(self._addToDict(uKey= oChild.tag, oValue = oChild.text.strip(), dDict = self))
                self.addAttributes(oChild,self)
            else:
                dInnerChild = cXMLToDic(oParentElement=oChild)
                self.update(self._addToDict(uKey=dInnerChild.XML_Attributes.tag, oValue=dInnerChild, dDict=self))

    def getDict(self)->Dict:
        """
        Return the attributes as a dict
        """
        return {self.XML_Attributes.tag: self}

    # noinspection PyMethodMayBeStatic
    def addAttributes(self,oNode: ET.Element,dDict:Dict):
        """
        Adds the xml attributes into the Dict tree
        :param oNode: The xml node to parse the attributes
        :param dDict: The target dict to store the attributes
        """
        for uAttribute in oNode.attrib:
            uValue = oNode.get(uAttribute, default='')
            if uValue:
                if not 'attributes' in dDict:
                    dDict['attributes'] = {}
                dDict['attributes'][uAttribute]=uValue
                for iIndex in range(1000):
                    sTag = uAttribute+'[%s]' % iIndex
                    if not sTag in dDict['attributes']:
                        dDict['attributes'][sTag] = uValue
                        if iIndex>0:
                            del dDict['attributes'][uAttribute]
                        break

    class _addToDict(dict):
        def __init__(self, uKey: str, oValue, dDict: Dict):
            super().__init__()
            if not uKey in dDict:
                self.update({uKey: oValue})
            else:
                identical = dDict[uKey] if type(dDict[uKey]) == list else [dDict[uKey]]
                self.update({uKey: identical + [oValue]})

class FritzBox:
    """
    The main class. You could derivate the class, if for eg you won't not use the command line or the config file
    """
    def __init__(self):

        self.sFNConfig: str     = os.path.dirname(sys.argv[0])+os.sep+"fritzcli.cfg"
        self.dConfig: Dict      = {}
        self.dDevicesRaw: Dict  = {}
        self.dDevices: Dict     = {}
        self.dRooms: Dict       = {}
        self.aArgs: List[List]  = []
        self.sSid:str           = ""
        self.oSession:Session   = Session()
        self.oLogger:Optional[Rootlogger] = None
        self.CreateLogger()

    def CreateLogger(self):
        """
        Derivate it, if you want to use your own logger
        """
        self.oLogger = logging.getLogger()
        # self.oLogger.addHandler(logging.StreamHandler(sys.stdout))

    def Info(self)->None:
        """
        Displays a message how to use the cli
        :return:
        """
        sMessage=f"fritzcli: Command line tool control temperatures on Fritz Smarthome heating controller\n" \
                 "\n" \
                 "usage:\n" \
                 "\n" \
                 "python3 fritzcli.py device|roomname command\n" \
                 "\n" \
                 "where\n:" \
                 "device|room name is the name of your controller or your group/room (use apostroph it it contain blanks\n" \
                 "command is one of\n" \
                 "boost on 'seconds': sets the boost mode, replace seconds with a numeric value in seconds for the duration of the boos mode \n" \
                 "boost off: terminates the boost mode\n" \
                 "settemperature 'temperature': sets the temperature of the device in degree celsius (range 8 to 28 degrees)\n" \
                 "settemperature off: sets the temperature to off (closes valve)\n" \
                 "settemperature on: sets the temperature to max (opens valve)\n" \
                 "\n" \
                 "example:\n" \
                 "python3 fritzcli.py \"Livingroom 1\" settemperature 22" \
                 "\n" \
                 "To run multiple commands you can list them, but there need always 3 arguments\n" \
                 "\n" \
                 "example:\n" \
                 "python3 fritzcli.py \"Livingroom 1\" settemperature 22 \"Bathroom 1\" settemperature 22\m" \
                 "\n" \
                 "you need to configure a config file '{self.sFNConfig}'as well, defining the following parameter:\n"\
                 "user = username \n"\
                 "password = password\n"\
                 "host = http://fritz.box"

        print (sMessage)

    def Run(self) -> True:
        """
        The main entry point
        """
        if self.ReadConfig():
            if self.ReadCommandLine():
                if self.Login():
                    if self.GetAllFritzDevices():
                        return self.ExecuteCommand()
        return True

    def ReadConfig(self) -> bool:
        """
        Reads the config file
        """
        try:
            uToken:str
            uValue:str
            self.dConfig['host'] = "http://fritz.box"
            oFile = open (self.sFNConfig,"r")
            for uLine in oFile.readlines():
                uToken,uValue = uLine.split("=")
                if not uToken.strip().startswith("#"):
                    self.dConfig[uToken.strip().lower()]=uValue.strip()
            oFile.close()
            assert self.dConfig.get("password") is not None , f"No password given in config file {self.sFNConfig}"
            assert self.dConfig.get("user") is not None, f"No user given in config file {self.sFNConfig}"
            return True
        except Exception as e:
            self.oLogger.error(f"Can't read config file: {self.sFNConfig} Error: {str(e)}")
            self.Info()
            return False

    def ReadCommandLine(self) -> bool:
        """
        Reads the command line. 3 Parameter defines one set
        syntax is "room command parameter"
        """
        aArgs:List[str]
        aCmdArgs:List[str]
        i:int
        u:int
        try:
            aCmdArgs = sys.argv[1:]
            for i in range(int((len(aCmdArgs)+1)/3)):
                aArgs=[]
                aArgs.append(aCmdArgs[i*3])
                aArgs.append(aCmdArgs[i*3+1])
                aArgs.append(aCmdArgs[i*3+2])
                self.aArgs.append(aArgs)
            return True
        except Exception as e:
            self.oLogger.error(f"Can't read command line: Error: {str(e)}")
            return False

    def Login(self) -> bool:
        """
        Logins to the FritzBox
        """
        oResponse:Response
        sChallenge:str
        sSid:str
        oXml:ET.Element
        iBlocktime:int
        sEmptySID:str = "0000000000000000"
        try:
            sUrlLogin:str = self.dConfig["host"] + '/login_sid.lua'
            oResponse = self.oSession.get(sUrlLogin, timeout=10)
            oXml = ET.fromstring(oResponse.text)
            if oXml.find('SID').text == sEmptySID:
                sChallenge = oXml.find('Challenge').text
                oResponse = self.oSession.get(sUrlLogin, params={"username": self.dConfig["user"],"response": self.CalculateResponse(sChallenge=sChallenge, sPassword=self.dConfig["password"]),}, timeout=10)
                oXml = ET.fromstring(oResponse.text)
                self.sSid = oXml.find('SID').text
                if self.sSid == sEmptySID:
                    iBlocktime = int(oXml.find('BlockTime').text)
                    raise Exception(f"Wrong credentials or please wait {iBlocktime} seconds")
                return True
        except Exception as e:
            self.oLogger.error(f"Login failed: Error: {str(e)}")
            return False

    def ExecuteCommand(self) ->bool:
        """
        Executes a list of commands
        """
        sDeviceName:str
        sCommand:str
        dDevice:dict
        sParameter1:str
        sAin:str
        aArgs:List
        try:
            for aArgs in self.aArgs:

                sDeviceName=aArgs[0]
                sCommand=aArgs[1]
                try:
                    sParameter1=aArgs[2]
                except:
                    sParameter1=""

                dDevice=self.dRooms.get(sDeviceName,self.dDevices.get(sDeviceName,{}))
                if len(dDevice)==0:
                    raise Exception(f"Room or device {sDeviceName} not found")

                sAin=dDevice["attributes"]["identifier"]
                if sCommand=="boost":
                    if not self.ExecuteCommand_Boost(sAin=sAin,sTime=sParameter1):
                        return False
                elif sCommand=="settemperature":
                    if not self.ExecuteCommand_SetTemperature(sAin=sAin,sTemperature=sParameter1):
                        return False
                else:
                    self.Info()
                    return False
            return True
        except Exception as e:
            self.oLogger.error(f"Executecommand failed: Error: {str(e)}")
            return False

    def ExecuteCommand_Boost(self, *, sAin:str, sTime:str) ->bool:
        """
        Sets the boost command for a heating controller/room/group
        :param sAin: The identifier of a group/room/device
        :param sTime: The time in seconds of "off"
        """
        if sTime=="off":
            sTime="0"
        iTime:int=ToInt(sTime)
        sEndTimeStamp=str(self.CalculateBoostEndTime(iAddSeconds=iTime))
        if self.SendCommand(sCmd="sethkrboost",sAin=sAin,dParam={"endtimestamp":sEndTimeStamp}) != "***error***":
            return True
        return False

    def ExecuteCommand_SetTemperature(self, *, sAin:str, sTemperature:str) ->bool:
        """
        Sets the temperature of of a device
        :param sAin: The identifier of a group/room/device
        :param sTemperature: The temperature in degree celsius, or "on" or "off"
        """
        iTemperature:int
        if sTemperature.isdigit():
            iTemperature:int=self.CalculateFritzTemperature(ToInt(sTemperature))
        elif sTemperature == "off":
            iTemperature = 253
        elif sTemperature == "on":
            iTemperature = 254
        else:
            raise Exception(f"Wrong temperature {sTemperature}")

        if self.SendCommand(sCmd="sethkrtsoll",sAin=sAin,dParam={"param":str(iTemperature)}) != "***error***":
            return True
        return False


    def CalculateFritzTemperature(self,iTemperature:int)->int:
        """
        Converts a standard temperature into a AVM temperature
        :param iTemperature: The temperature in degree celsius
        """
        return max(min(iTemperature*2,56),16)

    def CalculateBoostEndTime(self, iAddSeconds:int) -> int:
        """Adds a time in seconds to the current time in seconds (started 1.1.1970
           This is the boost end time
           0 Ends Boosting """

        uDstVarName:str
        iSecondsFromStart:int
        iNewTime:int
        oDateFromStart:datetime

        try:
            if iAddSeconds==0:
                return 0
            oDateFromStart  = datetime.fromtimestamp(0) + timedelta(seconds=datetime.now().timestamp())
            iSecondsFromStart = int(oDateFromStart.timestamp())
            iNewTime          = iSecondsFromStart + iAddSeconds
            return iNewTime
        except Exception as e:
            self.oLogger.error(f"CalculateBoostEndTime failed: Error: {str(e)}")
        return 0

    def CalculateResponse(self, *, sChallenge:str, sPassword:str)->str:
        """
        Calculate the hash or the login procedure of the FritzBox
        :param sChallenge: The challenge returned on the first login step
        :param sPassword: The password
        """
        bToHash:bytes = f"{sChallenge}-{sPassword}".encode("UTF-16LE")
        sHashed:str = hashlib.md5(bToHash).hexdigest()
        return f"{sChallenge}-{sHashed}"

    def GetAllFritzDevices(self) -> bool:
        """
        Returns a list of Actor objects for querying SmartHome devices.
        This is currently the only working method for getting temperature data.
        """
        dDevice:Dict
        try:
            sResult:str = self.SendCommand("getdevicelistinfos")
            self.dDevicesRaw = cXMLToDic(ET.fromstring(sResult)).getDict()
            for dDevice in self.dDevicesRaw["devicelist"]["device"]:
                self.dDevices[dDevice["name"]] = dDevice
            for dDevice in self.dDevicesRaw["devicelist"]["group"]:
                self.dRooms[dDevice["name"]] = dDevice
            return True
        except Exception as e:
            self.oLogger.error(f"Can't get Fritzbox Devices: {str(e)}")
        return False


    def SendCommand(self, sCmd:str, sAin:Optional[str]=None, dParam:Optional[Dict]=None) -> str:
        """
        Call a switch method.
        Should only be used by internal library functions.
        """
        oResponse:Response
        dParams:Dict
        sUrl:str = f"{self.dConfig['host']}/webservices/homeautoswitch.lua"
        sResult:str

        try:
            dParams = {'switchcmd': sCmd,
                       'sid': self.sSid
                       }
            if dParam is not None:
                dParams.update(dParam)

            if sAin:
                dParams['ain'] = self.NormalizeAin(sAin)

            oResponse = self.oSession.get(sUrl, params=dParams, timeout=10)
            oResponse.raise_for_status()
            sResult = oResponse.text.strip().encode('utf-8')
            self.oLogger.info(f"fritzcli: Send command {sCmd} returned {sResult}")
            if sCmd!="getdevicelistinfos":
                print(f"fritzcli: Send command {sCmd} returned {sResult}")
            return sResult
        except Exception as e:
            self.oLogger.error(f"Sending command failed: Error: {str(e)}")
            return '***error***'


    @classmethod
    def NormalizeAin(cls, sAin:str)->str:
        """
        Removes blanks from an AIN.
        """
        return re.sub('\s', '', sAin)


if __name__ == '__main__':
    if FritzBox().Run():
        print ("Success")
    else:
        print ("Error")