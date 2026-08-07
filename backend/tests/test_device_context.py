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

from __future__ import annotations

"""Tests for device context providers and tools."""

import json
import sys
import os
import pytest


# ── Provider tests ──────────────────────────────────────────────────


def test_platform_info_provider():
    from encre.device_context.providers.platform_ import PlatformInfoProvider
    p = PlatformInfoProvider()
    data = p.collect()
    assert data is not None, "PlatformInfoProvider should return data"
    os_info = data.get("os", {})
    assert os_info.get("system") == "Windows", f"Expected Windows, got {os_info.get('system')}"
    assert os_info.get("node"), "Hostname should not be empty"
    assert data.get("arch") in ("AMD64", "x86_64", "arm64"), f"Unexpected arch: {data.get('arch')}"
    assert data.get("python", {}).get("version", "").startswith("3"), f"Python version: {data.get('python', {})}"
    print(f"[PASS] platform_info: {json.dumps(data, ensure_ascii=False, indent=2)}")


def test_hardware_info_provider():
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
    assert total > 100, f"Total disk should be > 100 GB, got {total:.0f} GB"
    assert disk.get("current_working_directory", ""), "CWD should not be empty"
    assert disk.get("current_drive", ""), "Current drive should not be empty"
    print(f"[PASS] hardware_info: CPU={cpu.get('logical_cores')} cores, "
          f"RAM={mem.get('total_gb')} GB, Disk={total:.0f} GB ({len(partitions)} partitions), "
          f"CWD={disk.get('current_working_directory')}")


def test_gpu_info_provider():
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
    from encre.device_context.providers.sensors import SensorInfoProvider
    p = SensorInfoProvider()
    data = p.collect()
    if data is None:
        print("[SKIP] sensor_info: No sensors available (expected on most desktops)")
        return
    print(f"[PASS] sensor_info: {json.dumps(data, ensure_ascii=False, indent=2)}")


def test_location_info_provider():
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


# ── Catalog tests ───────────────────────────────────────────────────


def test_catalog_builds_from_real_data():
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
    assert "Location:" in catalog, "Should have location line"
    assert "Device tools available:" in catalog, "Should list available tools"
    print(f"[PASS] catalog:\n{catalog}")


# ── Tool tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_device_info_tool():
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
    assert total > 100, f"Total disk should be > 100 GB, got {total:.0f} GB"
    print(f"[PASS] device_info (detail): platform={data['platform']['os']['system']}, "
          f"RAM={hw['memory']['total_gb']}GB, CPU={hw['cpu']['logical_cores']}cores, "
          f"Disk={total:.0f}GB ({len(parts)} partitions), "
          f"CWD={disk.get('current_working_directory')}")


@pytest.mark.asyncio
async def test_device_battery_tool():
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
    from encre.tools.builtin.device_sensor import EncreDeviceSensorTool
    result = await EncreDeviceSensorTool.execute()
    if "unavailable" in result.lower() or "no sensor" in result.lower():
        print(f"[SKIP] device_sensor: {result}")
        return
    data = json.loads(result)
    print(f"[PASS] device_sensor: {json.dumps(data, ensure_ascii=False, indent=2)}")


# ── Prompt file test ────────────────────────────────────────────────


def test_device_context_prompt_file():
    from encre.prompts.loader import PromptLoader
    loader = PromptLoader()
    content = loader.load_with_context("device_context", device_context="Test catalog content")
    assert "Test catalog content" in content, "Prompt should substitute {{device_context}}"
    print(f"[PASS] device_context.prompt: template works correctly")
    path = loader.get_block_path("device_context")
    assert os.path.isfile(path), f"Prompt file should exist at {path}"
    print(f"[PASS] device_context.prompt file exists at: {path}")


# ── Config test ─────────────────────────────────────────────────────


def test_config_has_device_context_fields():
    from encre.config import EncreConfig
    c = EncreConfig()
    assert hasattr(c, "device_context_enabled"), "Config should have device_context_enabled"
    assert c.device_context_enabled is True, "Default should be True"
    assert hasattr(c, "device_context_cache_ttl"), "Config should have device_context_cache_ttl"
    assert hasattr(c, "device_context_providers"), "Config should have device_context_providers"
    print(f"[PASS] config: device_context_enabled={c.device_context_enabled}, "
          f"ttl={c.device_context_cache_ttl}s")


# ── Tool registration test ──────────────────────────────────────────


def test_tools_registered_in_defaults():
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


# ── Full integration test (run with pytest -s to see output) ────────


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