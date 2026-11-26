// 页面装配：只调 API 与 render，不做规则计算。接口字段见 docs/09_接口清单.md。
const state = {
  runId: localStorage.getItem('sim.runId') || null,
  page: 1,
  size: 50,
  reasons: [],
  pollTimer: null,
};

const $ = sel => document.querySelector(sel);

function setStatus(text) {
  $('#status').textContent = text;
}

function showToast(message, kind = 'error') {
  const el = $('#toast');
  el.textContent = message;
  el.className = `toast ${kind}`;
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => el.classList.add('hidden'), 5000);
}

async function guard(button, fn) {
  const old = button.disabled;
  button.disabled = true;
  try {
    await fn();
  } catch (err) {
    console.error(err);
    showToast(err.message || String(err));
  } finally {
    button.disabled = old;
  }
}

document.querySelectorAll('#nav button').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('#nav button').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    const target = btn.dataset.page;
    document.querySelectorAll('.page').forEach(p => p.classList.toggle('active', p.id === `page-${target}`));
  });
});

const BALANCE_COLS = [
  { key: 'batch', fmt: r => renderScore(r.batch) },
  { key: 'quota', fmt: r => renderScore(r.quota) },
  { key: 'admitted', fmt: r => renderScore(r.admitted) },
  { key: 'remaining', fmt: r => renderScore(r.remaining) },
];

const DIST_COLS = [
  { key: 'label', fmt: r => String(r.label ?? '') },
  { key: 'count', fmt: r => String(r.count ?? '') },
];

const BATCH_PLAN_COLS = [
  { key: 'plan_id', fmt: r => renderScore(r.plan_id) },
  { key: 'school', fmt: r => renderScore(r.school) },
  { key: 'category', fmt: r => renderCategory(r.category) },
  { key: 'quota_total', fmt: r => renderScore(r.quota_total) },
  { key: 'admitted_count', fmt: r => renderScore(r.admitted_count) },
  { key: 'remaining', fmt: r => renderScore(r.remaining) },
  { key: 'min_score', fmt: r => renderScore(r.min_score) },
];

function schoolAggCols(labelKey) {
  return [
    { key: labelKey, fmt: r => labelKey === 'category' ? renderCategory(r[labelKey]) : renderScore(r[labelKey]) },
    { key: 'plan_count', fmt: r => renderScore(r.plan_count) },
    { key: 'quota_total', fmt: r => renderScore(r.quota_total) },
    { key: 'admitted_count', fmt: r => renderScore(r.admitted_count) },
    { key: 'completion_rate', fmt: r => formatRate(r.completion_rate, r.completion_rate_text) },
    { key: 'unfilled_quota', fmt: r => renderScore(r.unfilled_quota) },
    { key: 'min_score', fmt: r => renderScore(r.min_score) },
    { key: 'max_score', fmt: r => renderScore(r.max_score) },
  ];
}

const SCHOOL_PLAN_COLS = [
  { key: 'plan_id', fmt: r => renderScore(r.plan_id) },
  { key: 'batch', fmt: r => renderScore(r.batch) },
  { key: 'category', fmt: r => renderCategory(r.category) },
  { key: 'quota_total', fmt: r => renderScore(r.quota_total) },
  { key: 'admitted_count', fmt: r => renderScore(r.admitted_count) },
  { key: 'remaining', fmt: r => renderScore(r.remaining) },
  { key: 'min_score', fmt: r => renderScore(r.min_score) },
  { key: 'last_admitted', fmt: r => lastAdmittedText(r.last_admitted) },
];

async function boot() {
  if (state.runId) {
    setStatus(`运行 ${state.runId}`);
    $('#run-info').textContent = `当前运行 ${state.runId}`;
  }
  renderProgress($('#progress-bar'), $('#progress-text'), { stage: 'idle', done: 0, total: 0 });
  renderRows($('#balances tbody'), [], BALANCE_COLS);
  renderRows($('#distribution tbody'), [], DIST_COLS);
  renderRows($('#batch-plans tbody'), [], BATCH_PLAN_COLS);
  renderRows($('#school-batches tbody'), [], schoolAggCols('batch'));
  renderRows($('#school-categories tbody'), [], schoolAggCols('category'));
  renderRows($('#school-plans tbody'), [], SCHOOL_PLAN_COLS);
  try {
    state.reasons = await API.get('/api/reasons');
  } catch (err) {
    console.warn('原因码未就绪', err);
  }
}

