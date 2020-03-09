# IsardVDI - Mosquitto - Power management IoT

This is an optional (but cool) extra that will bring up a mosquitto container plugged to your IsardVDI grafana container and app

## Features
- It will allow power consumption monitoring, for example for hypervisors.
- It will allow to power on/off hypervisors based on virtual desktops demand.

## Requirements

- Grafana extra running
- ESP8266 based plug devices with custom firmware like Espurna (https://github.com/xoseperez/espurna)
- 
## Installation

```
./build.sh <image version>
docker-compose up -d
```

## Plugs

We have tested this feature with Espurna (https://github.com/xoseperez/espurna) and Teckin and SONOFF IoT Smart Plugs.

You should configure the mqtt plug with:
- HOSTNAME: The same as the hypervisor it will be monitoring that you set up in Hypervisors menu
- MQTT Broquer: Accessible IP/DNS of this container (usually the same as IsardVDI)
- MQTT Client ID: Could be anything or nothing as Espurna will auto generate one if missing.
- MQTT Root Topic: /isard/hypers/{hostname}

You should then see the power consumption in your grafana hypervisors dashboard

## More info

https://isardvdi.readthedocs.io/en/latest/
