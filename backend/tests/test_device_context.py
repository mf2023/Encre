#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
#
# This file is part of Encre.
# The Encre project belongs to the Dunimd Team.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# DISCLAIMER: Users must comply with applicable AI regulations.
# Non-compliance may result in service termination or legal liability.

"""Tests for device context providers and tools."""

import json
import sys
import os
import pytest


# 鈹€鈹€ Provider tests 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


def test_platform_info_provider():
    """Validate that PlatformInfoProvider returns structured OS metadata.

    The test collects platform data and asserts the OS system field is one
    of the three known values (Windows, Linux, Darwin), that the node
    hostname is non-empty, that the architecture is a recognized value,
    and that the Python version string starts with '3' because these
    fields are required for the agent to tailor behavior to the host.
    """
    from encre.device_context.providers.platform_ import PlatformInfoProvider
    p = PlatformInfoProvider()
    data = p.collect()
    assert data is not None, "PlatformInfoProvider should return data"
    os_info = data.get("os", {})
    assert os_info.get("system") in ("Windows", "Linux", "Darwin"), \
        f"Expected a real OS, got {os_info.get('system')}"
    assert os_info.get("node"), "Hostname should not be empty"
    assert data.get("arch") in ("AMD64", "x86_64", "arm64", "aarch64"), f"Unexpected arch: {data.get('arch')}"
    assert data.get("python", {}).get("version", "").startswith("3"), f"Python version: {data.get('python', {})}"
    print(f"[PASS] platform_info: {json.dumps(data, ensure_ascii=False, indent=2)}")


def test_hardware_info_provider():
    """Validate that HardwareInfoProvider returns structured CPU, memory, and disk metadata.

    The test asserts logical CPU cores > 0, total RAM > 0 GB, at least one
    disk partition exists, total disk capacity > 0 GB, and the current
    working directory is recorded because these hardware signals inform
    the agent's resource-aware decision making.
    """
    from encre.device_context.providers.hardware import HardwareInfoProvider
    p = HardwareInfoProvider()
    data = p.collect()
    assert data is not None, "HardwareInfoProvider should return data"
    cpu = data.get("cpu", {})
    assert cpu.get("logical_cores", 0) > 0, f"CPU cores should be > 0: {cpu}"
    mem = data.get("memory", {})
    assert mem.get("total_gb", 0) > 0, f"RAM should be > 0 GB: {mem}"
    disk = data.get("disk", {})
    partitions = disk.get("partitions", [])
    assert len(partitions) > 0, f"Should have at least one partition: {disk}"
    total = sum(p.get("total_gb", 0) for p in partitions)
    assert total > 0, f"Total disk should be > 0 GB, got {total:.0f} GB"
    assert disk.get("current_working_directory", ""), "CWD should not be empty"
    # ``current_drive`` is a Windows-only concept; on POSIX it is empty by design.
    print(f"[PASS] hardware_info: CPU={cpu.get('logical_cores')} cores, "
          f"RAM={mem.get('total_gb')} GB, Disk={total:.0f} GB ({len(partitions)} partitions), "
          f"CWD={disk.get('current_working_directory')}")


def test_gpu_info_provider():
    """Validate that GPUInfoProvider returns structured GPU metadata when hardware is present.

    The test skips (prints SKIP) when no GPU is detected because GPU info
    is optional on desktop machines. When data is present, it asserts the
    GPU list is non-empty and every GPU has a non-empty name string because
    the agent uses GPU presence to decide on compute-offloading behavior.
    """
    from encre.device_context.providers.gpu import GPUInfoProvider
    p = GPUInfoProvider()
    data = p.collect()
    if data is None:
        print("[SKIP] gpu_info: No GPU detected (not a failure)")
        return
    gpus = data.get("gpus", [])
    assert len(gpus) > 0, "GPU list should not be empty if data returned"
    for gpu in gpus:
        assert gpu.get("name"), f"GPU name should not be empty: {gpu}"
    print(f"[PASS] gpu_info: {json.dumps(data, ensure_ascii=False, indent=2)}")


