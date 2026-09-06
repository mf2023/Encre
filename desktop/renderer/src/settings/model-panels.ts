// @ts-nocheck
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

import { getState, setSettings } from "../core/state.js";
import { send } from "../core/ws.js";
import { t } from "../features/i18n.js";
import { platformIconHtml } from "../ui/icons.js";
import type { ModelConfigMeta, ProviderEntry } from "../core/types.js";

interface AdapterFieldDef {
  key: string;
  labelKey: string;
  type: "text" | "password" | "number" | "textarea";
  placeholderKey?: string;
}

interface AdapterDef {
  id: string;
  name: string;
  desc: string;
  fields: AdapterFieldDef[];
  docs?: string;
}

const ADAPTER_DEFS: AdapterDef[] = [
  { id: "bluebubbles", name: "BlueBubbles", desc: "Connect to a BlueBubbles server to send and receive iMessage", fields: [
    { key: "server_url", labelKey: "fieldServerUrl", type: "text", placeholderKey: "placeholderServerUrl" },
    { key: "api_key", labelKey: "fieldApiKey", type: "password", placeholderKey: "placeholderApiKey" },
  ], docs: "https://bluebubbles.app/" },
  { id: "dingtalk", name: "DingTalk", desc: "Connect to a DingTalk custom bot webhook to send work notifications and group messages", fields: [
    { key: "client_id", labelKey: "fieldDingtalkClientId", type: "text", placeholderKey: "placeholderClientId" },
    { key: "client_secret", labelKey: "fieldDingtalkClientSecret", type: "password", placeholderKey: "placeholderClientSecret" },
  ], docs: "https://open.dingtalk.com/document/orgapp/create-and-configure-a-robot" },
  { id: "discord", name: "Discord", desc: "Integrate Discord bots to manage server channel messages and interactions", fields: [
    { key: "token", labelKey: "fieldBotToken", type: "password", placeholderKey: "placeholderBotToken" },
  ], docs: "https://discord.com/developers/applications" },
  { id: "email", name: "Email", desc: "Send and receive emails via SMTP/IMAP, with auto-reply and processing support", fields: [
    { key: "smtp_host", labelKey: "fieldSmtpHost", type: "text", placeholderKey: "placeholderSmtpHost" },
    { key: "smtp_port", labelKey: "fieldSmtpPort", type: "number", placeholderKey: "placeholderSmtpPort" },
    { key: "smtp_user", labelKey: "fieldSmtpUser", type: "text", placeholderKey: "placeholderSmtpUser" },
    { key: "smtp_pass", labelKey: "fieldSmtpPass", type: "password", placeholderKey: "placeholderSmtpPass" },
    { key: "imap_host", labelKey: "fieldImapHost", type: "text", placeholderKey: "placeholderImapHost" },
    { key: "imap_port", labelKey: "fieldImapPort", type: "number", placeholderKey: "placeholderImapPort" },
  ]},
  { id: "feishu", name: "Feishu", desc: "Connect to the Feishu open platform to receive bot events and reply to messages", fields: [
    { key: "app_id", labelKey: "fieldAppId", type: "text", placeholderKey: "placeholderAppId" },
    { key: "app_secret", labelKey: "fieldAppSecret", type: "password", placeholderKey: "placeholderAppSecret" },
  ], docs: "https://open.feishu.cn/document/home/develop-a-bot-in-5-minutes" },
  { id: "google_chat", name: "Google Chat", desc: "Connect to Google Chat spaces to send and receive messages via Webhook", fields: [
    { key: "webhook_url", labelKey: "fieldWebhookUrl", type: "text", placeholderKey: "placeholderWebhookUrl" },
    { key: "service_account", labelKey: "fieldServiceAccount", type: "textarea", placeholderKey: "placeholderServiceAccount" },
  ], docs: "https://developers.google.com/chat" },
  { id: "homeassistant", name: "Home Assistant", desc: "Connect to the Home Assistant smart home platform to control devices and query state", fields: [
    { key: "server_url", labelKey: "fieldServerUrl", type: "text", placeholderKey: "placeholderServerUrl" },
    { key: "access_token", labelKey: "fieldLongLivedToken", type: "password", placeholderKey: "placeholderAccessToken" },
  ], docs: "https://www.home-assistant.io/docs/authentication/" },
  { id: "irc", name: "IRC", desc: "Connect to an IRC server to join channels and auto-respond to messages", fields: [
    { key: "server", labelKey: "fieldServer", type: "text", placeholderKey: "placeholderServer" },
    { key: "port", labelKey: "fieldPort", type: "number", placeholderKey: "placeholderPort" },
    { key: "nickname", labelKey: "fieldNickname", type: "text", placeholderKey: "placeholderNickname" },
    { key: "password", labelKey: "fieldPassword", type: "password", placeholderKey: "placeholderPassword" },
  ]},
  { id: "line", name: "LINE", desc: "Connect to the LINE Messaging API to handle friend and group chat messages", fields: [
    { key: "channel_access_token", labelKey: "fieldChannelAccessToken", type: "password", placeholderKey: "placeholderChannelAccessToken" },
    { key: "channel_secret", labelKey: "fieldChannelSecret", type: "password", placeholderKey: "placeholderChannelSecret" },
  ], docs: "https://developers.line.biz/en/services/messaging-api/" },
  { id: "matrix", name: "Matrix", desc: "Connect to the Matrix decentralized communication network to join rooms and auto-respond to messages", fields: [
    { key: "homeserver_url", labelKey: "fieldHomeserverUrl", type: "text", placeholderKey: "placeholderHomeserverUrl" },
    { key: "access_token", labelKey: "fieldAccessToken", type: "password", placeholderKey: "placeholderAccessToken" },
  ], docs: "https://matrix.org/docs/guides/" },
  { id: "mattermost", name: "Mattermost", desc: "Integrate the Mattermost team collaboration platform to listen and send channel messages", fields: [
    { key: "server_url", labelKey: "fieldServerUrl", type: "text", placeholderKey: "placeholderServerUrl" },
    { key: "token", labelKey: "fieldBotToken", type: "password", placeholderKey: "placeholderBotToken" },
  ], docs: "https://developers.mattermost.com/" },
  { id: "ntfy", name: "ntfy", desc: "Send notification messages via the ntfy push service", fields: [
    { key: "topic", labelKey: "fieldTopic", type: "text", placeholderKey: "placeholderTopic" },
    { key: "server_url", labelKey: "fieldServerUrl", type: "text", placeholderKey: "placeholderServerUrl" },
  ], docs: "https://ntfy.sh/docs/" },
  { id: "photon", name: "Photon", desc: "Connect to the Photon social platform for messaging and interaction", fields: [
    { key: "api_url", labelKey: "fieldApiUrl", type: "text", placeholderKey: "placeholderApiUrl" },
    { key: "api_key", labelKey: "fieldApiKey", type: "password", placeholderKey: "placeholderApiKey" },
  ]},
  { id: "qqbot", name: "QQ", desc: "Connect to the QQ platform to receive and reply to group and private chat messages in real time", fields: [
    { key: "app_id", labelKey: "fieldAppId", type: "text", placeholderKey: "placeholderAppId" },
    { key: "client_secret", labelKey: "fieldClientSecret", type: "password", placeholderKey: "placeholderClientSecret" },
  ], docs: "https://bot.q.qq.com/wiki/" },
  { id: "raft", name: "Raft", desc: "Connect to the Raft distributed communication network to handle inter-node messages", fields: [
    { key: "node_id", labelKey: "fieldNodeId", type: "text", placeholderKey: "placeholderNodeId" },
    { key: "peers", labelKey: "fieldPeers", type: "text", placeholderKey: "placeholderPeers" },
  ]},
  { id: "signal", name: "Signal", desc: "Connect to the Signal messaging service to send and receive encrypted messages via REST API", fields: [
    { key: "phone_number", labelKey: "fieldPhoneNumber", type: "text", placeholderKey: "placeholderPhoneNumber" },
    { key: "api_url", labelKey: "fieldApiUrl", type: "text", placeholderKey: "placeholderApiUrl" },
  ]},
  { id: "simplex", name: "SimpleX", desc: "Connect to the SimpleX decentralized messaging platform for private secure communication", fields: [
    { key: "server_url", labelKey: "fieldServerUrl", type: "text", placeholderKey: "placeholderServerUrl" },
    { key: "display_name", labelKey: "fieldDisplayName", type: "text", placeholderKey: "placeholderDisplayName" },
  ], docs: "https://simplex.chat/" },
  { id: "slack", name: "Slack", desc: "Integrate a Slack workspace to listen on and send channel messages via Bot Token", fields: [
    { key: "token", labelKey: "fieldBotToken", type: "password", placeholderKey: "placeholderBotToken" },
    { key: "signing_secret", labelKey: "fieldSigningSecret", type: "password", placeholderKey: "placeholderSigningSecret" },
  ], docs: "https://api.slack.com/apps" },
  { id: "sms", name: "SMS", desc: "Connect to an SMS provider API to send and receive SMS notifications", fields: [
    { key: "provider", labelKey: "fieldProvider", type: "text", placeholderKey: "placeholderProvider" },
    { key: "account_sid", labelKey: "fieldAccountSid", type: "text", placeholderKey: "placeholderAccountSid" },
    { key: "auth_token", labelKey: "fieldAuthToken", type: "password", placeholderKey: "placeholderAuthToken" },
  ]},
  { id: "teams", name: "Microsoft Teams", desc: "Integrate Microsoft Teams to handle channel and group chat messages via Bot Framework", fields: [
    { key: "app_id", labelKey: "fieldAppId", type: "text", placeholderKey: "placeholderAppId" },
    { key: "app_password", labelKey: "fieldAppPassword", type: "password", placeholderKey: "placeholderAppPassword" },
  ], docs: "https://learn.microsoft.com/en-us/microsoftteams/platform/" },
  { id: "telegram", name: "Telegram", desc: "Connect to the Telegram Bot API to automatically handle commands and conversations in channels and direct messages", fields: [
    { key: "token", labelKey: "fieldBotToken", type: "password", placeholderKey: "placeholderBotToken" },
  ], docs: "https://core.telegram.org/bots#how-do-i-create-a-bot" },
  { id: "webhook", name: "Webhook", desc: "Start a Webhook listener to receive HTTP callbacks from external systems", fields: [
    { key: "listen_path", labelKey: "fieldListenPath", type: "text", placeholderKey: "placeholderListenPath" },
    { key: "secret", labelKey: "fieldSecret", type: "password", placeholderKey: "placeholderSecret" },
  ]},
  { id: "weixin", name: "WeChat", desc: "After configuring iLink Bot, connect to WeChat to send and receive messages and auto-reply", fields: [], docs: "https://www.wechatbot.dev/zh/protocol" },
  { id: "wecom", name: "WeCom", desc: "Connect to a WeCom custom app to enable internal message notifications and collaboration", fields: [
    { key: "token", labelKey: "fieldWecomToken", type: "text", placeholderKey: "placeholderWecomToken" },
    { key: "encoding_aes_key", labelKey: "fieldEncodingAesKey", type: "password", placeholderKey: "placeholderEncodingAesKey" },
    { key: "receive_id", labelKey: "fieldWecomReceiveId", type: "text", placeholderKey: "placeholderWecomReceiveId" },
  ], docs: "https://developer.work.weixin.qq.com/document/" },
  { id: "whatsapp", name: "WhatsApp", desc: "Connect to the WhatsApp Business API to handle customer messages and conversations", fields: [
    { key: "phone_number_id", labelKey: "fieldPhoneNumberId", type: "text", placeholderKey: "placeholderPhoneNumberId" },
    { key: "access_token", labelKey: "fieldAccessToken", type: "password", placeholderKey: "placeholderAccessToken" },
  ], docs: "https://developers.facebook.com/docs/whatsapp/" },
  { id: "yuanbao", name: "Yuanbao", desc: "Connect to the Yuanbao open platform to exchange messages via API", fields: [
    { key: "app_key", labelKey: "fieldAppKey", type: "text", placeholderKey: "placeholderAppKey" },
    { key: "app_secret", labelKey: "fieldAppSecret", type: "password", placeholderKey: "placeholderAppSecret" },
  ]},
];

