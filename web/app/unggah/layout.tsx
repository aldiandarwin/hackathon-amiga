import type { Metadata } from 'next'
import type { ReactNode } from 'react'

// Exists only for the tab title: the page itself is a client component.
export const metadata: Metadata = {
  title: 'Unggah invoice',
}

export default function UploadLayout({ children }: Readonly<{ children: ReactNode }>) {
  return children
}
