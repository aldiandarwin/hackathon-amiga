import type { Metadata } from 'next'
import type { ReactNode } from 'react'

// Exists only for the tab title: the page itself is a client component.
export const metadata: Metadata = {
  title: 'Hubungi klien',
}

export default function HandoverLayout({ children }: Readonly<{ children: ReactNode }>) {
  return children
}