// ---------- 运行控制 ----------

async function createRun() {
  const scale = $('#scale').value;
  const data = await API.post('/api/runs', { year: 2026, scale });
  state.runId = data.run_id;
  localStorage.setItem('sim.runId', state.runId);
  setStatus(`运行 ${state.runId}`);
  $('#run-info').textContent = `已创建运行 ${state.runId}（${scale === 'large' ? '15 万' : '小数据集'}），可以执行投档。`;
}

function renderBalances(balances) {
  renderRows($('#balances tbody'), balances || [], BALANCE_COLS);
}

async function pollProgress() {
  if (!state.runId) return;
  if (state.pollTimer) {
    clearInterval(state.pollTimer);
    state.pollTimer = null;
  }
  let finished = false;

  const tick = async () => {
    const p = await API.get(`/api/runs/${state.runId}/progress`);
    renderProgress($('#progress-bar'), $('#progress-text'), p);
    renderBalances(p.balances);
    if (p.stage === 'done' || p.stage === 'error') {
      finished = true;
      if (state.pollTimer) {
        clearInterval(state.pollTimer);
        state.pollTimer = null;
      }
      $('#run-info').textContent = p.stage === 'done'
        ? `运行 ${state.runId} 已完成。`
        : `运行 ${state.runId} 失败：${p.detail || ''}`;
    }
  };

  await tick();
  if (finished) return;
  state.pollTimer = setInterval(() => {
    tick().catch(err => {
      if (state.pollTimer) {
        clearInterval(state.pollTimer);
        state.pollTimer = null;
      }
      showToast(err.message || String(err));
    });
  }, 800);
}

async function executeBatches(batches) {
  if (!state.runId) throw new Error('请先在“运行控制”新建运行');
  $('#run-info').textContent = `正在执行批次 ${batches.join('、')}…`;
  const data = await API.post(`/api/runs/${state.runId}/execute`, { batches });
  renderProgress($('#progress-bar'), $('#progress-text'), data.progress);
  renderBalances(data.progress && data.progress.balances);
  await pollProgress();
}

// ---------- 考生查询 ----------

function renderStudent(data) {
  const out = $('#student-out');
  out.className = 'card';
  renderKV(out, {
    '考生': data.student_id,
    '姓名': renderScore(data.name),
    '初中': renderScore(data.junior_school),
    '总分': renderScore(data.score),
    '同分序号': renderScore(data.tie_seq),
    '是否录取': data.admitted ? '是' : '否',
    '录取批次': renderScore(data.batch),
    '录取计划': renderScore(data.plan_id),
    '学校': renderScore(data.school),
    '志愿序号': renderScore(data.volunteer_no),
    '录取顺序': renderScore(data.admit_order),
  });
  const title = document.createElement('h3');
  title.textContent = '志愿处理';
  out.appendChild(title);
  const list = document.createElement('div');
  out.appendChild(list);
  renderVolunteers(list, data.volunteers || [], state.reasons);
}

async function loadStudent() {
  if (!state.runId) throw new Error('请先在“运行控制”新建运行');
  const sid = $('#sid').value.trim();
  if (!sid) throw new Error('请输入考生编号');
  const data = await API.get(`/api/students/${encodeURIComponent(sid)}/result`, { run_id: state.runId });
  renderStudent(data);
}

// ---------- 计划与名单 ----------

