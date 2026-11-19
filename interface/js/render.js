// 空值与“无”的唯一渲染处；页面不得自行判断分数为 0 还是空。
function renderScore(v) {
  return (v === null || v === undefined || v === '') ? '无' : String(v);
}

function renderReason(code, reasons) {
  if (!code) return '—';
  const hit = (reasons || []).find(r => r.code === code);
  return hit ? `${code} ${hit.text}` : code;
}

function renderRows(tbody, rows, cols) {
  tbody.innerHTML = '';
  for (const row of rows) {
    const tr = document.createElement('tr');
    for (const c of cols) {
      const td = document.createElement('td');
      td.textContent = typeof c === 'function' ? c(row) : (row[c] ?? '');
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }
}

function renderKV(el, obj) {
  el.innerHTML = '';
  for (const [k, v] of Object.entries(obj)) {
    const p = document.createElement('p');
    p.textContent = `${k}：${v === null || v === undefined ? '无' : v}`;
    el.appendChild(p);
  }
}