export function renderModelImpl(this: any): void {
    const st = getState();
    const models = st.modelConfigs;
    const activeIdx = st.activeModelIndex;

    let rowsHtml = "";
    for (let i = 0; i < models.length; i++) {
      const m = models[i];
      const isActive = i === activeIdx && m.enabled !== false;
      rowsHtml += `
        <div class="model-table-row" data-model-idx="${i}">
          <div class="model-table-cell model-cell-name">
            <span class="model-name-text">${this.esc(m.name || t("common.unnamed"))}</span>
            ${isActive ? `<span class="model-active-tag">${t("settings.inUse")}</span>` : ''}
          </div>
          <div class="model-table-cell model-cell-provider">${this.esc(m.backend_type)}</div>
          <div class="model-table-cell model-cell-actions">
            <button class="btn-icon" data-action="edit" data-idx="${i}" data-tooltip="${t("settings.edit")}">
              <i data-lucide="pencil" class="lucide"></i>
            </button>
            <button class="btn-icon btn-icon--danger" data-action="delete" data-idx="${i}" data-tooltip="${t("settings.delete")}">
              <i data-lucide="trash-2" class="lucide"></i>
            </button>
            <label class="toggle-switch toggle-sm">
              <input type="checkbox" class="model-enable-toggle" data-idx="${i}" ${m.enabled !== false ? "checked" : ""} />
              <span class="toggle-slider"></span>
            </label>
          </div>
        </div>`;
    }

    const tableHtml = models.length === 0
      ? `<div class="model-empty"><i data-lucide="cpu" class="lucide"></i><span>${t("settings.noModelsYet")}</span></div>`
      : `
        <div class="model-table">
          <div class="model-table-header">
            <div class="model-table-cell model-cell-name">${t("settings.model")}</div>
            <div class="model-table-cell model-cell-provider">${t("settings.provider")}</div>
            <div class="model-table-cell model-cell-actions">${t("settings.actions")}</div>
          </div>
          ${rowsHtml}
        </div>`;

    this.panels.model.innerHTML = `
      <div class="settings-section-title"><i data-lucide="cpu" class="lucide section-title-icon"></i> ${t("settings.modelManagement")}</div>
      <div class="settings-card">
        <div class="model-manage-header">
          <div class="model-manage-desc">${t("settings.modelManagementDesc")}</div>
          <button class="btn-add-model-top" id="btn-goto-create-model">
            <i data-lucide="plus" class="lucide"></i>
            <span>${t("settings.addModel")}</span>
          </button>
        </div>
        ${tableHtml}
      </div>`;

    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: this.panels.model });
    }
  }

