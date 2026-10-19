import '@fontsource-variable/figtree'
import type { Metadata, Viewport } from 'next'
import type { ReactNode } from 'react'
import Script from 'next/script'
import { AppShell } from '../components/shell'
import './globals.css'

export const metadata: Metadata = {
  title: {
    default: 'Dashboard antrean · AMIGA Robot Admin',
    template: '%s · AMIGA Robot Admin',
  },
  description: 'Pantau dan unggah invoice vendor. AI membaca, aturan memeriksa, Finance memutuskan.',
  icons: { icon: '/brand/amiga-icon.png', apple: '/brand/amiga-icon.png' },
}

export const viewport: Viewport = {
  themeColor: '#324158',
}

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="id">
      <body>
        <AppShell>{children}</AppShell>
        {/* Robot Admin chat on every screen; FastAPI serves it, the /static rewrite keeps it same-origin. */}
        <Script src="/static/chat-dock.js" strategy="afterInteractive" />
      </body>
    </html>
  )
}
