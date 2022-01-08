This is small command line interface to control the AVM Fritz Heating controllers. You can set the temperature or you can enable the boost mode. Both for either a room or a single device.
No other Fritz Smarthome devices are implemented, as I do not own them

fritzcli: Command line tool control temperatures on Fritz Smarthome heating controller

usage:

python3 fritzcli.py device|roomname command

where:

device|room name is the name of your controller or your group/room (use apostroph it it contain blanks)

command is one of

boost on 'seconds': sets the boost mode, replace seconds with a numeric value in seconds for the duration of the boos mode 

boost off: terminates the boost mode

settemperature 'temperature': sets the temperature of the device in degree celsius (range 8 to 28 degrees)

settemperature off: sets the temperature to off (closes valve)

settemperature on: sets the temperature to max (opens valve)

example:

python3 fritzcli.py "Livingroom 1" settemperature 22

To run multiple commands you can list them, but there need always 3 arguments

example:

python3 fritzcli.py "Livingroom 1" settemperature 22 "Bathroom 1" settemperature 22

you need to configure a config file fritzcli.cfgas well, defining the following parameter:
user = username

password = password

host = http://fritz.box"

