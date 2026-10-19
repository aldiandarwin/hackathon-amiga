import type { Metadata } from 'next'
import type { ReactNode } from 'react'

// Exists only for the tab title: the page itself is a client component.
export const metadata: Metadata = {
  title: 'Persetujuan',
}

export default function ApprovalsLayout({ children }: Readonly<{ children: ReactNode }>) {
  return children
}
