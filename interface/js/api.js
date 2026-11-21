// 唯一访问后端的方式：页面不直接 fetch，也不拼 URL 细节。
const API = (() => {
  function query(params = {}) {
    const usable = Object.entries(params)
      .filter(([, v]) => v !== undefined && v !== null && v !== '');
    return new URLSearchParams(usable).toString();
  }

  async function failure(resp) {
    const text = await resp.text();
    let detail = text;
    try {
      const data = JSON.parse(text);
      detail = data.detail || text;
    } catch (_) { /* 非 JSON，保留原文 */ }
    throw new Error(`${resp.status} ${detail}`);
  }

  async function request(path, options) {
    const resp = await fetch(path, options);
    if (!resp.ok) return failure(resp);
    const type = resp.headers.get('content-type') || '';
    return type.includes('application/json') ? resp.json() : resp.text();
  }

  function get(path, params = {}) {
    const qs = query(params);
    return request(qs ? `${path}?${qs}` : path);
  }

  function post(path, body = {}) {
    return request(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  }

  async function download(path, params = {}) {
    const qs = query(params);
    const url = qs ? `${path}?${qs}` : path;
    const resp = await fetch(url);
    if (!resp.ok) return failure(resp);
    const blob = await resp.blob();
    const cd = resp.headers.get('content-disposition') || '';
    const hit = cd.match(/filename="?([^";]+)"?/i);
    const name = hit ? hit[1] : 'download.csv';
    const a = document.createElement('a');
    const href = URL.createObjectURL(blob);
    a.href = href;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(href);
  }

  return { get, post, download };
})();