def test_battery_info_provider():
    """Validate that BatteryInfoProvider returns structured battery metadata when present.

    The test skips when no battery is detected (desktop without UPS) because
    battery info is optional. When present, it asserts 'percent' is in the
    range [0, 100] because the agent uses battery state to avoid heavy
    operations on low-power devices.
    """
    from encre.device_context.providers.battery import BatteryInfoProvider
    p = BatteryInfoProvider()
    data = p.collect()
    if data is None:
        print("[SKIP] battery_info: No battery detected (desktop without battery)")
        return
    assert "percent" in data, f"Battery should have percent: {data}"
    assert 0 <= data["percent"] <= 100, f"Battery percent out of range: {data['percent']}"
    print(f"[PASS] battery_info: {data['percent']}%, plugged={data.get('power_plugged')}")


def test_display_info_provider():
    """Validate that DisplayInfoProvider returns structured monitor geometry metadata.

    The test skips when no display data is returned. When present, it asserts
    at least one display entry exists and that its width and height are both
    positive because the agent uses display dimensions to set viewport size
    for browser automation and screenshot resolution.
    """
    from encre.device_context.providers.display import DisplayInfoProvider
    p = DisplayInfoProvider()
    data = p.collect()
    if data is None:
        print("[SKIP] display_info: No display data returned")
        return
    displays = data.get("displays", [])
    assert len(displays) > 0, "Should have at least one display"
    d = displays[0]
    assert d.get("width", 0) > 0, f"Display width should be > 0: {d}"
    assert d.get("height", 0) > 0, f"Display height should be > 0: {d}"
    print(f"[PASS] display_info: {displays[0].get('width')}x{displays[0].get('height')} "
          f"@{displays[0].get('refresh_rate_hz', '?')}Hz")


def test_network_info_provider():
    """Validate that NetworkInfoProvider returns structured network interface metadata.

    The test asserts the hostname is non-empty and at least one network
    interface is reported because the agent uses network topology info to
    determine connectivity status and local address bindings.
    """
    from encre.device_context.providers.network import NetworkInfoProvider
    p = NetworkInfoProvider()
    data = p.collect()
    assert data is not None, "NetworkInfoProvider should return data"
    assert data.get("hostname"), "Hostname should not be empty"
    ifaces = data.get("interfaces", [])
    assert len(ifaces) > 0, "Should have at least one network interface"
    has_lo = any("Loopback" in i.get("name", "") or "lo" in i.get("name", "") for i in ifaces)
    print(f"[PASS] network_info: hostname={data['hostname']}, "
          f"{len(ifaces)} interfaces, loopback={'yes' if has_lo else 'no'}")


def test_sensor_info_provider():
    """Validate that SensorInfoProvider returns structured sensor data when hardware is available.

    The test skips when no sensors are present because sensor data is
    optional on most desktops. When available, it prints the full JSON
    for visual verification without asserting specific values since
    sensor hardware varies widely across systems.
    """
    from encre.device_context.providers.sensors import SensorInfoProvider
    p = SensorInfoProvider()
    data = p.collect()
    if data is None:
        print("[SKIP] sensor_info: No sensors available (expected on most desktops)")
        return
    print(f"[PASS] sensor_info: {json.dumps(data, ensure_ascii=False, indent=2)}")


def test_location_info_provider():
    """Validate that LocationInfoProvider returns timezone and UTC offset metadata.

    The test asserts timezone and utc_offset are non-empty because the
    agent uses timezone info for timestamp normalization and scheduling.
    GPS coordinates are optional and printed when available for debugging.
    """
    from encre.device_context.providers.location import LocationInfoProvider
    p = LocationInfoProvider()
    data = p.collect()
    assert data is not None, "LocationInfoProvider should return at least timezone"
    assert data.get("timezone"), "Timezone should not be empty"
    assert data.get("utc_offset"), "UTC offset should not be empty"
    gps = data.get("gps") or {}
    print(f"[PASS] location_info: tz={data['timezone']}, offset={data['utc_offset']}")
    if gps.get("latitude") is not None:
        print(f"  GPS: {gps['latitude']:.4f}, {gps['longitude']:.4f} "
              f"(accuracy={gps.get('accuracy', '?')}m, source={gps.get('source', '?')})")
    else:
        print("  GPS: OS location service unavailable (expected on some setups)")


