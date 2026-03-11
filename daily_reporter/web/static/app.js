// Kgent V3 Web — Vue 3 SPA
// 架构：Vue 3 CDN + Vue Router 4 CDN，无构建工具
'use strict';

const { createApp, ref, computed, onMounted, onUnmounted, watch, nextTick, h } = Vue;
const { createRouter, createWebHistory, RouterLink, RouterView, useRouter, useRoute } = VueRouter;

// ============================================================
// API 工具
// ============================================================
const api = {
  async _request(method, url, body) {
    const opts = {
      method,
      headers: { 'Content-Type': 'application/json' },
    };
    if (body !== undefined) opts.body = JSON.stringify(body);
    const res = await fetch(url, opts);
    const data = await res.json();
    if (!res.ok || !data.ok) {
      throw new Error(data.detail || data.error || `HTTP ${res.status}`);
    }
    return data;
  },
  get:    (url)        => api._request('GET', url),
  post:   (url, body)  => api._request('POST', url, body),
  delete: (url, body)  => api._request('DELETE', url, body),

  snapshots: {
    list:       (p=1,s=20,q='') => api.get(`/api/snapshots?page=${p}&size=${s}&q=${encodeURIComponent(q)}`),
    create:     (label)          => api.post('/api/snapshots', { label }),
    get:        (id,p=1,s=50,q='') => api.get(`/api/snapshots/${id}?page=${p}&size=${s}&q=${encodeURIComponent(q)}`),
    delete:     (id)             => api.delete(`/api/snapshots/${id}`),
    bulkDelete: (ids)            => api.delete('/api/snapshots', { ids }),
  },
  reports: {
    list:       (p=1,s=20,t='all') => api.get(`/api/reports?page=${p}&size=${s}&type=${t}`),
    content:    (name)              => api.get(`/api/reports/${encodeURIComponent(name)}/content`),
    generate:   (snap_a, snap_b)    => api.post('/api/reports/generate', { snap_a, snap_b }),
    generateAI: (name)              => api._request('POST', `/api/reports/${encodeURIComponent(name)}/ai`),
    aiTasks:    ()                  => api.get('/api/reports/ai-tasks'),
    delete:     (name)              => api.delete(`/api/reports/${encodeURIComponent(name)}`),
  },
  compare: {
    diff: (a, b) => api.get(`/api/compare/${a}/${b}`),
  },
  watch: {
    status: () => api.get('/api/watch/status'),
    start:  () => api.post('/api/watch/start'),
    stop:   () => api.post('/api/watch/stop'),
  },
  config: {
    get: () => api.get('/api/config'),
  },
  stats: {
    activity: (days=90) => api.get(`/api/stats/activity?days=${days}`),
  },
};

// ============================================================
// 全局 Toast 系统
// ============================================================
const toasts = ref([]);
let _toastId = 0;

function showToast(message, type = 'info', duration = 3000) {
  const id = ++_toastId;
  toasts.value.push({ id, message, type });
  setTimeout(() => {
    const idx = toasts.value.findIndex(t => t.id === id);
    if (idx !== -1) toasts.value.splice(idx, 1);
  }, duration);
}

function debounce(fn, delay = 300) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), delay); };
}

function fmtDate(ts) {
  if (!ts) return '-';
  return ts.replace('T', ' ').slice(0, 16);
}

// ============================================================
// ToastContainer 组件
// ============================================================
const ToastContainer = {
  template: `
    <div class="toast toast-top toast-end z-50" style="top:4.5rem">
      <transition-group name="slide">
        <div v-for="t in toasts" :key="t.id"
             :class="['alert shadow-md text-sm min-w-60',
                      t.type==='success'?'alert-success':
                      t.type==='error'?'alert-error':
                      t.type==='warning'?'alert-warning':'alert-info']">
          <span>{{ t.message }}</span>
        </div>
      </transition-group>
    </div>
  `,
  setup() { return { toasts }; },
};

// ============================================================
// Pagination 组件
// ============================================================
const Pagination = {
  props: { total: Number, page: Number, size: { type: Number, default: 20 } },
  emits: ['update:page'],
  setup(props, { emit }) {
    const totalPages = computed(() => Math.max(1, Math.ceil(props.total / props.size)));
    const pages = computed(() => {
      const cur = props.page, last = totalPages.value;
      const set = new Set([1, last, cur - 1, cur, cur + 1].filter(p => p >= 1 && p <= last));
      return [...set].sort((a, b) => a - b);
    });
    const go = (p) => { if (p >= 1 && p <= totalPages.value) emit('update:page', p); };
    return { totalPages, pages, go };
  },
  template: `
    <div v-if="totalPages > 1" class="flex items-center gap-1 flex-wrap">
      <button class="btn btn-xs btn-ghost" :disabled="page===1" @click="go(1)">«</button>
      <button class="btn btn-xs btn-ghost" :disabled="page===1" @click="go(page-1)">‹</button>
      <template v-for="p in pages" :key="p">
        <button :class="['btn btn-xs', p===page?'btn-primary':'btn-ghost']" @click="go(p)">{{ p }}</button>
      </template>
      <button class="btn btn-xs btn-ghost" :disabled="page===totalPages" @click="go(page+1)">›</button>
      <button class="btn btn-xs btn-ghost" :disabled="page===totalPages" @click="go(totalPages)">»</button>
      <span class="text-xs text-base-content/50 ml-1">共 {{ total }} 条</span>
    </div>
    <div v-else class="text-xs text-base-content/50">共 {{ total }} 条</div>
  `,
};

// ============================================================
// ConfirmModal 组件
// ============================================================
const ConfirmModal = {
  props: { title: String, message: String, confirmText: { type: String, default: '确认删除' } },
  emits: ['confirm', 'cancel'],
  template: `
    <div class="modal modal-open">
      <div class="modal-box max-w-sm">
        <h3 class="font-bold text-lg mb-2">{{ title }}</h3>
        <p class="text-sm text-base-content/70">{{ message }}</p>
        <div class="modal-action mt-4">
          <button class="btn btn-ghost btn-sm" @click="$emit('cancel')">取消</button>
          <button class="btn btn-error btn-sm" @click="$emit('confirm')">{{ confirmText }}</button>
        </div>
      </div>
      <div class="modal-backdrop bg-black/30" @click="$emit('cancel')"></div>
    </div>
  `,
};

// ============================================================
// SkeletonRows
// ============================================================
const SkeletonRows = {
  props: { cols: { type: Number, default: 4 }, rows: { type: Number, default: 5 } },
  template: `
    <tr v-for="r in rows" :key="r" class="skeleton-row">
      <td v-for="c in cols" :key="c"><div class="h-4 bg-base-300 rounded w-full"></div></td>
    </tr>
  `,
};

// ============================================================
// 仪表盘页
// ============================================================

