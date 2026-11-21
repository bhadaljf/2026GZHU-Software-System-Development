// 空值与“无”的唯一渲染处；页面不得自行判断分数为 0 还是空。
function isNil(v) {
  return v === null || v === undefined || v === '';
}

function renderScore(v) {
  return isNil(v) ? '无' : String(v);
}

function renderReason(code, reasons) {
  if (isNil(code)) return '—';
  const hit = (reasons || []).find(r => r.code === code);
  return hit ? `${code} ${hit.text}` : code;
}

function renderStatus(status) {
  const labels = { admitted: '录取', skipped: '跳过' };
  return labels[status] || status || '—';
}

function renderRows(tbody, rows, cols) {
  tbody.innerHTML = '';
  if (!rows || rows.length === 0) {
    const tr = document.createElement('tr');
    const td = document.createElement('td');
    td.colSpan = cols.length;
    td.className = 'empty-cell';
    td.textContent = '无数据';
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }
  for (const row of rows) {
    const tr = document.createElement('tr');
    for (const col of cols) {
      const td = document.createElement('td');
      let text;
      if (typeof col === 'function') text = col(row);
      else if (typeof col === 'string') text = isNil(row[col]) ? '' : row[col];
      else if (col.fmt) text = col.fmt(row);
      else text = isNil(row[col.key]) ? '' : row[col.key];
      td.textContent = text ?? '';
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }
}

function renderKV(el, obj) {
  el.innerHTML = '';
  for (const [k, v] of Object.entries(obj)) {
    const p = document.createElement('p');
    const label = document.createElement('span');
    label.className = 'kv-key';
    label.textContent = `${k}：`;
    const value = document.createElement('span');
    value.textContent = isNil(v) ? '无' : String(v);
    p.append(label, value);
    el.appendChild(p);
  }
}

function renderProgress(barEl, textEl, p) {
  const data = p || {};
  const total = Number(data.total) || 0;
  const done = Number(data.done) || 0;
  let pct = 0;
  if (data.stage === 'done') pct = 100;
  else if (total > 0) pct = Math.min(100, Math.round(done / total * 100));
  barEl.style.width = `${pct}%`;
  const labels = { idle: '未开始', running: '执行中', done: '已完成', error: '失败', unknown: '未知' };
  const stage = labels[data.stage] || data.stage || '未开始';
  textEl.textContent = `阶段：${stage}　进度：${done}/${total}（${pct}%）${data.detail ? `　${data.detail}` : ''}`;
}

function renderDistribution(tbody, data) {
  const buckets = (data && data.buckets) || [];
  renderRows(tbody, buckets, [
    { key: 'label', fmt: r => String(r.label ?? '') },
    { key: 'count', fmt: r => String(r.count ?? '') },
  ]);
}

function formatRate(v) {
  if (isNil(v)) return '无';
  const n = Number(v);
  if (Number.isNaN(n)) return String(v);
  // 4 号约定 0—1 的小数；若直接给百分数也兼容。
  const pct = n <= 1 ? n * 100 : n;
  return `${pct.toFixed(1)}%`;
}

function lastAdmittedText(v) {
  if (!v) return '无';
  return `${v.student_id}（${renderScore(v.score)} 分，志愿 ${renderScore(v.volunteer_no)}，同分序号 ${renderScore(v.tie_seq)}）`;
}

function renderVolunteers(el, volunteers, reasons, other) {
  el.innerHTML = '';
  if (!volunteers || volunteers.length === 0) {
    el.className = 'empty';
    el.textContent = '无志愿记录';
    return;
  }
  el.className = 'volunteers';
  const otherMap = new Map((other || []).map(v => [`${v.batch}-${v.seq}`, v]));
  for (const v of volunteers) {
    const p = document.createElement('p');
    const peer = otherMap.get(`${v.batch}-${v.seq}`);
    const changed = Boolean(other) && (!peer
      || peer.plan_id !== v.plan_id
      || peer.status !== v.status
      || peer.reason_code !== v.reason_code);
    p.className = changed ? 'vol changed' : 'vol';
    p.textContent = `批次 ${v.batch} 志愿 ${v.seq}：${v.plan_id}　${renderStatus(v.status)}　${renderReason(v.reason_code, reasons)}`;
    el.appendChild(p);
  }
}

function renderEmpty(el, text) {
  el.className = 'card empty';
  el.innerHTML = '';
  el.textContent = text;
}
