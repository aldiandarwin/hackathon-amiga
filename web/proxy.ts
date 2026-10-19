import { NextResponse, type NextRequest } from 'next/server'
import { frontendConfig, sameOrigin } from './server-config.mjs'

// Validate browser writes before the rewrite. Remote backends authenticate this
// server with a shared secret; local demos keep their existing loopback origin.
// Cookies and CSRF tokens are forwarded unchanged to FastAPI.

const MUTATIONS = new Set(['POST', 'PATCH', 'PUT', 'DELETE'])

export function proxy(request: NextRequest) {
  const { backendOrigin, publicOrigin, proxySecret } = frontendConfig()
  const origin = request.headers.get('origin')
  if (MUTATIONS.has(request.method) && origin !== null && !sameOrigin(origin, request.headers.get('host'), publicOrigin)) {
    return NextResponse.json({ code: 'ORIGIN_REJECTED', message: 'Sumber permintaan tidak diizinkan.' }, { status: 403 })
  }
  const headers = new Headers(request.headers)
  // Replace a visitor-supplied secret. This header is sent upstream, never to the browser.
  headers.delete('x-amiga-proxy-secret')
  if (proxySecret) headers.set('x-amiga-proxy-secret', proxySecret)
  // Local demos retain the loopback contract. The remote backend checks the original
  // approved public origin and the shared secret; its CSRF/session checks still apply.
  if (!proxySecret && MUTATIONS.has(request.method) && origin !== null) headers.set('origin', backendOrigin)
  return NextResponse.next({ request: { headers } })
}

export const config = {
  matcher: ['/api/v1/:path*', '/review', '/static/:path*', '/verifikasi/:path*'],
}
