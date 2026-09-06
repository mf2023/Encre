import { defineConfig } from 'vitepress'

const nav_zh = [
  { text: 'Encre Agent Harness', link: '/harness', activeMatch: '^(harness|en/harness)' },
  { text: 'Encre Agent Core', link: '/core', activeMatch: '^(core|en/core)' },
  { text: 'Encre Agent Desktop', link: '/', activeMatch: '^(?!.*(harness|core)).*$' }
]

const nav_en = [
  { text: 'Encre Agent Harness', link: '/en/harness', activeMatch: '^(harness|en/harness)' },
  { text: 'Encre Agent Core', link: '/en/core', activeMatch: '^(core|en/core)' },
  { text: 'Encre Agent Desktop', link: '/en/', activeMatch: '^(?!.*(harness|core)).*$' }
]

const sidebar_zh = [
  {
    text: '开始使用',
    items: [
      { text: '介绍', link: '/' },
      { text: '快速上手', link: '/getting-started' }
    ]
  },
  {
    text: '核心功能',
    items: [
      { text: '三种工作模式', link: '/modes' },
      { text: '对话与会话', link: '/chat' },
      { text: '工作区', link: '/workspace' },
      { text: '自动化任务', link: '/automation' },
      { text: '全局搜索', link: '/search' },
      { text: '内置工具面板', link: '/panels' }
    ]
  },
  {
    text: '设置',
    items: [
      { text: '模型管理', link: '/models' },
      { text: '智能体', link: '/agents' },
      { text: '网关接入', link: '/gateway' },
      { text: '技能与命令', link: '/skills' },
      { text: 'MCP Server', link: '/mcp' },
      { text: '规则', link: '/rules' },
      { text: '记忆', link: '/memory' },
      { text: '权限与安全', link: '/permissions' },
      { text: '通用设置', link: '/general' },
      { text: '存储与数据', link: '/storage' },
      { text: '用量统计', link: '/usage' }
    ]
  },
  {
    text: '更多',
    items: [
      { text: '快捷键参考', link: '/shortcuts' },
      { text: '常见问题', link: '/faq' },
      { text: '关于与更新', link: '/about' }
    ]
  }
]

const sidebar_en = [
  {
    text: 'Getting Started',
    items: [
      { text: 'Introduction', link: '/en/' },
      { text: 'Quick Start', link: '/en/getting-started' }
    ]
  },
  {
    text: 'Core Features',
    items: [
      { text: 'Three Modes', link: '/en/modes' },
      { text: 'Chat & Sessions', link: '/en/chat' },
      { text: 'Workspace', link: '/en/workspace' },
      { text: 'Automation', link: '/en/automation' },
      { text: 'Search', link: '/en/search' },
      { text: 'Built-in Panels', link: '/en/panels' }
    ]
  },
  {
    text: 'Settings',
    items: [
      { text: 'Models', link: '/en/models' },
      { text: 'Agents', link: '/en/agents' },
      { text: 'Gateway', link: '/en/gateway' },
      { text: 'Skills & Commands', link: '/en/skills' },
      { text: 'MCP Server', link: '/en/mcp' },
      { text: 'Rules', link: '/en/rules' },
      { text: 'Memory', link: '/en/memory' },
      { text: 'Permissions', link: '/en/permissions' },
      { text: 'General', link: '/en/general' },
      { text: 'Storage', link: '/en/storage' },
      { text: 'Usage', link: '/en/usage' }
    ]
  },
  {
    text: 'More',
    items: [
      { text: 'Shortcuts', link: '/en/shortcuts' },
      { text: 'FAQ', link: '/en/faq' },
      { text: 'About', link: '/en/about' }
    ]
  }
]

export default defineConfig({
  lang: 'zh-CN',
  title: 'Encre Agent Docs',
  description: 'Encre Agent Docs - Encre Agent 全产品官方帮助文档',
  base: '/',
  cleanUrls: false,
  head: [
    ['link', { rel: 'icon', href: '/assets/Encre.ico' }]
  ],
  themeConfig: {
    logo: { light: '/assets/Encre-lm.svg', dark: '/assets/Encre-dm.svg', alt: 'Encre' },
    siteTitle: 'Encre Agent Docs',
    search: {
      provider: 'local',
      options: {
        translations: {
          button: { buttonText: '搜索文档', buttonAriaLabel: '搜索文档' },
          modal: {
            noResultsText: '未找到相关结果',
            footer: { selectText: '选择', navigateText: '切换', closeText: '关闭' }
          }
        }
      }
    },
    lastUpdated: { text: '更新于' },
    docFooter: { prev: '上一页', next: '下一页' },
    externalLinkIcon: true,
    outline: { label: '本页目录', level: [2, 3] },
    nav: nav_zh,
    sidebar: sidebar_zh,
    socialLinks: [],
    /* i18n locale switch */
    localeText: { label: 'English', link: '/en/' },
    langMenuLabel: '语言 / Language'
  },
  locales: {
    root: {
      label: '简体中文',
      lang: 'zh-CN',
      themeConfig: {
        nav: nav_zh,
        sidebar: sidebar_zh,
        docFooter: { prev: '上一页', next: '下一页' },
        outline: { label: '本页目录', level: [2, 3] },
        lastUpdated: { text: '更新于' },
        langMenuLabel: '语言 / Language',
        localeText: { label: 'English', link: '/en/' }
      }
    },
    en: {
      label: 'English',
      lang: 'en',
      link: '/en/',
      themeConfig: {
        nav: nav_en,
        sidebar: sidebar_en,
        docFooter: { prev: 'Previous', next: 'Next' },
        outline: { label: 'On this page', level: [2, 3] },
        lastUpdated: { text: 'Updated' },
        langMenuLabel: 'Language',
        localeText: { label: '简体中文', link: '/' }
      }
    }
  },
  markdown: {
    lineNumbers: false,
    image: { lazyLoading: true }
  }
})