# 鈹€鈹€ Catalog tests 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


def test_catalog_builds_from_real_data():
    """Validate that DeviceContextManager.build_catalog() produces a complete context catalog.

    The test creates a manager with device_context_enabled=True, builds the
    catalog synchronously, and asserts the catalog string contains the header
    '## Device Context', the OS line, a real OS name (Windows/Linux/Darwin),
    a location section, and the tool availability listing because the catalog
    is injected into the system prompt and must contain all required sections.
    """
    from encre.device_context.manager import DeviceContextManager
    from encre.config import EncreConfig
    import asyncio

    config = EncreConfig()
    config.device_context_enabled = True
    mgr = DeviceContextManager(config)
    catalog = asyncio.run(mgr.build_catalog())
    assert catalog, "Catalog should not be empty"
    assert "## Device Context" in catalog, "Should have Device Context header"
    assert "OS:" in catalog, "Should have OS line"
    assert "Windows" in catalog or "Linux" in catalog or "Darwin" in catalog, \
        "Should have real OS name"
    assert ("User Location" in catalog) or ("Location" in catalog), \
        "Should have location section"
    assert "Device tools available:" in catalog, "Should list available tools"
    print(f"[PASS] catalog:\n{catalog}")


# 鈹€鈹€ Tool tests 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


@pytest.mark.asyncio
async def test_device_info_tool():
    """Validate that EncreDeviceInfoTool.execute(detail=False) returns summary hardware JSON.

    The test first asserts the tool class inherits from EncreTool (registration
    contract), then executes with detail=False and parses the JSON result.
    It asserts cpu, ram, disk, and current_directory keys are present because
    the summary view must include the core hardware signals the agent needs.
    """
    from encre.tools.builtin.device_info import EncreDeviceInfoTool
    from encre.tools.base import EncreTool
    assert isinstance(EncreDeviceInfoTool, EncreTool)
    result = await EncreDeviceInfoTool.execute(detail=False)
    data = json.loads(result)
    assert "cpu" in data, f"Should have cpu info: {data}"
    assert "ram" in data, f"Should have ram info: {data}"
    assert "disk" in data, f"Should have disk info: {data}"
    assert "current_directory" in data, f"Should have current_directory: {data}"
    print(f"[PASS] device_info (summary): {json.dumps(data, ensure_ascii=False, indent=2)}")


@pytest.mark.asyncio
async def test_device_info_tool_detail():
    """Validate that EncreDeviceInfoTool.execute(detail=True) returns full hardware JSON.

    The test parses the JSON result and asserts the top-level keys 'hardware'
    and 'platform' exist, that cpu.logical_cores > 0, that memory.total_gb > 0,
    that at least one disk partition exists, and that total disk capacity > 0
    because the detail view must provide complete hardware telemetry.
    """
    from encre.tools.builtin.device_info import EncreDeviceInfoTool
    result = await EncreDeviceInfoTool.execute(detail=True)
    data = json.loads(result)
    assert "hardware" in data, f"Should have hardware key: {list(data.keys())}"
    assert "platform" in data, f"Should have platform key: {list(data.keys())}"
    hw = data["hardware"]
    assert hw["cpu"]["logical_cores"] > 0
    assert hw["memory"]["total_gb"] > 0
    disk = hw.get("disk", {})
    parts = disk.get("partitions", [])
    assert len(parts) > 0, f"Should have partitions: {disk}"
    total = sum(p.get("total_gb", 0) for p in parts)
    assert total > 0, f"Total disk should be > 0 GB, got {total:.0f} GB"
    print(f"[PASS] device_info (detail): platform={data['platform']['os']['system']}, "
          f"RAM={hw['memory']['total_gb']}GB, CPU={hw['cpu']['logical_cores']}cores, "
          f"Disk={total:.0f}GB ({len(parts)} partitions), "
          f"CWD={disk.get('current_working_directory')}")


