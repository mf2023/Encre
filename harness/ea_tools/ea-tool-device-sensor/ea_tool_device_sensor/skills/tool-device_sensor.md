---
name: tool-device_sensor
description: "WHAT: Returns live readings from device sensors such as accelerometer, gyroscope, magnetometer, and ambient light when the hardware exposes them. WHEN: Use on laptops, tablets, or phones to detect orientation, motion, or ambient lighting for adaptive behaviour. WHEN NOT: Not applicable on most desktop servers or VMs that lack sensor hardware -- the call returns 'No sensor data available'. TIPS: Treat readings as instantaneous snapshots; sample repeatedly if you need trends or gesture detection. PITFALLS: Availability and units vary widely by platform and driver; some sensors may report zeros or stale values when the OS has suspended them."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# device_sensor

WHAT: Returns live readings from device sensors such as accelerometer, gyroscope, magnetometer, and ambient light when the hardware exposes them. WHEN: Use on laptops, tablets, or phones to detect orientation, motion, or ambient lighting for adaptive behaviour. WHEN NOT: Not applicable on most desktop servers or VMs that lack sensor hardware -- the call returns 'No sensor data available'. TIPS: Treat readings as instantaneous snapshots; sample repeatedly if you need trends or gesture detection. PITFALLS: Availability and units vary widely by platform and driver; some sensors may report zeros or stale values when the OS has suspended them.
