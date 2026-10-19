'use client'

import type { ReactNode } from 'react'
import { OFFLINE_MESSAGE } from '../lib/api'
import { useMainAppOrigin } from '../lib/hooks'
import { IconAlert, IconLock, IconPlug } from './icons'

// Screen states shared by every page, so the wording stays the same everywhere.

export function LoadingState({ title }: { title: string }) {
  return (
    <section className="card state" role="status" aria-live="polite">
      <span className="loader" aria-hidden="true" />
      <h2>{title}</h2>
    </section>
  )
}

export function SignedOutState({ onRetry }: { onRetry: () => void }) {
  const origin = useMainAppOrigin()
  return (
    <section className="card state" aria-labelledby="signed-out-title">
      <span className="state-icon state-icon-teal">
        <IconLock size={26} />
      </span>
      <h2 id="signed-out-title">Masuk dulu ke AMIGA, ya.</h2>
      <p>Masuk dengan akun PIC, Finance, atau Manajer Keuangan untuk melanjutkan pekerjaan Anda.</p>
      <div className="state-actions">
        <a className="button button-primary" href={`${origin}/review?next=dashboard`}>
          Masuk ke AMIGA
        </a>
        <button type="button" className="button button-secondary" onClick={onRetry}>
          Saya sudah masuk
        </button>
      </div>
    </section>
  )
}

export function OfflineState({ onRetry, autoRetry }: { onRetry: () => void; autoRetry: boolean }) {
  return (
    <section className="card state state-warn" role="alert">
      <span className="state-icon state-icon-amber">
        <IconPlug size={26} />
      </span>
      <h2>{OFFLINE_MESSAGE}</h2>
      <p>Pastikan aplikasi AMIGA sudah menyala, lalu coba lagi.</p>
      {autoRetry ? <p className="state-note">Halaman ini juga mencoba sendiri tiap 15 detik.</p> : null}
      <div className="state-actions">
        <button type="button" className="button button-primary" onClick={onRetry}>
          Coba lagi
        </button>
      </div>
    </section>
  )
}

export function ErrorState({
  title,
  message,
  onRetry,
  children,
}: {
  title: string
  message: string
  onRetry?: () => void
  children?: ReactNode
}) {
  return (
    <section className="card state state-warn" role="alert">
      <span className="state-icon state-icon-amber">
        <IconAlert size={26} />
      </span>
      <h2>{title}</h2>
      <p>{message}</p>
      {children}
      {onRetry ? (
        <div className="state-actions">
          <button type="button" className="button button-primary" onClick={onRetry}>
            Coba lagi
          </button>
        </div>
      ) : null}
    </section>
  )
}
