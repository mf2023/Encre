---
name: tool-device_location
description: "WHAT: Returns the device's geographic location via the OS-native location service -- timezone, UTC offset, and GPS coordinates (latitude/longitude) when available. WHEN: Use for locale-aware formatting, scheduling actions in the user's local time, or tagging events with an approximate location. WHEN NOT: Not for precise tracking or navigation -- accuracy depends on the OS location service (Wi-Fi/IP-based on laptops, GPS on phones). Do not use as a geofencing security control. TIPS: Timezone and UTC offset are almost always available even when GPS is denied; rely on those when coordinates are absent. PITFALLS: Returns 'Location information unavailable' when the user has disabled location services or denied the app permission; coordinates may be coarse (kilometre-level) on Wi-Fi-only devices."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# device_location

WHAT: Returns the device's geographic location via the OS-native location service -- timezone, UTC offset, and GPS coordinates (latitude/longitude) when available. WHEN: Use for locale-aware formatting, scheduling actions in the user's local time, or tagging events with an approximate location. WHEN NOT: Not for precise tracking or navigation -- accuracy depends on the OS location service (Wi-Fi/IP-based on laptops, GPS on phones). Do not use as a geofencing security control. TIPS: Timezone and UTC offset are almost always available even when GPS is denied; rely on those when coordinates are absent. PITFALLS: Returns 'Location information unavailable' when the user has disabled location services or denied the app permission; coordinates may be coarse (kilometre-level) on Wi-Fi-only devices.