async function loadPlan(page) {
  if (!state.runId) throw new Error('请先在“运行控制”新建运行');
  const pid = $('#pid').value.trim();
  if (!pid) throw new Error('请输入计划编号');
  const size = Number($('#page-size').value) || 50;
  const data = await API.get(`/api/plans/${encodeURIComponent(pid)}/admissions`, {
    run_id: state.runId,
    page,
    size,
  });

  state.page = page;
  state.size = size;

  const summary = $('#plan-summary');
  summary.className = 'card';
  renderKV(summary, {
    '计划': data.plan_id,
    '学校': renderScore(data.school),
    '批次': renderScore(data.batch),
    '类别': renderCategory(data.category),
    '控制线': renderScore(data.control_line),
    '名额': renderScore(data.quota),
    '转入名额': renderScore(data.carry_in),
    '有效计划数': renderScore(data.quota_total),
    '已录': renderScore(data.admitted_count),
    '余额': renderScore(data.remaining),
    '最低录取分': renderScore(data.min_score),
    '最高录取分': renderScore(data.max_score),
    '末位考生': lastAdmittedText(data.last_admitted),
    '完成情况': Number(data.remaining) > 0 ? '未完成' : '已完成',
  });

  renderRows($('#plan-rows tbody'), data.items || [], [
    { key: 'admit_order', fmt: r => renderScore(r.admit_order) },
    { key: 'student_id', fmt: r => renderScore(r.student_id) },
    { key: 'score', fmt: r => renderScore(r.score) },
    { key: 'volunteer_no', fmt: r => renderScore(r.volunteer_no) },
    { key: 'tie_seq', fmt: r => renderScore(r.tie_seq) },
  ]);

  const total = Number(data.total) || 0;
  const pages = Number(data.total_pages) || Math.max(1, Math.ceil(total / size));
  $('#page-info').textContent = `第 ${data.page} / ${pages} 页，共 ${total} 条`;
  $('#prev').disabled = data.page <= 1;
  $('#next').disabled = data.page >= pages;
}

// ---------- 统计 ----------

async function loadBatchStats() {
  if (!state.runId) throw new Error('请先在“运行控制”新建运行');
  const batch = $('#stat-batch').value;
  const data = await API.get(`/api/stats/batch/${batch}`, { run_id: state.runId });
  const out = $('#stats-out');
  out.className = 'card';
  renderKV(out, {
    '批次': renderScore(data.batch),
    '计划数': renderScore(data.plan_count),
    '有效计划数': renderScore(data.quota_total),
    '录取数': renderScore(data.admitted_count),
    '完成率': formatRate(data.completion_rate, data.completion_rate_text),
    '未完成名额': renderScore(data.unfilled_quota),
    '剩余名额': renderScore(data.remaining_quota),
    '未完成计划数': renderScore(data.unfilled_plans),
    '填报人数': renderScore(data.volunteered_students),
    '未录人数': renderScore(data.unadmitted_students),
    '最低录取分': renderScore(data.min_score),
    '最高录取分': renderScore(data.max_score),
  });
  renderRows($('#batch-plans tbody'), data.plans || [], BATCH_PLAN_COLS);
}

async function loadSchoolStats() {
  if (!state.runId) throw new Error('请先在“运行控制”新建运行');
  const sid = $('#school-id').value.trim();
  if (!sid) throw new Error('请输入学校编号');
  const data = await API.get(`/api/stats/school/${encodeURIComponent(sid)}`, { run_id: state.runId });
  const out = $('#school-out');
  const overall = data.overall || {};
  out.className = 'card';
  renderKV(out, {
    '学校': `${data.school_id || ''} ${data.school || ''}`.trim(),
    '计划数': renderScore(overall.plan_count),
    '有效计划数': renderScore(overall.quota_total),
    '录取数': renderScore(overall.admitted_count),
    '完成率': formatRate(overall.completion_rate, overall.completion_rate_text),
    '未完成名额': renderScore(overall.unfilled_quota),
    '剩余名额': renderScore(overall.remaining_quota),
    '未完成计划数': renderScore(overall.unfilled_plans),
    '最低录取分': renderScore(overall.min_score),
    '最高录取分': renderScore(overall.max_score),
  });
  renderRows($('#school-batches tbody'), data.by_batch || [], schoolAggCols('batch'));
  renderRows($('#school-categories tbody'), data.by_category || [], schoolAggCols('category'));
  renderRows($('#school-plans tbody'), data.plans || [], SCHOOL_PLAN_COLS);
}