export function renderGatewayImpl(this: any): void {
    const st = getState();
    const s = st.settings;
    const gs = st.gatewayStatus;
    const adapters = gs?.adapters ?? [];

    let cardsHtml = "";
    for (const def of ADAPTER_DEFS) {
      const adapterNameKey = `settings.adapterName${def.id.charAt(0).toUpperCase() + def.id.slice(1)}`;
      const displayName = t(adapterNameKey);
      const enabled = !!(s[`adapter_${def.id}_enabled` as keyof typeof s]);
      const statusInfo = adapters.find(a => a.name === def.id);
      const connected = statusInfo?.connected ?? false;

      const fieldCount = def.fields.length;
      const allConfigured = def.fields.every(f => {
        const val = s[`adapter_${def.id}_${f.key}` as keyof typeof s];
        return val && String(val).length > 0;
      });

      // Unified status: only ONE state shown at a time
      let statusLabel: string;
      let statusStyle: string;
      if (!enabled) {
        statusLabel = `○ ${t("settings.adapterDisabled")}`;
        statusStyle = "color:var(--text-muted)";
      } else if (!allConfigured) {
        statusLabel = `○ ${t("settings.adapterNotConfigured")}`;
        statusStyle = "color:var(--text-muted)";
      } else if (connected) {
        statusLabel = `● ${t("settings.adapterStatusConnected")}`;
        statusStyle = "color:var(--text-success)";
      } else {
        statusLabel = `● ${t("settings.adapterStatusDisconnected")}`;
        statusStyle = "color:var(--text-warning)";
      }

      // Description shows connection error, adapter description, or config hint
      const connErr = statusInfo?.error || null;
      let descHtml: string;
      if (connErr && enabled && allConfigured) {
        descHtml = `<span style="color:var(--text-danger);font-size:11px"><i data-lucide="alert-circle" style="width:11px;height:11px;display:inline-block;vertical-align:middle;margin-right:3px"></i> ${this.esc(connErr)}</span>`;
      } else if (!enabled) {
        descHtml = `<span style="color:var(--text-muted);font-size:11px">${t("settings.adapterDisabled")} · ${this.esc(t(`settings.adapterDesc${def.id.charAt(0).toUpperCase() + def.id.slice(1)}`))}</span>`;
      } else if (!allConfigured) {
        descHtml = `<span style="color:var(--text-muted);font-size:11px">${this.esc(t(`settings.adapterDesc${def.id.charAt(0).toUpperCase() + def.id.slice(1)}`))}</span>`;
      } else {
        descHtml = `<span style="color:var(--text-muted);font-size:11px">${this.esc(t(`settings.adapterDesc${def.id.charAt(0).toUpperCase() + def.id.slice(1)}`))}</span>`;
      }

      const iconHtml = platformIconHtml(def.id, 22, "", "margin-right:10px");

      cardsHtml += `
        <div class="settings-card" style="margin-bottom:12px">
          <div class="settings-item-row" data-adapter-toggle="${def.id}">
            <div class="settings-item-info">
              <div class="settings-item-title" style="display:flex;align-items:center">
                ${iconHtml}
                 ${this.esc(displayName)}
                <span style="margin-left:8px;font-size:11px;font-weight:400">${statusLabel}</span>
              </div>
              <div class="settings-item-desc">${descHtml}</div>
            </div>
            <div class="settings-item-control" style="gap:8px">
              <label class="toggle-switch" onclick="event.stopPropagation()">
                <input type="checkbox" id="adapter-enable-${def.id}" ${enabled ? "checked" : ""} />
                <span class="toggle-slider"></span>
              </label>
              <button class="btn-icon" id="adapter-expand-${def.id}" data-adapter-expand="${def.id}" data-tooltip="${t("settings.adapterConfig")}">
                <i data-lucide="arrow-up-right" style="width:16px;height:16px"></i>
              </button>
            </div>
          </div>
        </div>`;
    }

    this.panels.gateway.innerHTML = `
      <div class="settings-section-title"><i data-lucide="network" class="lucide section-title-icon"></i> ${t("settings.gatewayManagement")}</div>
      ${cardsHtml}`;

    // Bind event listeners
    for (const def of ADAPTER_DEFS) {
      const enableToggle = document.getElementById(`adapter-enable-${def.id}`) as HTMLInputElement;
      if (enableToggle) {
        enableToggle.addEventListener("change", () => {
          const enabled = enableToggle.checked;
          const current = { ...getState().settings, [`adapter_${def.id}_enabled`]: enabled };
          setSettings(current as any);
          send({ type: "configure", config: { [`adapter_${def.id}_enabled`]: enabled } });
          this.renderGateway();
        });
      }

      const expandBtn = document.getElementById(`adapter-expand-${def.id}`);
      if (expandBtn) {
        expandBtn.addEventListener("click", (e) => {
          e.stopPropagation();
          this._showAdapterConfigDialog(def.id);
        });
      }

      const docsLink = document.querySelector(`[data-adapter-docs="${def.id}"]`) as HTMLAnchorElement;
      if (docsLink) {
        docsLink.addEventListener("click", (e) => {
          e.preventDefault();
          e.stopPropagation();
          const behavior = (getState().settings.default_link_behavior as string) || "system";
          const url = def.docs || "";
          if (behavior === "in_app") {
            const api = (window as any).electronAPI;
            if (api?.openChildWindow) { api.openChildWindow(url, url); return; }
          } else {
            const api = (window as any).electronAPI;
            if (api?.openExternal) { api.openExternal(url); return; }
          }
          window.open(url, "_blank");
});
  }

}
    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: this.panels.gateway });
    }
  }
