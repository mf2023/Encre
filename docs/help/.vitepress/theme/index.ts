import { h, onMounted, defineComponent, watch } from 'vue'
import DefaultTheme from 'vitepress/theme'
import './custom.css'

const STORAGE_KEY = 'encre-help-sidebar-collapsed'

// ── Init component (sidebar restore + lang switcher lifecycle) ──
const EncreHelpInit = defineComponent({
  name: 'EncreHelpInit',
  setup() {
    onMounted(() => {
      // restore sidebar collapse state (desktop only)
      if (window.innerWidth >= 960) {
        let collapsed = false
        try { collapsed = localStorage.getItem(STORAGE_KEY) === '1' } catch { /* ignore */ }
        applyCollapsed(collapsed)
      }
      // bind lang switcher trigger as soon as it appears in DOM
      const bindTrigger = () => {
        const btn = document.querySelector('.encre-lang-trigger') as HTMLElement | null
        if (btn && !btn.dataset.bound) setupLangSwitcher()
      }
      bindTrigger()
      // re-bind after every DOM mutation (e.g. VitePress route transition)
      new MutationObserver(bindTrigger).observe(document.body, { childList: true, subtree: true })
      // close dropdown on outside click / Escape
      document.addEventListener('click', (e) => {
        const t = e.target
        const trig = document.querySelector('.encre-lang-trigger')
        const dd = document.querySelector('.encre-lang-dropdown')
        if (t instanceof Node && trig && trig.contains(t)) return
        if (t instanceof Node && dd && dd.contains(t)) return
        closeLangDropdown()
      })
      document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeLangDropdown() })
      // re-close dropdown on route change
      let lastPath = window.location.pathname
      watch(() => window.location.pathname, (p) => {
        if (p !== lastPath) { lastPath = p; closeLangDropdown() }
      })
    })
    return () => h('div', { class: 'encre-help-init' })
  }
})

function applyCollapsed(collapsed: boolean) {
  document.documentElement.classList.toggle('collapse-sidebar', collapsed)
  try {
    localStorage.setItem(STORAGE_KEY, collapsed ? '1' : '0')
  } catch { /* ignore */ }
}

function toggleSidebar() {
  const root = document.documentElement
  if (window.innerWidth >= 960) {
    applyCollapsed(!root.classList.contains('collapse-sidebar'))
    return
  }
  const sidebar = document.querySelector('.VPSidebar')
  if (!sidebar) return
  const isOpen = sidebar.classList.contains('open')
  if (isOpen) {
    const backdrop = document.querySelector('.VPBackdrop') as HTMLElement | null
    if (backdrop) {
      backdrop.click()
    } else {
      sidebar.classList.remove('open')
      document.body.style.overflow = ''
    }
  } else {
    const menu = document.querySelector('.VPLocalNav .menu') as HTMLElement | null
    if (menu) {
      menu.click()
    } else {
      sidebar.classList.add('open')
      document.body.style.overflow = 'hidden'
    }
  }
}

// ── Language switcher ──────────────────────────────────────────
// Replicates the Encre Agent Desktop "settings-dropdown" pattern:
// a trigger button + a floating dropdown div appended to <body>,
// positioned via getBoundingClientRect(), with fixed item order and
// the current language marked `.selected`. No Vue reactivity for the
// list — pure DOM, exactly like the app's openEncreMenu / bindChildRegionDropdown.
const LANGS = [
  { label: 'English', path: '/en/' },
  { label: '简体中文', path: '/' }
]

function currentLangPath(): string {
  const p = window.location.pathname.replace(/\.html$/, '')
  if (p === '/en' || p === '/en/' || p.startsWith('/en/')) return '/en/'
  return '/'
}

function currentLangLabel(): string {
  const cur = currentLangPath()
  return (LANGS.find((l) => l.path === cur) || LANGS[0]).label
}

let langDropdownEl: HTMLElement | null = null

function closeLangDropdown() {
  if (langDropdownEl) {
    langDropdownEl.remove()
    langDropdownEl = null
  }
  document.querySelectorAll('.encre-lang-trigger.open').forEach((el) => el.classList.remove('open'))
}

function openLangDropdown(triggerEl: HTMLElement) {
  closeLangDropdown()
  const cur = currentLangPath()
  const dd = document.createElement('div')
  dd.className = 'settings-dropdown encre-lang-dropdown open'
  dd.innerHTML = LANGS.map(
    (l) =>
      `<div class="settings-dropdown-item${l.path === cur ? ' selected' : ''}" data-path="${l.path}">${l.label}</div>`
  ).join('')
  document.body.appendChild(dd)
  const rect = triggerEl.getBoundingClientRect()
  dd.style.position = 'fixed'
  dd.style.top = `${rect.bottom + 4}px`
  dd.style.left = 'auto'
  dd.style.right = `${window.innerWidth - rect.right}px`
  langDropdownEl = dd
  triggerEl.classList.add('open')
  dd.querySelectorAll('.settings-dropdown-item').forEach((item) => {
    item.addEventListener('click', (e) => {
      e.stopPropagation()
      const path = (item as HTMLElement).getAttribute('data-path') || '/'
      closeLangDropdown()
      if (path !== currentLangPath()) {
        window.location.href = path
      }
    })
  })
  dd.addEventListener('click', (e) => e.stopPropagation())
}

function setupLangSwitcher() {
  const btn = document.querySelector('.encre-lang-trigger') as HTMLElement | null
  if (!btn) return
  if (!btn.dataset.bound) {
    btn.dataset.bound = '1'
    btn.addEventListener('click', (e) => {
      e.stopPropagation()
      e.preventDefault()
      if (btn.classList.contains('open')) closeLangDropdown()
      else openLangDropdown(btn)
    })
  }
}

export default {
  extends: DefaultTheme,
  Layout: () =>
    h(DefaultTheme.Layout, null, {
      'nav-bar-title-after': () =>
        h('button', {
          class: 'nav-sidebar-toggle',
          'aria-label': 'Toggle sidebar',
          title: 'Toggle sidebar',
          onClick: (e: Event) => {
            e.preventDefault()
            e.stopPropagation()
            toggleSidebar()
          },
          innerHTML:
            '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M9 5v14"/></svg>'
        }),
      'nav-bar-content-after': () =>
        h('button', {
          class: 'encre-lang-trigger',
          type: 'button',
          'aria-label': 'Language',
          title: 'Language',
          innerHTML:
            '<svg class="encre-lang-globe" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3a14 14 0 0 1 0 18"/><path d="M12 3a14 14 0 0 0 0 18"/></svg>' +
            '<svg class="encre-lang-chevron" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>'
        }),
      'layout-bottom': () => h(EncreHelpInit)
    })
}
