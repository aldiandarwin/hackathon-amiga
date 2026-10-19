'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { createContext, useCallback, useContext, useEffect, useState, type ComponentType, type ReactNode } from 'react'
import { useMainAppOrigin } from '../lib/hooks'
import { approvalStage, canUpload, roleLabel } from '../lib/status'
import { IconCheck, IconDashboard, IconSend, IconSidebar, IconUpload } from './icons'

export type ShellAuth =
  | { kind: 'unknown' }
  | { kind: 'signed-out' }
  | { kind: 'signed-in'; name: string; role: string }

const ReportAuthContext = createContext<(auth: ShellAuth) => void>(() => {})

/**
 * Pages already load the session for their own data, so they report the result here.
 * The header then always agrees with what the page shows, without a second request.
 */
export function useReportAuth(): (auth: ShellAuth) => void {
  return useContext(ReportAuthContext)
}

interface NavItem {
  href: string
  label: string
  short: string
  icon: ComponentType<{ size?: number }>
}

const DASHBOARD: NavItem = { href: '/', label: 'Dashboard', short: 'Dashboard', icon: IconDashboard }
const UPLOAD: NavItem = { href: '/unggah', label: 'Unggah invoice', short: 'Unggah', icon: IconUpload }
const APPROVALS: NavItem = { href: '/persetujuan', label: 'Persetujuan', short: 'Setujui', icon: IconCheck }
const HANDOVER: NavItem = { href: '/hubungi-klien', label: 'Hubungi klien', short: 'Klien', icon: IconSend }
const PAGES: NavItem[] = [DASHBOARD, UPLOAD, APPROVALS, HANDOVER]

/**
 * The PIC uploads and hands final vouchers to the client; Finance and the Manajer Keuangan decide.
 * Until a page reports the role, only Dashboard shows.
 */
function navFor(auth: ShellAuth): NavItem[] {
  if (auth.kind !== 'signed-in') return [DASHBOARD]
  if (canUpload(auth.role)) return [DASHBOARD, UPLOAD, HANDOVER]
  if (approvalStage(auth.role)) return [DASHBOARD, APPROVALS]
  return [DASHBOARD]
}

function isActive(pathname: string, href: string): boolean {
  return href === '/' ? pathname === '/' : pathname === href || pathname.startsWith(`${href}/`)
}

function sameAuth(a: ShellAuth, b: ShellAuth): boolean {
  if (a.kind !== b.kind) return false
  if (a.kind === 'signed-in' && b.kind === 'signed-in') return a.name === b.name && a.role === b.role
  return true
}

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part.charAt(0).toUpperCase())
    .join('')
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? '/'
  const origin = useMainAppOrigin()
  const [auth, setAuth] = useState<ShellAuth>({ kind: 'unknown' })
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  useEffect(() => {
    try { setSidebarCollapsed(localStorage.getItem('amiga.sidebar.collapsed') === 'true') } catch { /* Storage is optional. */ }
  }, [])
  const toggleSidebar = () => {
    const collapsed = !sidebarCollapsed
    setSidebarCollapsed(collapsed)
    try { localStorage.setItem('amiga.sidebar.collapsed', String(collapsed)) } catch { /* Keep the control usable. */ }
  }
  const sidebarLabel = sidebarCollapsed ? 'Tampilkan sidebar' : 'Sembunyikan sidebar'
  const report = useCallback((next: ShellAuth) => {
    setAuth((current) => (sameAuth(current, next) ? current : next))
  }, [])
  const nav = navFor(auth)
  const currentPage = PAGES.find((item) => isActive(pathname, item.href))?.label ?? 'Robot Admin'

  return (
    <ReportAuthContext.Provider value={report}>
      <a className="skip-link" href="#konten">
        Lewati ke konten
      </a>
      <div className={sidebarCollapsed ? 'app is-sidebar-collapsed' : 'app'}>
        <aside className="sidebar" id="workspace-sidebar" aria-label="Navigasi workspace" hidden={sidebarCollapsed}>
          <div className="sidebar-top">
            <Link href="/" className="brand" aria-label="amiga Robot Admin, kembali ke dashboard">
              <img className="brand-logo" src="/brand/amiga-logo.png" alt="AMIGA" width={1080} height={304} />
              <span className="brand-tag" aria-hidden="true">
                Robot Admin
              </span>
            </Link>
          </div>
          <nav className="nav" aria-label="Navigasi utama">
            <ul>
              {nav.map((item) => {
                const active = isActive(pathname, item.href)
                const Glyph = item.icon
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      className={active ? 'nav-link is-active' : 'nav-link'}
                      aria-current={active ? 'page' : undefined}
                    >
                      <Glyph size={20} />
                      <span className="nav-label">{item.label}</span>
                      <span className="nav-short" aria-hidden="true">
                        {item.short}
                      </span>
                    </Link>
                  </li>
                )
              })}
            </ul>
          </nav>
          <p className="sidebar-foot">Robot Admin untuk invoice vendor</p>
        </aside>

        <div className="main">
          <header className="topbar">
            <div className="topbar-start">
              <button type="button" className="sidebar-toggle" onClick={toggleSidebar}
                aria-label={sidebarLabel} title={sidebarLabel}
                aria-controls="workspace-sidebar" aria-expanded={!sidebarCollapsed}>
                <IconSidebar size={20} />
              </button>
              <p className="crumbs">
                <span>Robot Admin</span>
                <span aria-hidden="true">/</span>
                <strong>{currentPage}</strong>
              </p>
            </div>
            <UserChip auth={auth} origin={origin} />
          </header>
          <div className="content">{children}</div>
        </div>
      </div>
    </ReportAuthContext.Provider>
  )
}

function UserChip({ auth, origin }: { auth: ShellAuth; origin: string }) {
  if (auth.kind === 'signed-in') {
    return (
      <div className="user-chip">
        <span className="avatar" aria-hidden="true">
          {initials(auth.name)}
        </span>
        <span className="user-text">
          <span className="sr-only">Masuk sebagai </span>
          <span className="user-name">{auth.name}</span>
          <span className="user-role">{roleLabel(auth.role)}</span>
        </span>
        <a className="account-switch" href="/review?switch=1">Ganti akun</a>
      </div>
    )
  }
  if (auth.kind === 'signed-out') {
    return (
      <a className="button button-secondary button-small user-signin" href={`${origin}/review?next=dashboard`}>
        Masuk
      </a>
    )
  }
  return <span className="user-chip is-placeholder" aria-hidden="true" />
}
