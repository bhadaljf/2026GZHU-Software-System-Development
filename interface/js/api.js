// 唯一访问后端的方式：页面不直接 fetch，也不拼 URL 细节。
const API = (() => {
  async function request(path, options) {
    const resp = await fetch(path, options);
    if (!resp.ok) {
      const text = await resp.text();
      throw new Error(`${resp.status} ${text}`);
    }
    return resp.headers.get('content-type')?.includes('json') ? resp.json() : resp.text();
  }

  function get(path, params = {}) {
    const qs = new URLSearchParams(params).toString();
    return request(qs ? `${path}?${qs}` : path);
  }

  function post(path, body = {}) {
    return request(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  }

  return { get, post };
})();
