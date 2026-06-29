// Cloudflare Worker: Telegram Bot Webhook Proxy
// Forwards incoming Telegram updates to your backend server.
//
// Environment variables (set in Workers dashboard or wrangler.toml):
//   BACKEND_URL  – e.g. https://n-sun.ru/tg-webhook/
//   SECRET_TOKEN – must match TG_WEBHOOK_SECRET on the bot side

export default {
  async fetch(request, env) {
    if (request.method !== 'POST') {
      return new Response('OK', { status: 200 });
    }

    const secretHeader = request.headers.get('X-Telegram-Bot-Api-Secret-Token') || '';
    if (env.SECRET_TOKEN && secretHeader !== env.SECRET_TOKEN) {
      return new Response('Unauthorized', { status: 403 });
    }

    const body = await request.arrayBuffer();
    const backendUrl = env.BACKEND_URL;
    if (!backendUrl) {
      return new Response('BACKEND_URL not configured', { status: 500 });
    }

    const headers = new Headers();
    headers.set('Content-Type', 'application/json');
    if (env.SECRET_TOKEN) {
      headers.set('X-Telegram-Bot-Api-Secret-Token', env.SECRET_TOKEN);
    }

    try {
      const resp = await fetch(backendUrl, {
        method: 'POST',
        headers,
        body,
      });
      return new Response(await resp.text(), {
        status: resp.status,
        headers: { 'Content-Type': 'text/plain' },
      });
    } catch (err) {
      return new Response('Backend error: ' + err.message, { status: 502 });
    }
  },
};