// 本地日期格式化（避免 toISOString 的 UTC 时区偏移问题）
function toLocalDateStr(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

const PageDashboard = {
  components: { SkeletonRows },
  setup() {
    const router = useRouter();
    const stats = ref({ snapshots: 0, reports: 0, watch: false, config: null });
    const recentSnaps = ref([]);
    const recentReports = ref([]);
    const loading = ref(true);
    const snapLabel = ref('manual');
    const snapping = ref(false);

    // ECharts 实例
    let heatmapChart = null;
    let trendChart = null;

    async function load() {
      loading.value = true;
      try {
        const [snaps, rpts, cfg, ws] = await Promise.all([
          api.snapshots.list(1, 5),
          api.reports.list(1, 5),
          api.config.get(),
          api.watch.status(),
        ]);
        stats.value = {
          snapshots: snaps.total,
          reports: rpts.total,
          watch: ws.running,
          config: cfg,
        };
        recentSnaps.value = snaps.items;
        recentReports.value = rpts.items;
      } catch (e) {
        showToast('加载失败：' + e.message, 'error');
      } finally {
        loading.value = false;
      }
    }

    async function loadCharts() {
      if (typeof echarts === 'undefined') return;
      try {
        const data = await api.stats.activity(90);
        // 等待 DOM 布局完成，确保容器有实际宽度再 init
        await nextTick();
        await new Promise(r => setTimeout(r, 150));
        renderHeatmap(data.heatmap);
        renderTrend(data.trend);
      } catch (e) {
        console.warn('图表加载失败', e);
      }
    }

    function renderHeatmap(heatmapData) {
      const el = document.getElementById('chart-heatmap');
      if (!el) return;
      if (heatmapChart) heatmapChart.dispose();
      heatmapChart = echarts.init(el);

      // 空数据提示
      if (!heatmapData || heatmapData.length === 0) {
        heatmapChart.setOption({
          title: { text: '活动热力图', left: 'center', textStyle: { fontSize: 14, fontWeight: 600 } },
          graphic: { type: 'text', left: 'center', top: 'middle', style: { text: '暂无快照数据', fontSize: 14, fill: '#999' } },
        });
        return;
      }

      // 自适应日期范围：从第一条数据到今天，至少 14 天
      const now = new Date();
      const end = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      const dateDates = heatmapData.map(d => new Date(d.date + 'T00:00:00'));
      const earliest = new Date(Math.min(...dateDates));
      const minStart = new Date(end);
      minStart.setDate(minStart.getDate() - 13); // 至少显示 14 天
      const start = new Date(Math.min(earliest.getTime(), minStart.getTime()));
      // 对齐到周日（日历组件以周日为起点）
      start.setDate(start.getDate() - start.getDay());

      // 按日期索引
      const valueMap = {};
      for (const item of heatmapData) {
        valueMap[item.date] = item.count;
      }

      // 构建日历数据
      const calData = [];
      const d = new Date(start);
      while (d <= end) {
        const ds = toLocalDateStr(d);
        calData.push([ds, valueMap[ds] || 0]);
        d.setDate(d.getDate() + 1);
      }

      const maxVal = Math.max(1, ...calData.map(v => v[1]));
      const startStr = toLocalDateStr(start);
      const endStr = toLocalDateStr(end);

      // 根据周数动态计算 cellSize，适配容器宽度
      const weeks = Math.ceil((end - start) / (7 * 86400000)) + 1;
      const containerW = el.clientWidth || 400;
      const maxCellW = Math.floor((containerW - 70) / weeks);  // 70 = left + right margin
      const cellSize = Math.max(12, Math.min(22, maxCellW));

      heatmapChart.setOption({
        title: {
          text: '活动热力图',
          left: 'center',
          textStyle: { fontSize: 14, fontWeight: 600 },
        },
        tooltip: {
          formatter(params) {
            return `${params.value[0]}<br/>快照次数: <b>${params.value[1]}</b>`;
          },
        },
        visualMap: {
          min: 0,
          max: maxVal,
          type: 'piecewise',
          orient: 'horizontal',
          left: 'center',
          bottom: 0,
          pieces: [
            { min: 0, max: 0, label: '0', color: '#ebedf0' },
            { min: 1, max: Math.max(1, Math.floor(maxVal * 0.25)), label: '少', color: '#9be9a8' },
            { min: Math.floor(maxVal * 0.25) + 1, max: Math.max(2, Math.floor(maxVal * 0.5)), label: '中', color: '#40c463' },
            { min: Math.floor(maxVal * 0.5) + 1, max: Math.max(3, Math.floor(maxVal * 0.75)), label: '多', color: '#30a14e' },
            { min: Math.floor(maxVal * 0.75) + 1, max: maxVal, label: '高', color: '#216e39' },
          ],
        },
        calendar: {
          top: 50,
          left: 40,
          right: 20,
          cellSize: [cellSize, cellSize],
          range: [startStr, endStr],
          itemStyle: { borderWidth: 2, borderColor: '#fff' },
          splitLine: { show: false },
          yearLabel: { show: false },
          dayLabel: { nameMap: 'ZH', fontSize: 10 },
          monthLabel: { nameMap: 'ZH', fontSize: 10 },
        },
        series: [{
          type: 'heatmap',
          coordinateSystem: 'calendar',
          data: calData,
        }],
      });
      heatmapChart.resize();
    }

    function renderTrend(trendData) {
      const el = document.getElementById('chart-trend');
      if (!el) return;
      if (trendChart) trendChart.dispose();
      trendChart = echarts.init(el);

      // 空数据提示
      if (!trendData || trendData.length === 0) {
        trendChart.setOption({
          title: { text: '代码变更趋势', left: 'center', textStyle: { fontSize: 14, fontWeight: 600 } },
          graphic: { type: 'text', left: 'center', top: 'middle', style: { text: '暂无变更数据（需至少 2 个快照）', fontSize: 14, fill: '#999' } },
        });
        return;
      }

      const dates = trendData.map(d => d.date);
      const added = trendData.map(d => d.added);
      const removed = trendData.map(d => -d.removed);  // 负值
      const net = trendData.map(d => d.net);

      // 根据数据点数量动态调整柱宽
      const barWidth = dates.length <= 3 ? 40 : dates.length <= 7 ? 25 : undefined;

      trendChart.setOption({
        title: {
          text: '代码变更趋势',
          left: 'center',
          textStyle: { fontSize: 14, fontWeight: 600 },
        },
        tooltip: {
          trigger: 'axis',
          formatter(params) {
            let s = `<b>${params[0].axisValue}</b><br/>`;
            for (const p of params) {
              const v = Math.abs(p.value);
              s += `${p.marker} ${p.seriesName}: ${v} 行<br/>`;
            }
            return s;
          },
        },
        legend: { bottom: 0, data: ['新增行', '删除行', '净变更'] },
        grid: { top: 50, left: 55, right: 20, bottom: 40 },
        xAxis: {
          type: 'category',
          data: dates,
          axisLabel: { fontSize: 10, rotate: dates.length > 7 ? 30 : 0 },
        },
        yAxis: { type: 'value', axisLabel: { fontSize: 10 } },
        series: [
          {
            name: '新增行',
            type: 'bar',
            stack: 'changes',
            data: added,
            itemStyle: { color: '#40c463' },
            barMaxWidth: 50,
            ...(barWidth ? { barWidth } : {}),
          },
          {
            name: '删除行',
            type: 'bar',
            stack: 'changes',
            data: removed,
            itemStyle: { color: '#f85149' },
            barMaxWidth: 50,
            ...(barWidth ? { barWidth } : {}),
          },
          {
            name: '净变更',
            type: 'line',
            data: net,
            smooth: true,
            symbol: 'circle',
            symbolSize: 6,
            lineStyle: { color: '#58a6ff', width: 2 },
            itemStyle: { color: '#58a6ff' },
          },
        ],
      });
      trendChart.resize();
    }

    function handleResize() {
      if (heatmapChart) heatmapChart.resize();
      if (trendChart) trendChart.resize();
    }

    async function doSnapshot() {
      snapping.value = true;
      try {
        const snap = await api.snapshots.create(snapLabel.value || 'manual');
        showToast(`快照已生成：${snap.id}（${snap.file_count} 个文件）`, 'success');
        await load();
      } catch (e) {
        showToast('打快照失败：' + e.message, 'error');
      } finally {
        snapping.value = false;
      }
    }

    onMounted(async () => {
      await load();
      await loadCharts();
      window.addEventListener('resize', handleResize);
    });
    onUnmounted(() => {
      window.removeEventListener('resize', handleResize);
      if (heatmapChart) { heatmapChart.dispose(); heatmapChart = null; }
      if (trendChart) { trendChart.dispose(); trendChart = null; }
    });

    return { stats, recentSnaps, recentReports, loading, snapLabel, snapping, doSnapshot, fmtDate, router };
  },
  template: `
    <div class="space-y-6">
      <!-- 统计卡片 -->
      <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div class="card bg-base-100 shadow-sm border border-base-200 p-5">
          <div class="text-3xl font-bold text-primary">{{ stats.snapshots }}</div>
          <div class="text-sm text-base-content/60 mt-1">快照总数</div>
        </div>
        <div class="card bg-base-100 shadow-sm border border-base-200 p-5">
          <div class="text-3xl font-bold text-secondary">{{ stats.reports }}</div>
          <div class="text-sm text-base-content/60 mt-1">日报总数</div>
        </div>
        <div class="card bg-base-100 shadow-sm border border-base-200 p-5">
          <div class="text-3xl font-bold text-accent">{{ stats.config?.watch_paths?.length ?? 0 }}</div>
          <div class="text-sm text-base-content/60 mt-1">监控目录</div>
        </div>
        <div class="card bg-base-100 shadow-sm border border-base-200 p-5">
          <div class="text-xl font-bold mt-1" :class="stats.watch?'text-success':'text-base-content/40'">
            {{ stats.watch ? '● 运行中' : '○ 已停止' }}
          </div>
          <div class="text-sm text-base-content/60 mt-1">Watch 状态</div>
        </div>
      </div>

      <!-- 图表区域 -->
      <div class="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <div class="card bg-base-100 shadow-sm border border-base-200 p-4">
          <div id="chart-heatmap" style="width:100%;height:240px;"></div>
        </div>
        <div class="card bg-base-100 shadow-sm border border-base-200 p-4">
          <div id="chart-trend" style="width:100%;height:260px;"></div>
        </div>
      </div>

      <!-- 快速操作 -->
      <div class="card bg-base-100 shadow-sm border border-base-200 p-5">
        <h2 class="font-semibold text-base mb-3">快速打快照</h2>
        <div class="flex gap-2 flex-wrap">
          <input v-model="snapLabel" class="input input-bordered input-sm w-40" placeholder="标签（manual）" />
          <button class="btn btn-primary btn-sm" :class="snapping?'loading':''" @click="doSnapshot" :disabled="snapping">
            {{ snapping ? '快照生成中...' : '+ 打快照' }}
          </button>
        </div>
      </div>

      <!-- 最近快照 + 最近日报 -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div class="card bg-base-100 shadow-sm border border-base-200">
          <div class="p-4 border-b border-base-200 flex justify-between items-center">
            <h2 class="font-semibold">最近快照</h2>
            <router-link to="/snapshots" class="text-xs text-primary hover:underline">全部 →</router-link>
          </div>
          <div class="overflow-x-auto">
            <table class="table table-xs">
              <thead><tr><th>ID</th><th>时间</th><th>标签</th><th>文件数</th></tr></thead>
              <tbody>
                <skeleton-rows v-if="loading" :cols="4" :rows="4" />
                <tr v-else v-for="s in recentSnaps" :key="s.id" class="hover cursor-pointer" @click="router.push('/snapshots/'+s.id)">
                  <td class="font-mono text-xs">{{ s.id }}</td>
                  <td class="text-xs">{{ fmtDate(s.timestamp) }}</td>
                  <td><span class="badge badge-ghost badge-sm">{{ s.label }}</span></td>
                  <td class="text-right">{{ s.file_count }}</td>
                </tr>
                <tr v-if="!loading && !recentSnaps.length"><td colspan="4" class="text-center text-xs text-base-content/40 py-4">暂无快照</td></tr>
              </tbody>
            </table>
          </div>
        </div>

        <div class="card bg-base-100 shadow-sm border border-base-200">
          <div class="p-4 border-b border-base-200 flex justify-between items-center">
            <h2 class="font-semibold">最近日报</h2>
            <router-link to="/reports" class="text-xs text-primary hover:underline">全部 →</router-link>
          </div>
          <div class="overflow-x-auto">
            <table class="table table-xs">
              <thead><tr><th>文件名</th><th>时间</th><th>类型</th><th>大小</th></tr></thead>
              <tbody>
                <skeleton-rows v-if="loading" :cols="4" :rows="4" />
                <tr v-else v-for="r in recentReports" :key="r.filename" class="hover cursor-pointer" @click="router.push('/reports/'+r.filename)">
                  <td class="text-xs max-w-40 truncate">{{ r.filename }}</td>
                  <td class="text-xs">{{ r.mtime }}</td>
                  <td><span :class="['badge badge-sm', r.is_ai?'badge-primary':'badge-ghost']">{{ r.is_ai?'AI':'原始' }}</span></td>
                  <td class="text-right text-xs">{{ r.size_kb }} KB</td>
                </tr>
                <tr v-if="!loading && !recentReports.length"><td colspan="4" class="text-center text-xs text-base-content/40 py-4">暂无日报</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  `,
};

// ============================================================
// 快照列表页
// ============================================================
const PageSnapshots = {
  components: { Pagination, SkeletonRows, ConfirmModal },
  setup() {
    const router = useRouter();
    const items = ref([]);
    const total = ref(0);
    const page = ref(1);
    const size = 20;
    const q = ref('');
    const loading = ref(false);
    const selected = ref(new Set());
    const delTarget = ref(null);
    const snapping = ref(false);
    const snapLabel = ref('manual');

    async function load() {
      loading.value = true;
      try {
        const data = await api.snapshots.list(page.value, size, q.value);
        items.value = data.items;
        total.value = data.total;
      } catch (e) {
        showToast('加载失败：' + e.message, 'error');
      } finally {
        loading.value = false;
      }
    }

    const debouncedLoad = debounce(load);
    watch(q, () => { page.value = 1; debouncedLoad(); });
    watch(page, load);
    onMounted(load);

    const allSelected = computed(() =>
      items.value.length > 0 && items.value.every(s => selected.value.has(s.id))
    );

    function toggleAll() {
      if (allSelected.value) { selected.value = new Set(); }
      else { items.value.forEach(s => selected.value.add(s.id)); }
    }

    async function doSnapshot() {
      snapping.value = true;
      try {
        const snap = await api.snapshots.create(snapLabel.value || 'manual');
        showToast(`快照已生成：${snap.id}`, 'success');
        page.value = 1;
        await load();
      } catch (e) {
        showToast('打快照失败：' + e.message, 'error');
      } finally {
        snapping.value = false;
      }
    }

    async function confirmDelete() {
      const id = delTarget.value;
      delTarget.value = null;
      try {
        await api.snapshots.delete(id);
        showToast('已删除快照 ' + id, 'success');
        selected.value.delete(id);
        await load();
      } catch (e) {
        showToast('删除失败：' + e.message, 'error');
      }
    }

    async function bulkDelete() {
      const ids = [...selected.value];
      if (!ids.length) return;
      try {
        await api.snapshots.bulkDelete(ids);
        showToast(`已批量删除 ${ids.length} 个快照`, 'success');
        selected.value = new Set();
        page.value = 1;
        await load();
      } catch (e) {
        showToast('批量删除失败：' + e.message, 'error');
      }
    }

    const canGenReport = computed(() => selected.value.size === 2);

    async function generateFromSelected() {
      const ids = [...selected.value].sort();
      try {
        const r = await api.reports.generate(ids[0], ids[1]);
        showToast('日报已生成：' + r.filename, 'success');
        router.push('/reports/' + r.filename);
      } catch (e) {
        showToast('生成日报失败：' + e.message, 'error');
      }
    }

    return { items, total, page, size, q, loading, selected, allSelected, toggleAll,
             delTarget, snapping, snapLabel, doSnapshot, confirmDelete, bulkDelete,
             canGenReport, generateFromSelected, fmtDate, router };
  },
  template: `
    <div class="space-y-4">
      <confirm-modal v-if="delTarget" title="确认删除快照"
        :message="'将永久删除快照 ' + delTarget + '，此操作不可撤销。'"
        @confirm="confirmDelete" @cancel="delTarget=null" />

      <!-- 操作栏 -->
      <div class="card bg-base-100 shadow-sm border border-base-200 p-4">
        <div class="flex flex-wrap gap-2 items-center justify-between">
          <div class="flex gap-2 items-center flex-wrap">
            <input v-model="q" class="input input-bordered input-sm w-48" placeholder="🔍 搜索 ID / 标签…" />
            <input v-model="snapLabel" class="input input-bordered input-sm w-32" placeholder="标签" />
            <button class="btn btn-primary btn-sm" :class="snapping?'loading':''" @click="doSnapshot" :disabled="snapping">
              {{ snapping ? '生成中…' : '+ 打快照' }}
            </button>
          </div>
          <div class="flex gap-2">
            <button v-if="canGenReport" class="btn btn-primary btn-sm" @click="generateFromSelected">
              📄 生成日报
            </button>
            <button v-if="selected.size>0" class="btn btn-error btn-sm" @click="bulkDelete">
              批量删除 ({{ selected.size }})
            </button>
          </div>
        </div>
      </div>

      <!-- 表格 -->
      <div class="card bg-base-100 shadow-sm border border-base-200">
        <div class="overflow-x-auto">
          <table class="table table-sm">
            <thead>
              <tr class="text-xs text-base-content/50 uppercase">
                <th><input type="checkbox" class="checkbox checkbox-xs" :checked="allSelected" @change="toggleAll" /></th>
                <th>ID</th><th>时间</th><th>标签</th><th>触发</th><th class="text-right">文件数</th><th></th>
              </tr>
            </thead>
            <tbody>
              <skeleton-rows v-if="loading" :cols="7" />
              <tr v-else v-for="s in items" :key="s.id" class="hover">
                <td><input type="checkbox" class="checkbox checkbox-xs"
                    :checked="selected.has(s.id)"
                    @change="selected.has(s.id)?selected.delete(s.id):selected.add(s.id)" /></td>
                <td class="font-mono text-xs">{{ s.id }}</td>
                <td class="text-xs">{{ fmtDate(s.timestamp) }}</td>
                <td><span class="badge badge-ghost badge-sm">{{ s.label }}</span></td>
                <td class="text-xs text-base-content/50">{{ s.trigger }}</td>
                <td class="text-right text-sm">{{ s.file_count }}</td>
                <td>
                  <div class="flex gap-1 justify-end">
                    <button class="btn btn-ghost btn-xs" @click="router.push('/snapshots/'+s.id)">查看</button>
                    <router-link :to="'/compare?a='+s.id" class="btn btn-ghost btn-xs">对比</router-link>
                    <button class="btn btn-ghost btn-xs text-error" @click="delTarget=s.id">删除</button>
                  </div>
                </td>
              </tr>
              <tr v-if="!loading && !items.length">
                <td colspan="7" class="text-center py-10 text-base-content/40">暂无快照，请先通过「打快照」创建</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="p-4 border-t border-base-200">
          <pagination :total="total" v-model:page="page" :size="size" />
        </div>
      </div>
    </div>
  `,
};

// ============================================================
// 快照详情页
// ============================================================
const PageSnapshotDetail = {
  components: { Pagination, SkeletonRows },
  setup() {
    const route = useRoute();
    const router = useRouter();
    const snap = ref(null);
    const files = ref({ total: 0, items: [] });
    const page = ref(1);
    const size = 50;
    const q = ref('');
    const loading = ref(false);

    async function load() {
      loading.value = true;
      try {
        const data = await api.snapshots.get(route.params.id, page.value, size, q.value);
        snap.value = data;
        files.value = data.files;
      } catch (e) {
        showToast('加载失败：' + e.message, 'error');
      } finally {
        loading.value = false;
      }
    }

    const debouncedLoad = debounce(load);
    watch(q, () => { page.value = 1; debouncedLoad(); });
    watch(page, load);
    onMounted(load);

    return { snap, files, page, size, q, loading, fmtDate, router, route };
  },
  template: `
    <div class="space-y-4">
      <div class="flex items-center gap-2">
        <button class="btn btn-ghost btn-sm" @click="router.back()">← 返回</button>
        <h1 class="font-bold text-lg font-mono">{{ route.params.id }}</h1>
      </div>

      <!-- 元数据卡片 -->
      <div v-if="snap" class="card bg-base-100 shadow-sm border border-base-200 p-5">
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div><span class="text-base-content/50">时间</span><br/><b>{{ fmtDate(snap.timestamp) }}</b></div>
          <div><span class="text-base-content/50">标签</span><br/><span class="badge badge-ghost">{{ snap.label }}</span></div>
          <div><span class="text-base-content/50">触发</span><br/><b>{{ snap.trigger }}</b></div>
          <div><span class="text-base-content/50">文件总数</span><br/><b>{{ snap.file_count }}</b></div>
        </div>
        <div class="mt-4 flex gap-2">
          <router-link :to="'/compare?a='+snap.id" class="btn btn-outline btn-sm">🔍 用此快照对比</router-link>
        </div>
      </div>

      <!-- 文件列表 -->
      <div class="card bg-base-100 shadow-sm border border-base-200">
        <div class="p-4 border-b border-base-200 flex gap-2 items-center justify-between">
          <h2 class="font-semibold">文件列表</h2>
          <input v-model="q" class="input input-bordered input-sm w-56" placeholder="🔍 搜索文件路径…" />
        </div>
        <div class="overflow-x-auto">
          <table class="table table-xs">
            <thead><tr class="text-xs text-base-content/50 uppercase">
              <th>文件路径</th><th>哈希</th><th class="text-right">行数</th>
            </tr></thead>
            <tbody>
              <skeleton-rows v-if="loading" :cols="3" />
              <tr v-else v-for="f in files.items" :key="f.path" class="hover">
                <td class="font-mono text-xs break-all">{{ f.path }}</td>
                <td class="font-mono text-xs text-base-content/40">{{ f.hash }}</td>
                <td class="text-right text-xs">{{ f.lines !== null ? f.lines : '大文件' }}</td>
              </tr>
              <tr v-if="!loading && !files.items.length">
                <td colspan="3" class="text-center py-8 text-base-content/40">无匹配文件</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="p-4 border-t border-base-200">
          <pagination :total="files.total" v-model:page="page" :size="size" />
        </div>
      </div>
    </div>
  `,
};

// ============================================================
// 日报列表页
// ============================================================
const PageReports = {
  components: { Pagination, SkeletonRows, ConfirmModal },
  setup() {
    const router = useRouter();
    const items = ref([]);
    const total = ref(0);
    const page = ref(1);
    const size = 20;
    const typeFilter = ref('all');
    const loading = ref(false);
    const delTarget = ref(null);
    const aiTasks = ref({});  // key=name, value=task object
    let _pollTimer = null;

    async function load() {
      loading.value = true;
      try {
        const data = await api.reports.list(page.value, size, typeFilter.value);
        items.value = data.items;
        total.value = data.total;
      } catch (e) {
        showToast('加载失败：' + e.message, 'error');
      } finally {
        loading.value = false;
      }
    }

    async function pollAiTasks() {
      try {
        const data = await api.reports.aiTasks();
        const prev = { ...aiTasks.value };
        const map = {};
        let hasRunning = false;
        for (const t of data.tasks) {
          map[t.name] = t;
          if (t.status === 'running') hasRunning = true;
        }
        aiTasks.value = map;
        // 检查是否有任务刚完成
        for (const t of data.tasks) {
          const old = prev[t.name];
          if (old && old.status === 'running' && t.status === 'done') {
            showToast('AI 日报已生成：' + t.filename, 'success');
            typeFilter.value = 'all';
            page.value = 1;
            await load();
          } else if (old && old.status === 'running' && t.status === 'error') {
            showToast('AI 生成失败：' + t.error, 'error');
          }
        }
        // 没有运行中的任务时停止轮询
        if (!hasRunning && _pollTimer) {
          clearInterval(_pollTimer);
          _pollTimer = null;
        }
      } catch (_) {}
    }

    function _ensurePolling() {
      if (!_pollTimer) {
        _pollTimer = setInterval(pollAiTasks, 3000);
      }
    }

    watch(typeFilter, () => { page.value = 1; load(); });
    watch(page, load);
    onMounted(async () => {
      await load();
      // 首次检查是否有运行中的任务，有则启动轮询
      await pollAiTasks();
      const hasRunning = Object.values(aiTasks.value).some(t => t.status === 'running');
      if (hasRunning) _ensurePolling();
    });
    onUnmounted(() => { if (_pollTimer) clearInterval(_pollTimer); });

    async function confirmDelete() {
      const name = delTarget.value;
      delTarget.value = null;
      try {
        await api.reports.delete(name);
        showToast('已删除 ' + name, 'success');
        await load();
      } catch (e) {
        showToast('删除失败：' + e.message, 'error');
      }
    }

    async function genAI(name) {
      try {
        await api.reports.generateAI(name);
        showToast('AI 生成任务已提交，后台处理中…', 'info', 5000);
        await pollAiTasks();
        _ensurePolling();  // 提交任务后启动轮询
      } catch (e) {
        showToast('AI 生成失败：' + e.message, 'error');
      }
    }

    function aiTaskStatus(name) {
      return aiTasks.value[name] || null;
    }

    return { items, total, page, size, typeFilter, loading, delTarget, confirmDelete, genAI, aiTaskStatus, router };
  },
  template: `
    <div class="space-y-4">
      <confirm-modal v-if="delTarget" title="确认删除日报"
        :message="'将永久删除 ' + delTarget"
        @confirm="confirmDelete" @cancel="delTarget=null" />

      <div class="card bg-base-100 shadow-sm border border-base-200 p-4">
        <div class="flex gap-2">
          <div class="join">
            <button v-for="t in [{v:'all',l:'全部'},{v:'ai',l:'AI'},{v:'raw',l:'原始'}]" :key="t.v"
              :class="['btn btn-sm join-item', typeFilter===t.v?'btn-primary':'btn-ghost']"
              @click="typeFilter=t.v">{{ t.l }}</button>
          </div>
        </div>
      </div>

      <div class="card bg-base-100 shadow-sm border border-base-200">
        <div class="overflow-x-auto">
          <table class="table table-sm">
            <thead><tr class="text-xs text-base-content/50 uppercase">
              <th>类型</th><th>文件名</th><th>生成时间</th><th>起点快照</th><th>终点快照</th><th class="text-right">大小</th><th></th>
            </tr></thead>
            <tbody>
              <skeleton-rows v-if="loading" :cols="7" />
              <tr v-else v-for="r in items" :key="r.filename" class="hover">
                <td><span :class="['badge badge-sm', r.is_ai?'badge-primary':'badge-ghost']">{{ r.is_ai?'AI':'原始' }}</span></td>
                <td class="text-xs font-mono max-w-xs truncate">{{ r.filename }}</td>
                <td class="text-xs">{{ r.mtime }}</td>
                <td class="text-xs font-mono text-base-content/50">{{ r.snap_a }}</td>
                <td class="text-xs font-mono text-base-content/50">{{ r.snap_b }}</td>
                <td class="text-right text-xs">{{ r.size_kb }} KB</td>
                <td>
                  <div class="flex gap-1 justify-end items-center">
                    <span v-if="!r.is_ai && aiTaskStatus(r.filename)?.status==='running'"
                          class="badge badge-warning badge-sm gap-1 animate-pulse">
                      ⏳ AI生成中… ({{ aiTaskStatus(r.filename).elapsed_sec }}s)
                    </span>
                    <span v-else-if="!r.is_ai && aiTaskStatus(r.filename)?.status==='error'"
                          class="badge badge-error badge-sm" :title="aiTaskStatus(r.filename).error">
                      ✗ 生成失败
                    </span>
                    <button class="btn btn-ghost btn-xs" @click="router.push('/reports/'+r.filename)">预览</button>
                    <button v-if="!r.is_ai && (!aiTaskStatus(r.filename) || aiTaskStatus(r.filename).status!=='running')"
                            class="btn btn-ghost btn-xs text-primary" @click="genAI(r.filename)">AI</button>
                    <button class="btn btn-ghost btn-xs text-error" @click="delTarget=r.filename">删除</button>
                  </div>
                </td>
              </tr>
              <tr v-if="!loading && !items.length">
                <td colspan="7" class="text-center py-10 text-base-content/40">暂无日报记录</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="p-4 border-t border-base-200">
          <pagination :total="total" v-model:page="page" :size="size" />
        </div>
      </div>
    </div>
  `,
};

// ============================================================
// 日报预览页
// ============================================================
const PageReportView = {
  setup() {
    const route = useRoute();
    const router = useRouter();
    const content = ref('');
    const rendered = ref('');
    const loading = ref(false);
    const headings = ref([]);
    const currentAnchor = ref('');

    async function load() {
      loading.value = true;
      try {
        const data = await api.reports.content(route.params.name);
        content.value = data.content;
        rendered.value = marked.parse(data.content);
        await nextTick();
        try { if (typeof hljs !== 'undefined') hljs.highlightAll(); } catch(_) {}
        // 提取目录
        const matches = [...data.content.matchAll(/^(#{1,3})\s+(.+)$/gm)];
        headings.value = matches.map(m => ({
          level: m[1].length,
          text: m[2],
          id: m[2].replace(/[^\w\u4e00-\u9fa5]/g, '-').toLowerCase(),
        }));
      } catch (e) {
        showToast('加载失败：' + e.message, 'error');
      } finally {
        loading.value = false;
      }
    }

    async function genAI() {
      try {
        await api.reports.generateAI(route.params.name);
        showToast('AI 生成任务已提交，请到日报管理页查看进度', 'info', 5000);
        router.push('/reports');
      } catch (e) {
        showToast('AI 生成失败：' + e.message, 'error');
      }
    }

    function download() {
      const blob = new Blob([content.value], { type: 'text/markdown;charset=utf-8' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = route.params.name;
      a.click();
    }

    onMounted(load);
    // 路由参数变化时重新加载（如从原始日报跳转到 AI 日报）
    watch(() => route.params.name, (newName, oldName) => {
      if (newName && newName !== oldName) load();
    });
    const isAI = computed(() => route.params.name.endsWith('-ai.md'));

    return { content, rendered, loading, headings, currentAnchor, genAI, download, isAI, router, route };
  },
  template: `
    <div class="space-y-4">
      <div class="flex flex-wrap items-center gap-2 justify-between">
        <div class="flex items-center gap-2">
          <button class="btn btn-ghost btn-sm" @click="router.back()">← 返回</button>
          <span :class="['badge', isAI?'badge-primary':'badge-ghost']">{{ isAI?'AI日报':'原始日报' }}</span>
          <span class="text-sm font-mono text-base-content/60 hidden md:inline">{{ route.params.name }}</span>
        </div>
        <div class="flex gap-2">
          <button v-if="!isAI" class="btn btn-outline btn-sm" @click="genAI">✨ 生成AI版</button>
          <button class="btn btn-ghost btn-sm" @click="download">⬇ 下载</button>
        </div>
      </div>

      <div v-if="loading" class="card bg-base-100 p-8 text-center text-base-content/40">加载中…</div>
      <div v-else class="flex gap-4">
        <!-- 目录 -->
        <div v-if="headings.length" class="hidden xl:block w-48 shrink-0">
          <div class="card bg-base-100 shadow-sm border border-base-200 p-4 sticky top-20">
            <h3 class="text-xs font-semibold text-base-content/50 uppercase mb-2">目录</h3>
            <nav class="space-y-1 text-sm">
              <a v-for="h in headings" :key="h.id" :href="'#'+h.id"
                 :class="['block hover:text-primary', h.level===1?'font-semibold':h.level===2?'pl-2':'pl-4 text-xs text-base-content/60']">
                {{ h.text }}
              </a>
            </nav>
          </div>
        </div>
        <!-- 内容 -->
        <div class="flex-1 card bg-base-100 shadow-sm border border-base-200 p-6 min-w-0">
          <div class="prose max-w-none" v-html="rendered"></div>
        </div>
      </div>
    </div>
  `,
};

// ============================================================
// 对比页
// ============================================================
const PageCompare = {
  components: { SkeletonRows },
  setup() {
    const route = useRoute();
    const router = useRouter();
    const snapshots = ref([]);
    const snapA = ref(route.query.a || '');
    const snapB = ref(route.query.b || '');
    const result = ref(null);
    const loading = ref(false);

    async function loadSnapshots() {
      try {
        const data = await api.snapshots.list(1, 200);
        snapshots.value = data.items;
        if (!snapA.value && data.items.length >= 2) {
          snapA.value = data.items[1].id;
          snapB.value = data.items[0].id;
        }
      } catch (e) {
        showToast('加载快照列表失败：' + e.message, 'error');
      }
    }

    async function compare() {
      if (!snapA.value || !snapB.value) return;
      loading.value = true;
      result.value = null;
      try {
        result.value = await api.compare.diff(snapA.value, snapB.value);
      } catch (e) {
        showToast('对比失败：' + e.message, 'error');
      } finally {
        loading.value = false;
      }
    }

    async function generateReport() {
      if (!result.value) return;
      try {
        const r = await api.reports.generate(result.value.snap_a.id, result.value.snap_b.id);
        showToast('日报已生成：' + r.filename, 'success');
        router.push('/reports/' + r.filename);
      } catch (e) {
        showToast('生成日报失败：' + e.message, 'error');
      }
    }

    const statusColor = { created: 'text-success', modified: 'text-warning', deleted: 'text-error' };
    const statusLabel = { created: '新增', modified: '修改', deleted: '删除' };

    onMounted(async () => { await loadSnapshots(); if (snapA.value && snapB.value) await compare(); });

    return { snapshots, snapA, snapB, result, loading, compare, generateReport, fmtDate, statusColor, statusLabel };
  },
  template: `
    <div class="space-y-4">
      <!-- 选择区 -->
      <div class="card bg-base-100 shadow-sm border border-base-200 p-5">
        <h2 class="font-semibold mb-3">选择对比快照</h2>
        <div class="flex flex-wrap gap-3 items-end">
          <div>
            <label class="text-xs text-base-content/50 block mb-1">起点快照 A</label>
            <select v-model="snapA" class="select select-bordered select-sm w-56">
              <option value="">请选择…</option>
              <option v-for="s in snapshots" :key="s.id" :value="s.id">{{ s.id }} ({{ s.label }})</option>
            </select>
          </div>
          <div>
            <label class="text-xs text-base-content/50 block mb-1">终点快照 B</label>
            <select v-model="snapB" class="select select-bordered select-sm w-56">
              <option value="">请选择…</option>
              <option v-for="s in snapshots" :key="s.id" :value="s.id">{{ s.id }} ({{ s.label }})</option>
            </select>
          </div>
          <button class="btn btn-primary btn-sm" @click="compare" :disabled="!snapA||!snapB||loading">
            {{ loading ? '对比中…' : '开始对比' }}
          </button>
        </div>
      </div>

      <!-- 结果 -->
      <div v-if="result">
        <!-- 摘要卡片 -->
        <div class="grid grid-cols-3 md:grid-cols-7 gap-3 mb-4">
          <div class="card bg-base-100 border border-base-200 p-3 text-center">
            <div class="text-2xl font-bold">{{ result.summary.total }}</div>
            <div class="text-xs text-base-content/50">变更总数</div>
          </div>
          <div class="card bg-base-100 border border-success/30 p-3 text-center">
            <div class="text-2xl font-bold text-success">{{ result.summary.created }}</div>
            <div class="text-xs text-base-content/50">新增</div>
          </div>
          <div class="card bg-base-100 border border-warning/30 p-3 text-center">
            <div class="text-2xl font-bold text-warning">{{ result.summary.modified }}</div>
            <div class="text-xs text-base-content/50">修改</div>
          </div>
          <div class="card bg-base-100 border border-error/30 p-3 text-center">
            <div class="text-2xl font-bold text-error">{{ result.summary.deleted }}</div>
            <div class="text-xs text-base-content/50">删除</div>
          </div>
          <div class="card bg-base-100 border border-base-200 p-3 text-center">
            <div class="text-2xl font-bold text-success">+{{ result.summary.total_add }}</div>
            <div class="text-xs text-base-content/50">新增行</div>
          </div>
          <div class="card bg-base-100 border border-base-200 p-3 text-center">
            <div class="text-2xl font-bold text-error">-{{ result.summary.total_remove }}</div>
            <div class="text-xs text-base-content/50">删除行</div>
          </div>
          <div class="card bg-base-100 border border-base-200 p-3 text-center">
            <div class="text-2xl font-bold" :class="result.summary.net>=0?'text-success':'text-error'">
              {{ result.summary.net > 0 ? '+' : '' }}{{ result.summary.net }}
            </div>
            <div class="text-xs text-base-content/50">净变化</div>
          </div>
        </div>

        <!-- 生成日报 -->
        <div class="flex justify-end mb-3">
          <button class="btn btn-primary btn-sm" @click="generateReport">📄 生成日报</button>
        </div>

        <!-- 变更明细 -->
        <div class="card bg-base-100 shadow-sm border border-base-200">
          <div class="overflow-x-auto">
            <table class="table table-sm">
              <thead><tr class="text-xs text-base-content/50 uppercase">
                <th>状态</th><th>文件路径</th><th class="text-right">+行</th><th class="text-right">-行</th>
              </tr></thead>
              <tbody>
                <tr v-for="d in result.diffs" :key="d.path" class="hover">
                  <td><span :class="['text-xs font-semibold', statusColor[d.status]]">{{ statusLabel[d.status] }}</span></td>
                  <td class="font-mono text-xs break-all">{{ d.path }}</td>
                  <td class="text-right text-xs text-success">+{{ d.added_lines }}</td>
                  <td class="text-right text-xs text-error">-{{ d.removed_lines }}</td>
                </tr>
                <tr v-if="!result.diffs.length">
                  <td colspan="4" class="text-center py-8 text-base-content/40">两快照之间无文件变更</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  `,
};

// ============================================================
// Watch 页
// ============================================================
const PageWatch = {
  setup() {
    const status = ref({ running: false, auto_snapshot_times: [], recent_log: [] });
    const logs = ref([]);
    const loading = ref(false);
    let es = null;
    const logEl = ref(null);

    async function loadStatus() {
      loading.value = true;
      try {
        const data = await api.watch.status();
        status.value = data;
        logs.value = data.recent_log || [];
      } catch (e) {
        showToast('加载失败：' + e.message, 'error');
      } finally {
        loading.value = false;
      }
    }

    async function toggleWatch() {
      try {
        if (status.value.running) {
          await api.watch.stop();
          showToast('Watch 停止信号已发送', 'info');
        } else {
          await api.watch.start();
          showToast('Watch 已启动', 'success');
        }
        await loadStatus();
      } catch (e) {
        showToast('操作失败：' + e.message, 'error');
      }
    }

    function connectSSE() {
      if (es) return;
      es = new EventSource('/api/watch/stream');
      ['snapshot', 'log', 'error'].forEach(evt => {
        es.addEventListener(evt, (e) => {
          try {
            const data = JSON.parse(e.data);
            logs.value.push({ ...data });
            if (logs.value.length > 200) logs.value.shift();
            nextTick(() => {
              if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight;
            });
          } catch(_) {}
        });
      });
    }

    function disconnectSSE() {
      if (es) { es.close(); es = null; }
    }

    onMounted(async () => { await loadStatus(); connectSSE(); });
    onUnmounted(disconnectSSE);

    const eventColor = { snapshot: 'text-success', log: 'text-base-content', error: 'text-error' };

    return { status, logs, loading, logEl, toggleWatch, eventColor };
  },
  template: `
    <div class="space-y-4">
      <!-- 状态卡片 -->
      <div class="card bg-base-100 shadow-sm border border-base-200 p-5">
        <div class="flex items-center justify-between flex-wrap gap-3">
          <div>
            <div class="flex items-center gap-2 mb-1">
              <span class="inline-block w-2.5 h-2.5 rounded-full" :class="status.running?'bg-success':'bg-base-300'"></span>
              <span class="font-semibold text-lg">Watch {{ status.running ? '运行中' : '已停止' }}</span>
            </div>
            <div class="text-sm text-base-content/50">
              自动快照时间：{{ status.auto_snapshot_times.join('、') || '未配置' }}
            </div>
          </div>
          <button :class="['btn btn-sm', status.running?'btn-error':'btn-success']" @click="toggleWatch">
            {{ status.running ? '停止 Watch' : '启动 Watch' }}
          </button>
        </div>
      </div>

      <!-- 实时日志 -->
      <div class="card bg-base-100 shadow-sm border border-base-200">
        <div class="p-4 border-b border-base-200">
          <h2 class="font-semibold">实时日志 <span class="text-xs text-base-content/40 ml-1">（SSE 推送，自动滚动）</span></h2>
        </div>
        <div ref="logEl" class="log-scroll bg-base-200 rounded-b-xl p-4 font-mono text-xs space-y-1">
          <div v-if="!logs.length" class="text-base-content/40">暂无日志…</div>
          <div v-for="(l, i) in logs" :key="i" :class="['flex gap-2', eventColor[l.event]||'']">
            <span class="text-base-content/40 shrink-0">{{ l.time }}</span>
            <span class="font-semibold shrink-0">[{{ l.event }}]</span>
            <span>{{ l.message || (l.id ? '快照 '+l.id+' 已生成，'+l.file_count+' 个文件' : JSON.stringify(l)) }}</span>
          </div>
        </div>
      </div>
    </div>
  `,
};

// ============================================================
// 设置页
// ============================================================
const PageSettings = {
  setup() {
    const cfg = ref(null);
    const loading = ref(false);

    async function load() {
      loading.value = true;
      try { cfg.value = await api.config.get(); }
      catch (e) { showToast('加载配置失败：' + e.message, 'error'); }
      finally { loading.value = false; }
    }

    onMounted(load);
    return { cfg, loading };
  },
  template: `
    <div class="space-y-4">
      <div v-if="loading" class="card bg-base-100 p-8 text-center text-base-content/40">加载中…</div>
      <template v-else-if="cfg">
        <!-- 监控目录 -->
        <div class="card bg-base-100 shadow-sm border border-base-200 p-5">
          <h2 class="font-semibold mb-3">监控目录</h2>
          <div v-for="p in cfg.watch_paths" :key="p" class="font-mono text-sm bg-base-200 rounded px-3 py-1.5 mb-1">{{ p }}</div>
        </div>
        <!-- 存储设置 -->
        <div class="card bg-base-100 shadow-sm border border-base-200 p-5">
          <h2 class="font-semibold mb-3">存储设置</h2>
          <table class="table table-xs">
            <tbody>
              <tr><td class="text-base-content/50 w-40">snapshot_root</td><td class="font-mono">{{ cfg.snapshot_root }}</td></tr>
              <tr><td class="text-base-content/50">output_root</td><td class="font-mono">{{ cfg.output_root }}</td></tr>
              <tr><td class="text-base-content/50">encoding</td><td>{{ cfg.encoding }}</td></tr>
              <tr><td class="text-base-content/50">max_file_size_kb</td><td>{{ cfg.max_file_size_kb }}</td></tr>
            </tbody>
          </table>
        </div>
        <!-- AI 配置 -->
        <div class="card bg-base-100 shadow-sm border border-base-200 p-5">
          <h2 class="font-semibold mb-3">AI 配置</h2>
          <table class="table table-xs">
            <tbody>
              <tr><td class="text-base-content/50 w-40">ai_provider</td><td>{{ cfg.ai_provider }}</td></tr>
              <tr><td class="text-base-content/50">ai_model</td><td>{{ cfg.ai_model || '（默认）' }}</td></tr>
              <tr><td class="text-base-content/50">ai_api_key</td><td>{{ cfg.ai_api_key || '（未配置）' }}</td></tr>
              <tr><td class="text-base-content/50">ai_base_url</td><td class="font-mono text-xs">{{ cfg.ai_base_url || '（默认）' }}</td></tr>
            </tbody>
          </table>
        </div>
        <!-- 自动快照时间 -->
        <div class="card bg-base-100 shadow-sm border border-base-200 p-5">
          <h2 class="font-semibold mb-3">自动快照时间</h2>
          <div v-if="cfg.auto_snapshot_times.length" class="flex gap-2 flex-wrap">
            <span v-for="t in cfg.auto_snapshot_times" :key="t" class="badge badge-outline">{{ t }}</span>
          </div>
          <div v-else class="text-sm text-base-content/40">未配置</div>
        </div>
        <!-- 忽略规则 -->
        <div class="card bg-base-100 shadow-sm border border-base-200 p-5">
          <h2 class="font-semibold mb-3">忽略规则</h2>
          <div class="grid md:grid-cols-3 gap-4 text-sm">
            <div>
              <div class="text-xs text-base-content/50 mb-1">ignore_dirs</div>
              <div v-for="d in cfg.ignore_dirs" :key="d" class="font-mono bg-base-200 rounded px-2 py-0.5 mb-1 text-xs">{{ d }}</div>
            </div>
            <div>
              <div class="text-xs text-base-content/50 mb-1">ignore_suffixes</div>
              <div v-for="s in cfg.ignore_suffixes" :key="s" class="font-mono bg-base-200 rounded px-2 py-0.5 mb-1 text-xs">{{ s }}</div>
            </div>
            <div>
              <div class="text-xs text-base-content/50 mb-1">ignore_patterns</div>
              <div v-for="p in cfg.ignore_patterns" :key="p" class="font-mono bg-base-200 rounded px-2 py-0.5 mb-1 text-xs">{{ p }}</div>
            </div>
          </div>
        </div>
      </template>
    </div>
  `,
};

// ============================================================
// AppLayout (侧栏 + 顶栏)
// ============================================================
const AppLayout = {
  components: { RouterLink, RouterView, ToastContainer, ConfirmModal },
  setup() {
    const sidebarOpen = ref(true);
    const darkMode = ref(localStorage.getItem('theme') === 'dark');

    function toggleTheme() {
      darkMode.value = !darkMode.value;
      const t = darkMode.value ? 'dark' : 'light';
      document.documentElement.setAttribute('data-theme', t);
      localStorage.setItem('theme', t);
    }

    onMounted(() => {
      const saved = localStorage.getItem('theme');
      if (saved) { document.documentElement.setAttribute('data-theme', saved); darkMode.value = saved === 'dark'; }
      nextTick(() => { if (window.lucide) lucide.createIcons(); });
    });

    const nav = [
      { to: '/dashboard', icon: 'layout-dashboard', label: '仪表盘' },
      { to: '/snapshots',  icon: 'camera',           label: '快照管理' },
      { to: '/reports',    icon: 'file-text',         label: '日报管理' },
      { to: '/compare',    icon: 'git-compare',       label: '对比分析' },
      { to: '/watch',      icon: 'timer',             label: 'Watch' },
      { to: '/settings',   icon: 'settings',          label: '设置' },
    ];

    return { sidebarOpen, darkMode, toggleTheme, nav };
  },
  template: `
    <div class="flex h-screen overflow-hidden bg-base-200">
      <!-- 侧栏 -->
      <aside :class="['bg-base-100 border-r border-base-200 flex flex-col shrink-0 transition-all duration-200',
                       sidebarOpen ? 'w-56' : 'w-14']">
        <!-- Logo -->
        <div class="h-16 flex items-center gap-2 px-3 border-b border-base-200">
          <button class="btn btn-ghost btn-sm btn-square" @click="sidebarOpen=!sidebarOpen">
            <i data-lucide="menu" class="w-4 h-4"></i>
          </button>
          <span v-if="sidebarOpen" class="font-bold text-primary text-sm">Kgent V3</span>
        </div>
        <!-- 导航 -->
        <nav class="flex-1 p-2 space-y-0.5 overflow-y-auto">
          <router-link v-for="item in nav" :key="item.to" :to="item.to"
            :class="['sidebar-link flex items-center gap-2.5 px-2 py-2 rounded-lg text-sm transition-colors hover:bg-base-200']">
            <i :data-lucide="item.icon" class="w-4 h-4 shrink-0"></i>
            <span v-if="sidebarOpen">{{ item.label }}</span>
          </router-link>
        </nav>
      </aside>

      <!-- 主区域 -->
      <div class="flex-1 flex flex-col overflow-hidden">
        <!-- 顶栏 -->
        <header class="h-16 bg-base-100 border-b border-base-200 flex items-center justify-between px-4 shrink-0">
          <div class="text-sm text-base-content/50 hidden sm:block">文件变更监控 · AI 日报生成</div>
          <button class="btn btn-ghost btn-sm btn-square" @click="toggleTheme" :title="darkMode?'切换亮色':'切换暗色'">
            <i :data-lucide="darkMode?'sun':'moon'" class="w-4 h-4"></i>
          </button>
        </header>
        <!-- 内容区 -->
        <main class="flex-1 overflow-y-auto p-4 md:p-6">
          <router-view />
        </main>
      </div>

      <!-- Toast 容器 -->
      <toast-container />
    </div>
  `,
};

// ============================================================
// 路由
// ============================================================
const routes = [
  { path: '/',              redirect: '/dashboard' },
  { path: '/dashboard',     component: PageDashboard },
  { path: '/snapshots',     component: PageSnapshots },
  { path: '/snapshots/:id', component: PageSnapshotDetail },
  { path: '/reports',       component: PageReports },
  { path: '/reports/:name', component: PageReportView },
  { path: '/compare',       component: PageCompare },
  { path: '/watch',         component: PageWatch },
  { path: '/settings',      component: PageSettings },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
});

// 路由变更后重新初始化 Lucide 图标
router.afterEach(() => {
  nextTick(() => { if (window.lucide) lucide.createIcons(); });
});

// ============================================================
// 挂载
// ============================================================
const app = createApp(AppLayout);
app.use(router);
app.component('ToastContainer', ToastContainer);
app.component('Pagination', Pagination);
app.component('ConfirmModal', ConfirmModal);
app.component('SkeletonRows', SkeletonRows);
app.mount('#app');
