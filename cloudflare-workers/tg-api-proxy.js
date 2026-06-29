// Cloudflare Worker: Telegram Bot API Proxy
// Proxies requests to api.telegram.org for regions where Telegram is blocked.
//
// Deploy this worker and use its URL as TG_API_URL in your bot config.
// Example: https://tg-api-proxy.your-domain.workers.dev
//
// Bot sends requests to:
//   https://tg-api-proxy.your-domain.workers.dev/bot<TOKEN>/sendMessage
// Worker forwards them to:
//   https://api.telegram.org/bot<TOKEN>/sendMessage
//
// No environment variables needed.

const TG_API = 'https://api.telegram.org';

export default {
  async fetch(request) {
    const url = new URL(request.url);

    if (url.pathname === '/' || url.pathname === '') {
      return new Response('Telegram API Proxy', { status: 200 });
    }

    const tgUrl = TG_API + url.pathname + url.search;

    const headers = new Headers(request.headers);
    headers.delete('Host');

    try {
      const resp = await fetch(tgUrl, {
        method: request.method,
        headers,
        body: request.method !== 'GET' ? request.body : undefined,
      });

      return new Response(resp.body, {
        status: resp.status,
        headers: resp.headers,
      });
    } catch (err) {
      return new Response(JSON.stringify({ ok: false, description: err.message }), {
        status: 502,
        headers: { 'Content-Type': 'application/json' },
      });
    }
  },
};