@pytest.mark.asyncio
async def test_device_battery_tool():
    """Validate that EncreDeviceBatteryTool.execute() returns battery metadata when hardware is present.

    The test skips when the tool returns a non-JSON string (no battery).
    When data is present, it asserts 'percent' exists and is in [0, 100]
    because the battery tool must report a valid charge percentage.
    """
    from encre.tools.builtin.device_battery import EncreDeviceBatteryTool
    result = await EncreDeviceBatteryTool.execute()
    data = json.loads(result) if result.startswith("{") else None
    if data is None:
        print(f"[SKIP] device_battery: {result}")
        return
    assert "percent" in data
    assert 0 <= data["percent"] <= 100
    print(f"[PASS] device_battery: {data['percent']}%, plugged={data.get('power_plugged')}")


@pytest.mark.asyncio
async def test_device_location_tool():
    """Validate that EncreDeviceLocationTool.execute() returns timezone and UTC offset.

    The test skips when the tool returns non-JSON (location service unavailable).
    When data is present, it asserts 'timezone' and 'utc_offset' keys exist
    because the location tool must always provide temporal context.
    """
    from encre.tools.builtin.device_location import EncreDeviceLocationTool
    result = await EncreDeviceLocationTool.execute()
    data = json.loads(result) if result.startswith("{") else None
    if data is None:
        print(f"[SKIP] device_location: {result}")
        return
    assert "timezone" in data
    assert "utc_offset" in data
    print(f"[PASS] device_location: tz={data['timezone']}, offset={data['utc_offset']}")


@pytest.mark.asyncio
async def test_device_display_tool():
    """Validate that EncreDeviceDisplayTool.execute() returns at least one display entry.

    The test skips when the tool returns non-JSON (no display hardware).
    When data is present, it asserts the displays list is non-empty and
    prints the primary display resolution because the agent uses display
    geometry to configure browser viewport settings.
    """
    from encre.tools.builtin.device_display import EncreDeviceDisplayTool
    result = await EncreDeviceDisplayTool.execute()
    data = json.loads(result) if result.startswith("{") else None
    if data is None:
        print(f"[SKIP] device_display: {result}")
        return
    displays = data.get("displays", [])
    assert len(displays) > 0
    print(f"[PASS] device_display: {len(displays)} display(s), "
          f"primary: {displays[0].get('width')}x{displays[0].get('height')}")


@pytest.mark.asyncio
async def test_device_network_tool():
    """Validate that EncreDeviceNetworkTool.execute() returns hostname and interface list.

    The test skips when the tool returns non-JSON. When data is present,
    it asserts 'hostname' and 'interfaces' keys exist and that the
    interfaces list is non-empty because network metadata is required
    for the agent to determine connectivity and bind addresses.
    """
    from encre.tools.builtin.device_network import EncreDeviceNetworkTool
    result = await EncreDeviceNetworkTool.execute()
    data = json.loads(result) if result.startswith("{") else None
    if data is None:
        print(f"[SKIP] device_network: {result}")
        return
    assert "hostname" in data
    assert "interfaces" in data
    assert len(data["interfaces"]) > 0
    print(f"[PASS] device_network: hostname={data['hostname']}, "
          f"{len(data['interfaces'])} interfaces")