async function loadDistribution() {
  if (!state.runId) throw new Error('请先在“运行控制”新建运行');
  const batch = $('#stat-batch').value;
  const data = await API.get(`/api/distribution/${batch}`, { run_id: state.runId });
  renderDistribution($('#distribution tbody'), data);
  const lines = data.lines || {};
  $('#distribution-meta').textContent =
    `共 ${data.total ?? 0} 人；最低 ${renderScore(data.min_score)}；最高 ${renderScore(data.max_score)}；` +
    `控制线 L=${renderScore(lines.control_line)}；第一梯度线 G₁=${renderScore(lines.gradient_first)}；` +
    `Δ=${renderScore(lines.gradient_delta)}`;
}

async function exportCsv() {
  if (!state.runId) throw new Error('请先在“运行控制”新建运行');
  await API.download('/api/export/admissions.csv', { run_id: state.runId });
}

async function exportStatsCsv() {
  if (!state.runId) throw new Error('请先在“运行控制”新建运行');
  await API.download('/api/export/stats.csv', { run_id: state.runId });
}

// ---------- 案例对比 ----------

function renderCaseSide(el, data, otherVolunteers) {
  el.className = 'case-side';
  renderKV(el, {
    '考生': data.student_id,
    '姓名': renderScore(data.name),
    '初中': renderScore(data.junior_school),
    '总分': renderScore(data.score),
    '是否录取': data.admitted ? '是' : '否',
    '录取批次': renderScore(data.batch),
    '录取计划': renderScore(data.plan_id),
    '志愿序号': renderScore(data.volunteer_no),
  });
  const title = document.createElement('h3');
  title.textContent = '志愿处理';
  el.appendChild(title);
  const list = document.createElement('div');
  el.appendChild(list);
  renderVolunteers(list, data.volunteers || [], state.reasons, otherVolunteers);
}

async function loadCase() {
  const sid = $('#case-sid').value.trim();
  const beforeRun = $('#case-before').value.trim();
  const afterRun = $('#case-after').value.trim();
  if (!sid || !beforeRun || !afterRun) throw new Error('请填写考生编号与两个 run_id');

  const [before, after] = await Promise.all([
    API.get(`/api/students/${encodeURIComponent(sid)}/result`, { run_id: beforeRun }),
    API.get(`/api/students/${encodeURIComponent(sid)}/result`, { run_id: afterRun }),
  ]);
  renderCaseSide($('#case-before-out'), before, after.volunteers);
  renderCaseSide($('#case-after-out'), after, before.volunteers);
}

// ---------- 事件绑定 ----------

$('#btn-create').addEventListener('click', e => guard(e.currentTarget, createRun));
$('#btn-run').addEventListener('click', e => guard(e.currentTarget, () => executeBatches([1, 2, 3, 4])));
$('#btn-batch').addEventListener('click', e => guard(e.currentTarget, () => executeBatches([Number($('#batch-select').value)])));
$('#btn-student').addEventListener('click', e => guard(e.currentTarget, loadStudent));
$('#btn-plan').addEventListener('click', e => guard(e.currentTarget, () => loadPlan(1)));
$('#prev').addEventListener('click', e => guard(e.currentTarget, () => loadPlan(state.page - 1)));
$('#next').addEventListener('click', e => guard(e.currentTarget, () => loadPlan(state.page + 1)));
$('#btn-stats').addEventListener('click', e => guard(e.currentTarget, loadBatchStats));
$('#btn-dist').addEventListener('click', e => guard(e.currentTarget, loadDistribution));
$('#btn-export').addEventListener('click', e => guard(e.currentTarget, exportCsv));
$('#btn-export-stats').addEventListener('click', e => guard(e.currentTarget, exportStatsCsv));
$('#btn-school').addEventListener('click', e => guard(e.currentTarget, loadSchoolStats));
$('#btn-case').addEventListener('click', e => guard(e.currentTarget, loadCase));

$('#page-size').addEventListener('change', () => {
  if ($('#pid').value.trim()) {
    loadPlan(1).catch(err => showToast(err.message || String(err)));
  }
});

[['sid', 'btn-student'], ['pid', 'btn-plan'], ['school-id', 'btn-school'], ['case-sid', 'btn-case']]
  .forEach(([input, button]) => {
    $(`#${input}`).addEventListener('keydown', e => {
      if (e.key === 'Enter') $(`#${button}`).click();
    });
  });

boot();
