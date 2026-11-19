// 页面装配：只调 API 与 render，不做规则计算。接口字段见 docs/09_接口清单.md。
let state = { runId: null, page: 1, size: 50, reasons: [] };

document.querySelectorAll('#nav button').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('#nav button').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    const target = btn.dataset.page;
    document.querySelectorAll('.page').forEach(p => p.classList.toggle('active', p.id === `page-${target}`));
  });
});

async function boot() {
  try {
    state.reasons = await API.get('/api/reasons');
  } catch (e) {
    console.warn('原因码未就绪', e);
  }
}

async function ensureRun(scale) {
  const { run_id } = await API.post('/api/runs', { year: 2026, scale });
  state.runId = run_id;
  document.getElementById('status').textContent = `运行 ${run_id}`;
  return run_id;
}

document.getElementById('btn-run')?.addEventListener('click', async () => {
  const scale = document.getElementById('scale').value;
  await ensureRun(scale);
  await API.post(`/api/runs/${state.runId}/execute`, { batches: [1, 2, 3, 4] });
  const p = await API.get(`/api/runs/${state.runId}/progress`);
  document.getElementById('run-info').textContent = `完成：${p.done}/${p.total}`;
  renderRows(document.querySelector('#balances tbody'), p.balances || [],
    ['batch', 'quota', 'admitted', 'remaining']);
});

document.getElementById('btn-batch3')?.addEventListener('click', async () => {
  const scale = document.getElementById('scale').value;
  await ensureRun(scale);
  await API.post(`/api/runs/${state.runId}/execute`, { batches: [3] });
  document.getElementById('run-info').textContent = '第三批已执行';
});

document.getElementById('btn-student')?.addEventListener('click', async () => {
  const sid = document.getElementById('sid').value.trim();
  const data = await API.get(`/api/students/${sid}/result`, { run_id: state.runId });
  const out = document.getElementById('student-out');
  renderKV(out, {
    '考生': data.student_id,
    '总分': renderScore(data.score),
    '是否录取': data.admitted ? '是' : '否',
    '批次': renderScore(data.batch),
    '学校': data.school || '无',
    '志愿序号': renderScore(data.volunteer_no),
  });
  const list = document.createElement('div');
  (data.volunteers || []).forEach(v => {
    const p = document.createElement('p');
    p.textContent = `批次 ${v.batch} 志愿 ${v.seq}：${v.plan_id} ${v.status} ${renderReason(v.reason_code, state.reasons)}`;
    list.appendChild(p);
  });
  out.appendChild(list);
});

document.getElementById('btn-plan')?.addEventListener('click', async () => {
  const pid = document.getElementById('pid').value.trim();
  const data = await API.get(`/api/plans/${pid}/admissions`, { run_id: state.runId, page: state.page, size: state.size });
  renderKV(document.getElementById('plan-summary'), {
    '计划': data.plan_id,
    '名额': data.quota,
    '已录': data.admitted_count,
    '余额': data.remaining,
    '最低录取分': renderScore(data.min_score),
    '末位考生': data.last_admitted ? `${data.last_admitted.student_id}（${data.last_admitted.score}，志愿 ${data.last_admitted.volunteer_no}）` : '无',
  });
  renderRows(document.querySelector('#plan-rows tbody'), data.items || [],
    ['admit_order', 'student_id', 'score', 'volunteer_no']);
  document.getElementById('page-info').textContent = `第 ${data.page} 页 / 共 ${data.total} 条`;
});

document.getElementById('btn-stats')?.addEventListener('click', async () => {
  const batch = document.getElementById('stat-batch').value;
  const data = await API.get(`/api/stats/batch/${batch}`, { run_id: state.runId });
  renderKV(document.getElementById('stats-out'), {
    '计划数': data.plan_count,
    '录取数': data.admitted_count,
    '完成率': data.fill_rate,
    '未录取': data.unadmitted_count,
    '最低录取分': renderScore(data.min_score),
  });
});

boot();