@pytest.mark.asyncio
async def test_device_sensor_tool():
    """Validate that EncreDeviceSensorTool.execute() returns sensor data when hardware is available.

    The test skips when the result indicates sensors are unavailable.
    When data is present, it parses JSON and prints it for visual
    verification because sensor hardware varies widely and specific
    value assertions would be platform-dependent.
    """
    from encre.tools.builtin.device_sensor import EncreDeviceSensorTool
    result = await EncreDeviceSensorTool.execute()
    if "unavailable" in result.lower() or "no sensor" in result.lower():
        print(f"[SKIP] device_sensor: {result}")
        return
    data = json.loads(result)
    print(f"[PASS] device_sensor: {json.dumps(data, ensure_ascii=False, indent=2)}")


# 鈹€鈹€ Prompt file test 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


def test_device_context_prompt_file():
    """Validate that the device_context prompt template substitutes {{device_context}} correctly.

    The test loads the prompt via PromptLoader with a known catalog string and
    asserts the placeholder is replaced in the output because the prompt
    template must inject the live device context catalog into the system prompt.
    It also asserts the prompt file exists on disk at the resolved path.
    """
    from encre.prompts.loader import PromptLoader
    loader = PromptLoader()
    content = loader.load_with_context("device_context", device_context="Test catalog content")
    assert "Test catalog content" in content, "Prompt should substitute {{device_context}}"
    print(f"[PASS] device_context.prompt: template works correctly")
    path = loader.get_block_path("device_context")
    assert os.path.isfile(path), f"Prompt file should exist at {path}"
    print(f"[PASS] device_context.prompt file exists at: {path}")


# 鈹€鈹€ Config test 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


def test_config_has_device_context_fields():
    """Validate that EncreConfig exposes all device_context configuration fields with correct defaults.

    The test asserts device_context_enabled is True by default, and that
    device_context_cache_ttl and device_context_providers attributes exist
    because the config schema must expose all fields the manager reads.
    """
    from encre.config import EncreConfig
    c = EncreConfig()
    assert hasattr(c, "device_context_enabled"), "Config should have device_context_enabled"
    assert c.device_context_enabled is True, "Default should be True"
    assert hasattr(c, "device_context_cache_ttl"), "Config should have device_context_cache_ttl"
    assert hasattr(c, "device_context_providers"), "Config should have device_context_providers"
    print(f"[PASS] config: device_context_enabled={c.device_context_enabled}, "
          f"ttl={c.device_context_cache_ttl}s")


# 鈹€鈹€ Tool registration test 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


def test_tools_registered_in_defaults():
    """Validate that all 6 device_* tools are registered when register_default_tools is called.

    The test creates a fresh ToolRegistry, registers defaults, collects all
    tool names, and asserts the expected set {'device_info', 'device_location',
    'device_sensor', 'device_battery', 'device_display', 'device_network'} is
    fully present because the default registry must expose all device context
    tools for agent discovery.
    """
    from encre.tools.registry import ToolRegistry
    from encre.tools.defaults import register_default_tools
    registry = ToolRegistry()
    register_default_tools(registry)
    tool_names = {t.name for t in registry.all()}
    expected = {"device_info", "device_location", "device_sensor",
                "device_battery", "device_display", "device_network"}
    missing = expected - tool_names
    assert not missing, f"Tools missing from registry: {missing}"
    print(f"[PASS] All 6 device_* tools registered in defaults")


# 鈹€鈹€ Full integration test (run with pytest -s to see output) 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


if __name__ == "__main__":
    # Manual runner
    test_platform_info_provider()
    test_hardware_info_provider()
    test_gpu_info_provider()
    test_battery_info_provider()
    test_display_info_provider()
    test_network_info_provider()
    test_sensor_info_provider()
    test_location_info_provider()
    test_catalog_builds_from_real_data()
    test_device_context_prompt_file()
    test_config_has_device_context_fields()
    test_tools_registered_in_defaults()

    import asyncio
    asyncio.run(test_device_info_tool())
    asyncio.run(test_device_info_tool_detail())
    asyncio.run(test_device_battery_tool())
    asyncio.run(test_device_location_tool())
    asyncio.run(test_device_display_tool())
    asyncio.run(test_device_network_tool())
    asyncio.run(test_device_sensor_tool())
    print("\n=== ALL TESTS PASSED ===")
