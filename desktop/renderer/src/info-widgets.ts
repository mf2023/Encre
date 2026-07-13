/**
 * Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
 *
 * This file is part of Encre.
 * The Encre project belongs to the Dunimd Team.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * You may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *
 * DISCLAIMER: Users must comply with applicable AI regulations.
 * Non-compliance may result in service termination or legal liability.
 */

/**
 * Info-card widget templates.
 *
 * Fixed visual templates for travel and real-time info cards. Each function
 * returns an inline HTML fragment that is rendered directly into the chat
 * DOM (not inside the sandboxed HTML iframe used by display='base').
 */

export type FlightData = {
  flightNo: string;
  airline: string;
  terminal?: string;
  departureCode: string;
  departureAirport: string;
  departureTime: string;
  arrivalCode: string;
  arrivalAirport: string;
  arrivalTime: string;
  gate?: string;
  seat?: string;
  status?: string;
};

export type TrainData = {
  trainNo: string;
  type: string;
  departureStation: string;
  departureTime: string;
  arrivalStation: string;
  arrivalTime: string;
  platform?: string;
  seat?: string;
  status?: string;
};

export type ShipData = {
  shipName: string;
  operator: string;
  departurePort: string;
  departureTime: string;
  arrivalPort: string;
  arrivalTime: string;
  dock?: string;
  cabin?: string;
  status?: string;
};

export function renderFlightWidget(data: FlightData): string {
  const statusColor = data.status?.includes("delayed") ? "#fbbf24" : "#4ade80";
  return `
    <div class="encre-widget-card encre-widget-flight">
      <div class="encre-widget-header">
        <span class="encre-widget-badge">航班</span>
        <div class="encre-widget-title">${escapeHtml(data.flightNo)}</div>
        <div class="encre-widget-subtitle">${escapeHtml(data.airline)}${data.terminal ? ` · ${escapeHtml(data.terminal)}` : ""}</div>
      </div>
      <div class="encre-widget-body">
        <div class="flight-stage"><div class="dot-live"></div><div class="text">LIVE</div></div>
        <div class="flight-route">
          <div class="flight-airport">
            <span class="iata">${escapeHtml(data.departureCode)}<small>${escapeHtml(data.departureAirport)}</small></span>
            <span class="time">${escapeHtml(data.departureTime)}</span>
          </div>
          <div class="flight-plane-icon">✈</div>
          <div class="flight-airport">
            <span class="iata">${escapeHtml(data.arrivalCode)}<small>${escapeHtml(data.arrivalAirport)}</small></span>
            <span class="time">${escapeHtml(data.arrivalTime)}</span>
          </div>
        </div>
      </div>
      <div class="encre-widget-foot">
        <div class="flight-info-block">
          ${data.gate ? `<div class="flight-info-row"><span>登机口 <b>${escapeHtml(data.gate)}</b></span></div>` : ""}
          ${data.seat ? `<div class="flight-info-row"><span>座位 <b>${escapeHtml(data.seat)}</b></span></div>` : ""}
          <div class="flight-info-row"><span>状态 <b style="color:${statusColor};">${escapeHtml(data.status || "准点")}</b></span></div>
        </div>
        ${data.gate ? `<div class="flight-gate"><small>登机口</small>${escapeHtml(data.gate)}</div>` : ""}
      </div>
    </div>`;
}

export function renderTrainWidget(data: TrainData): string {
  return `
    <div class="encre-widget-card encre-widget-train">
      <div class="encre-widget-header">
        <span class="encre-widget-badge">高铁</span>
        <div class="encre-widget-title train-no-tag">${escapeHtml(data.trainNo)}<small>${escapeHtml(data.type)}</small></div>
        <div class="encre-widget-subtitle">${escapeHtml(data.status || "准点")}</div>
      </div>
      <div class="encre-widget-body">
        <div class="train-route">
          <div class="train-station">
            <span class="name">${escapeHtml(data.departureStation)}</span>
            <span class="time">${escapeHtml(data.departureTime)}</span>
          </div>
          <div class="train-arrow">→</div>
          <div class="train-station right">
            <span class="name">${escapeHtml(data.arrivalStation)}</span>
            <span class="time">${escapeHtml(data.arrivalTime)}</span>
          </div>
        </div>
      </div>
      <div class="encre-widget-foot">
        ${data.platform ? `<div class="train-platform"><div class="label">检票口</div><div class="value">${escapeHtml(data.platform)}</div></div>` : ""}
        ${data.seat ? `<div class="train-status">${escapeHtml(data.seat)}</div>` : ""}
      </div>
    </div>`;
}

export function renderShipWidget(data: ShipData): string {
  const statusColor = data.status?.includes("delayed") ? "#fbbf24" : "#4ade80";
  return `
    <div class="encre-widget-card encre-widget-ship">
      <div class="encre-widget-header">
        <span class="encre-widget-badge">轮船</span>
        <div class="encre-widget-title">${escapeHtml(data.shipName)}</div>
        <div class="encre-widget-subtitle">${escapeHtml(data.operator)}</div>
      </div>
      <div class="encre-widget-body">
        <div class="ship-stage"><div class="dot-live"></div><div class="text">航行中</div></div>
        <div class="ship-route">
          <div class="ship-port">
            <span class="name">${escapeHtml(data.departurePort)}</span>
            <span class="time">${escapeHtml(data.departureTime)}</span>
          </div>
          <div class="ship-wave">≋</div>
          <div class="ship-port">
            <span class="name">${escapeHtml(data.arrivalPort)}</span>
            <span class="time">${escapeHtml(data.arrivalTime)}</span>
          </div>
        </div>
      </div>
      <div class="encre-widget-foot">
        <div class="ship-info-block">
          ${data.dock ? `<div class="ship-info-row"><span>登船口 <b>${escapeHtml(data.dock)}</b></span></div>` : ""}
          ${data.cabin ? `<div class="ship-info-row"><span>舱位 <b>${escapeHtml(data.cabin)}</b></span></div>` : ""}
          <div class="ship-info-row"><span>状态 <b style="color:${statusColor};">${escapeHtml(data.status || "准点")}</b></span></div>
        </div>
        ${data.dock ? `<div class="ship-dock"><small>登船口</small>${escapeHtml(data.dock)}</div>` : ""}
      </div>
    </div>`;
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
