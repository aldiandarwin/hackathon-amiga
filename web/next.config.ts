import type { NextConfig } from 'next'
import { frontendConfig } from './server-config.mjs'

// FastAPI (app/main.py) owns every /api/v1 route and the amiga_session cookie.
// Proxying it through this origin keeps browser calls same-origin, so the
// HttpOnly cookie is sent: cookies are scoped by host, not by port.
// The server-only environment is validated at build time as well as in proxy.ts.
const { backendOrigin: BACKEND_ORIGIN } = frontendConfig()

const nextConfig: NextConfig = {
  poweredByHeader: false,
  // The rewrite proxy cuts a request at 30 s by default. A chat answer can take several model rounds, so give it
  // 60 s; the server ends a turn at 25 s and answers by search instead, so this is only a safety margin.
  experimental: { proxyTimeout: 60_000 },
  async rewrites() {
    return [
      { source: '/review', destination: `${BACKEND_ORIGIN}/review` },
      { source: '/static/:path*', destination: `${BACKEND_ORIGIN}/static/:path*` },
      { source: '/verifikasi/:path*', destination: `${BACKEND_ORIGIN}/verifikasi/:path*` },
      {
        source: '/api/v1/:path*',
        destination: `${BACKEND_ORIGIN}/api/v1/:path*`,
      },
    ]
  },
}

export default nextConfig
