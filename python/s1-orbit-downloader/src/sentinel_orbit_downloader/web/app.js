const DEFAULT_CATALOG_PATH = "\u5168\u56fd\u884c\u653f\u533a.geojson";
const FINAL_STATUSES = new Set(["succeeded", "failed", "partial_failed", "canceled"]);

const api = {
  async request(path, options = {}) {
    const init = { ...options };
    init.headers = {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.headers || {}),
    };
    const response = await fetch(path, init);
    if (!response.ok) {
      let detail = response.statusText;
      try {
        const payload = await response.json();
        detail = payload.detail || JSON.stringify(payload);
      } catch (_) {}
      throw new Error(detail);
    }
    if (response.status === 204) {
      return null;
    }
    return response.json();
  },
  health() {
    return this.request("/api/health");
  },
  earthdataSettings() {
    return this.request("/api/settings/earthdata");
  },
  saveEarthdataSettings(payload) {
    return this.request("/api/settings/earthdata", {
      method: "PUT",
      body: JSON.stringify(payload),
    });
  },
  clearEarthdataSettings() {
    return this.request("/api/settings/earthdata", {
      method: "DELETE",
    });
  },
  importRegions(payload) {
    return this.request("/api/regions/import", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  searchRegions(query) {
    return this.request(`/api/regions/search?q=${encodeURIComponent(query)}`);
  },
  regionDetail(adcode) {
    return this.request(`/api/regions/${encodeURIComponent(adcode)}`);
  },
  projects() {
    return this.request("/api/projects");
  },
  createProject(payload) {
    return this.request("/api/projects", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  jobs(projectId) {
    const suffix = projectId ? `?project_id=${projectId}&limit=50` : "?limit=50";
    return this.request(`/api/jobs${suffix}`);
  },
  job(jobId) {
    return this.request(`/api/jobs/${jobId}?include_events=true`);
  },
  createSearchJob(payload) {
    return this.request("/api/search-jobs", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  createDownloadJob(payload) {
    return this.request("/api/download-jobs", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  deleteJob(jobId, force = false) {
    return this.request(`/api/jobs/${jobId}?force=${force ? "true" : "false"}`, {
      method: "DELETE",
    });
  },
  clearJobs(projectId, force = false) {
    const projectPart = projectId ? `project_id=${projectId}&` : "";
    return this.request(`/api/jobs?${projectPart}force=${force ? "true" : "false"}`, {
      method: "DELETE",
    });
  },
};

const state = {
  projects: [],
  selectedProjectId: null,
  regions: [],
  selectedRegion: null,
  selectedRegionDetail: null,
  earthdataSettings: null,
  jobs: [],
  selectedJobId: null,
  selectedJobDetail: null,
  pollTimer: null,
};

const el = {
  healthDot: document.getElementById("healthDot"),
  healthLabel: document.getElementById("healthLabel"),
  healthDetail: document.getElementById("healthDetail"),
  catalogPath: document.getElementById("catalogPath"),
  simplifyTolerance: document.getElementById("simplifyTolerance"),
  projectName: document.getElementById("projectName"),
  projectPath: document.getElementById("projectPath"),
  projectDesc: document.getElementById("projectDesc"),
  projectList: document.getElementById("projectList"),
  messageBar: document.getElementById("messageBar"),
  regionKeyword: document.getElementById("regionKeyword"),
  regionList: document.getElementById("regionList"),
  regionDetailCard: document.getElementById("regionDetailCard"),
  startDate: document.getElementById("startDate"),
  endDate: document.getElementById("endDate"),
  maxResults: document.getElementById("maxResults"),
  processingLevel: document.getElementById("processingLevel"),
  beamMode: document.getElementById("beamMode"),
  flightDirection: document.getElementById("flightDirection"),
  polarization: document.getElementById("polarization"),
  relativeOrbit: document.getElementById("relativeOrbit"),
  manifestPath: document.getElementById("manifestPath"),
  rawRegion: document.getElementById("rawRegion"),
  selectionSummary: document.getElementById("selectionSummary"),
  dataDir: document.getElementById("dataDir"),
  orbitDir: document.getElementById("orbitDir"),
  skipData: document.getElementById("skipData"),
  skipOrbits: document.getElementById("skipOrbits"),
  downloadProcesses: document.getElementById("downloadProcesses"),
  ignoreOrbitErrors: document.getElementById("ignoreOrbitErrors"),
  earthdataUser: document.getElementById("earthdataUser"),
  earthdataPass: document.getElementById("earthdataPass"),
  earthdataSummary: document.getElementById("earthdataSummary"),
  jobFilterSummary: document.getElementById("jobFilterSummary"),
  jobList: document.getElementById("jobList"),
  deleteJobBtn: document.getElementById("deleteJobBtn"),
  clearJobsBtn: document.getElementById("clearJobsBtn"),
  jobMeta: document.getElementById("jobMeta"),
  sceneTableBody: document.getElementById("sceneTableBody"),
  eventList: document.getElementById("eventList"),
};

function setMessage(text, tone = "info") {
  el.messageBar.textContent = text;
  el.messageBar.className = `message ${tone}`;
}

function setHealth(ok, label, detail) {
  el.healthDot.className = `status-dot ${ok ? "ok" : "error"}`;
  el.healthLabel.textContent = label;
  el.healthDetail.textContent = detail;
}

function makeChip(text) {
  const span = document.createElement("span");
  span.className = "chip";
  span.textContent = text;
  return span;
}

function makeStatusPill(value) {
  const span = document.createElement("span");
  span.className = `status-pill ${value || ""}`.trim();
  span.textContent = value || "-";
  return span;
}

function renderEmpty(container, text) {
  container.innerHTML = `<div class="empty">${escapeHtml(text)}</div>`;
}

function formatMb(value) {
  if (value == null || Number.isNaN(Number(value))) {
    return "";
  }
  return `${Number(value).toFixed(1)} MB`;
}

function formatRelativeOrbit(value) {
  return value == null ? "" : String(value);
}

function formatBBox(bbox) {
  if (!Array.isArray(bbox) || bbox.length !== 4) {
    return "-";
  }
  return bbox.map((value) => Number(value).toFixed(4)).join(", ");
}

function formatPoint(point) {
  if (!Array.isArray(point) || point.length < 2) {
    return "-";
  }
  return point.slice(0, 2).map((value) => Number(value).toFixed(4)).join(", ");
}

function emptyToNull(value) {
  const text = (value || "").trim();
  return text ? text : null;
}

function numberOrNull(value) {
  const text = (value || "").trim();
  if (!text) {
    return null;
  }
  const number = Number(text);
  return Number.isFinite(number) ? number : null;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text || "";
  return div.innerHTML;
}

function statusCounts(scenes) {
  const product = {};
  const orbit = {};
  for (const scene of scenes) {
    product[scene.product_status] = (product[scene.product_status] || 0) + 1;
    orbit[scene.orbit_status] = (orbit[scene.orbit_status] || 0) + 1;
  }
  return { product, orbit };
}

function currentProject() {
  return state.projects.find((project) => project.id === state.selectedProjectId) || null;
}

function autoFillProjectPaths(project) {
  if (!project || !project.data_root) {
    return;
  }
  el.projectPath.value = project.data_root;
  el.dataDir.value = `${project.data_root}\\data`;
  el.orbitDir.value = `${project.data_root}\\orbits`;
  if (!el.manifestPath.value) {
    el.manifestPath.value = `${project.data_root}\\manifest.csv`;
  }
}

function renderProjects() {
  el.projectList.innerHTML = "";
  if (!state.projects.length) {
    renderEmpty(el.projectList, "暂无项目");
    return;
  }

  for (const project of state.projects) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `item ${state.selectedProjectId === project.id ? "active" : ""}`;
    button.innerHTML = `
      <div class="item-title">${escapeHtml(project.name)}</div>
      <div class="item-subtle mono">${escapeHtml(project.data_root)}</div>
      <div class="item-subtle">${escapeHtml(project.slug)}</div>
    `;
    button.addEventListener("click", async () => {
      state.selectedProjectId = project.id;
      autoFillProjectPaths(project);
      renderProjects();
      updateSelectionSummary();
      await loadJobs();
      await loadSelectedJobDetail();
    });
    el.projectList.appendChild(button);
  }
}

function renderRegions() {
  el.regionList.innerHTML = "";
  if (!state.regions.length) {
    renderEmpty(el.regionList, "暂无行政区结果");
    return;
  }

  for (const region of state.regions) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `item ${state.selectedRegion && state.selectedRegion.adcode === region.adcode ? "active" : ""}`;
    button.innerHTML = `
      <div class="item-title">${escapeHtml(region.label)}</div>
      <div class="item-subtle mono">${escapeHtml(region.adcode)}</div>
      <div class="item-subtle">${escapeHtml(region.level)} | ${escapeHtml(formatBBox(region.bbox))}</div>
    `;
    button.addEventListener("click", async () => {
      state.selectedRegion = region;
      renderRegions();
      updateSelectionSummary();
      await loadRegionDetail(region.adcode);
    });
    el.regionList.appendChild(button);
  }
}

function renderRegionDetail() {
  const region = state.selectedRegionDetail;
  if (!region) {
    el.regionDetailCard.innerHTML = '<div class="empty">未选择行政区</div>';
    return;
  }

  el.regionDetailCard.innerHTML = `
    <div class="stack">
      <div class="chip-row">
        <span class="status-pill succeeded">${escapeHtml(region.level)}</span>
        <span class="chip mono">${escapeHtml(region.adcode)}</span>
      </div>
      <div class="detail-grid">
        <div class="detail-row">
          <div class="detail-label">行政区</div>
          <div class="detail-value">${escapeHtml(region.label)}</div>
        </div>
        <div class="detail-row">
          <div class="detail-label">简化容差</div>
          <div class="detail-value">${escapeHtml(String(region.simplify_tolerance))}</div>
        </div>
        <div class="detail-row">
          <div class="detail-label">范围框</div>
          <div class="detail-value mono">${escapeHtml(formatBBox(region.bbox))}</div>
        </div>
        <div class="detail-row">
          <div class="detail-label">中心点</div>
          <div class="detail-value mono">${escapeHtml(formatPoint(region.center))}</div>
        </div>
      </div>
    </div>
  `;
}

function renderEarthdataSummary() {
  el.earthdataSummary.innerHTML = "";
  const settings = state.earthdataSettings;
  if (!settings || (!settings.username && !settings.has_password)) {
    el.earthdataSummary.appendChild(makeChip("Earthdata 本地凭据：未保存"));
    return;
  }
  if (settings.username) {
    el.earthdataSummary.appendChild(makeChip(`Earthdata 用户：${settings.username}`));
  }
  el.earthdataSummary.appendChild(
    makeChip(settings.has_password ? "Earthdata 密码：已保存" : "Earthdata 密码：未保存"),
  );
}

function renderJobFilterSummary() {
  el.jobFilterSummary.innerHTML = "";
  const project = currentProject();
  if (project) {
    el.jobFilterSummary.appendChild(makeChip(`项目 ${project.name}`));
  } else {
    el.jobFilterSummary.appendChild(makeChip("全部项目"));
  }
  el.jobFilterSummary.appendChild(makeChip(`任务数 ${state.jobs.length}`));
}

function renderJobs() {
  el.jobList.innerHTML = "";
  if (!state.jobs.length) {
    renderEmpty(el.jobList, "暂无任务");
    renderJobFilterSummary();
    return;
  }

  for (const job of state.jobs) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `item ${state.selectedJobId === job.id ? "active" : ""}`;
    button.appendChild(makeStatusPill(job.status));

    const title = document.createElement("div");
    title.className = "item-title";
    title.textContent = `#${job.id} ${job.region_name || job.source_value || job.source_type}`;
    button.appendChild(title);

    const subtles = [
      `${job.start_time} - ${job.end_time}`,
      `${job.processing_level}${job.beam_mode ? ` | ${job.beam_mode}` : ""}`,
      `结果 ${job.result_count ?? "-"}`,
    ];
    for (const text of subtles) {
      const div = document.createElement("div");
      div.className = "item-subtle";
      div.textContent = text;
      button.appendChild(div);
    }

    button.addEventListener("click", async () => {
      state.selectedJobId = job.id;
      renderJobs();
      updateSelectionSummary();
      await loadSelectedJobDetail();
    });
    el.jobList.appendChild(button);
  }

  renderJobFilterSummary();
}

function renderJobDetail() {
  const payload = state.selectedJobDetail;
  el.jobMeta.innerHTML = "";
  el.sceneTableBody.innerHTML = "";
  el.eventList.innerHTML = "";

  if (!payload) {
    renderEmpty(el.jobMeta, "未选择任务");
    el.sceneTableBody.innerHTML = '<tr><td colspan="7" class="empty">暂无场景</td></tr>';
    renderEmpty(el.eventList, "暂无事件");
    return;
  }

  const { job, scenes, events } = payload;
  const counts = statusCounts(scenes);
  const chips = [
    `Job #${job.id}`,
    `状态 ${job.status}`,
    `时间 ${job.start_time} - ${job.end_time}`,
    `产品 ${job.processing_level}`,
    `结果 ${job.result_count ?? scenes.length}`,
  ];

  if (job.region_name) {
    chips.push(`区域 ${job.region_name}`);
  }
  if (job.data_dir) {
    chips.push(`数据目录 ${job.data_dir}`);
  }
  if (job.orbit_dir) {
    chips.push(`轨道目录 ${job.orbit_dir}`);
  }
  if (job.error_message) {
    chips.push(`错误 ${job.error_message}`);
  }

  for (const text of chips) {
    el.jobMeta.appendChild(makeChip(text));
  }
  for (const [status, count] of Object.entries(counts.product)) {
    el.jobMeta.appendChild(makeChip(`产品 ${status} ${count}`));
  }
  for (const [status, count] of Object.entries(counts.orbit)) {
    el.jobMeta.appendChild(makeChip(`轨道 ${status} ${count}`));
  }

  if (!scenes.length) {
    el.sceneTableBody.innerHTML = '<tr><td colspan="7" class="empty">暂无场景</td></tr>';
  } else {
    for (const scene of scenes) {
      const row = document.createElement("tr");

      const sceneCell = document.createElement("td");
      sceneCell.className = "mono";
      sceneCell.textContent = scene.scene_id;
      row.appendChild(sceneCell);

      const startCell = document.createElement("td");
      startCell.textContent = scene.start_time || "";
      row.appendChild(startCell);

      const levelCell = document.createElement("td");
      levelCell.textContent = scene.processing_level || "";
      row.appendChild(levelCell);

      const orbitCell = document.createElement("td");
      orbitCell.textContent = formatRelativeOrbit(scene.relative_orbit);
      row.appendChild(orbitCell);

      const productCell = document.createElement("td");
      productCell.appendChild(makeStatusPill(scene.product_status));
      row.appendChild(productCell);

      const eofCell = document.createElement("td");
      eofCell.appendChild(makeStatusPill(scene.orbit_status));
      row.appendChild(eofCell);

      const sizeCell = document.createElement("td");
      sizeCell.textContent = formatMb(scene.size_mb);
      row.appendChild(sizeCell);

      el.sceneTableBody.appendChild(row);
    }
  }

  if (!events.length) {
    renderEmpty(el.eventList, "暂无事件");
  } else {
    for (const event of events) {
      const div = document.createElement("div");
      div.className = "event";
      div.innerHTML = `
        <div class="event-title">${escapeHtml(event.level)}</div>
        <div class="event-meta">${escapeHtml(event.created_at)}</div>
        <div class="event-message">${escapeHtml(event.message)}</div>
      `;
      el.eventList.appendChild(div);
    }
  }

  syncPolling();
}

function updateSelectionSummary() {
  el.selectionSummary.innerHTML = "";
  const project = currentProject();
  if (project) {
    el.selectionSummary.appendChild(makeChip(`项目 ${project.name}`));
  }
  if (state.selectedRegion) {
    el.selectionSummary.appendChild(makeChip(`行政区 ${state.selectedRegion.label}`));
  }
  el.selectionSummary.appendChild(makeChip(`时间 ${el.startDate.value} - ${el.endDate.value}`));
  el.selectionSummary.appendChild(makeChip(`产品 ${el.processingLevel.value}`));
  if (el.beamMode.value) {
    el.selectionSummary.appendChild(makeChip(`波束 ${el.beamMode.value}`));
  }
  if (state.selectedJobId) {
    el.selectionSummary.appendChild(makeChip(`当前任务 #${state.selectedJobId}`));
  }
}

async function loadHealth() {
  try {
    const health = await api.health();
    setHealth(true, "服务已连接", health.db_path);
  } catch (error) {
    setHealth(false, "服务不可用", error.message || String(error));
    throw error;
  }
}

async function loadEarthdataSettings() {
  state.earthdataSettings = await api.earthdataSettings();
  if (state.earthdataSettings && state.earthdataSettings.username && !el.earthdataUser.value) {
    el.earthdataUser.value = state.earthdataSettings.username;
  }
  renderEarthdataSummary();
}

async function loadProjects() {
  state.projects = await api.projects();
  if (!state.selectedProjectId && state.projects.length) {
    state.selectedProjectId = state.projects[0].id;
    autoFillProjectPaths(state.projects[0]);
  } else {
    const project = currentProject();
    if (project) {
      autoFillProjectPaths(project);
    }
  }
  renderProjects();
  updateSelectionSummary();
}

async function loadRegions() {
  const keyword = el.regionKeyword.value.trim();
  if (!keyword) {
    state.regions = [];
    state.selectedRegion = null;
    state.selectedRegionDetail = null;
    renderRegions();
    renderRegionDetail();
    updateSelectionSummary();
    return;
  }

  state.regions = await api.searchRegions(keyword);
  state.selectedRegion = state.regions[0] || null;
  renderRegions();
  if (state.selectedRegion) {
    await loadRegionDetail(state.selectedRegion.adcode);
  } else {
    state.selectedRegionDetail = null;
    renderRegionDetail();
  }
  updateSelectionSummary();
}

async function loadRegionDetail(adcode) {
  state.selectedRegionDetail = await api.regionDetail(adcode);
  renderRegionDetail();
}

async function loadJobs() {
  state.jobs = await api.jobs(state.selectedProjectId);
  if (state.selectedJobId && !state.jobs.some((job) => job.id === state.selectedJobId)) {
    state.selectedJobId = null;
    state.selectedJobDetail = null;
  }
  renderJobs();
  updateSelectionSummary();
}

async function loadSelectedJobDetail() {
  if (!state.selectedJobId) {
    state.selectedJobDetail = null;
    renderJobDetail();
    return;
  }
  state.selectedJobDetail = await api.job(state.selectedJobId);
  const updatedJob = state.selectedJobDetail.job;
  state.jobs = state.jobs.map((job) => (job.id === updatedJob.id ? updatedJob : job));
  renderJobs();
  renderJobDetail();
  updateSelectionSummary();
}

async function importCatalog() {
  const payload = {
    source_path: el.catalogPath.value.trim() || DEFAULT_CATALOG_PATH,
    simplify_tolerance: Number(el.simplifyTolerance.value || 0.01),
  };
  const result = await api.importRegions(payload);
  setMessage(`行政区已导入：${result.imported}/${result.total_features}`, "success");
  await loadRegions();
}

async function saveEarthdataSettings() {
  const username = el.earthdataUser.value.trim();
  const password = el.earthdataPass.value;
  if (!username || !password) {
    throw new Error("保存 Earthdata 凭据时必须填写用户名和密码");
  }
  const response = await api.saveEarthdataSettings({ username, password });
  state.earthdataSettings = response;
  el.earthdataPass.value = "";
  renderEarthdataSummary();
  setMessage("Earthdata 凭据已保存到本地配置", "success");
}

async function clearEarthdataSettings() {
  if (!window.confirm("确定清除本地保存的 Earthdata 用户名和密码吗？")) {
    return;
  }
  await api.clearEarthdataSettings();
  state.earthdataSettings = { username: null, has_password: false };
  el.earthdataUser.value = "";
  el.earthdataPass.value = "";
  renderEarthdataSummary();
  setMessage("Earthdata 本地凭据已清除", "success");
}

async function createProject() {
  const payload = {
    name: el.projectName.value.trim(),
    data_root: el.projectPath.value.trim(),
    description: emptyToNull(el.projectDesc.value),
  };
  if (!payload.name || !payload.data_root) {
    throw new Error("项目名称和数据根目录不能为空");
  }
  const project = await api.createProject(payload);
  state.selectedProjectId = project.id;
  setMessage(`项目已创建：${project.name}`, "success");
  await loadProjects();
  await loadJobs();
}

async function createSearchJob() {
  if (!state.selectedProjectId) {
    throw new Error("请先选择项目");
  }
  if (!state.selectedRegion) {
    throw new Error("请先选择行政区");
  }

  const payload = {
    project_id: state.selectedProjectId,
    region_adcode: state.selectedRegion.adcode,
    start: el.startDate.value,
    end: el.endDate.value,
    processing_level: el.processingLevel.value,
    beam_mode: emptyToNull(el.beamMode.value),
    flight_direction: emptyToNull(el.flightDirection.value),
    polarization: emptyToNull(el.polarization.value),
    relative_orbit: numberOrNull(el.relativeOrbit.value),
    max_results: Number(el.maxResults.value || 20),
    manifest_path: emptyToNull(el.manifestPath.value),
    raw_region: el.rawRegion.checked,
  };

  const response = await api.createSearchJob(payload);
  state.selectedJobId = response.job.id;
  state.selectedJobDetail = {
    job: response.job,
    scenes: response.scenes,
    events: [],
  };
  setMessage(`检索完成：job #${response.job.id}，场景 ${response.scenes.length}`, "success");
  await loadJobs();
  await loadSelectedJobDetail();
}

async function queueDownloadJob() {
  if (!state.selectedJobId) {
    throw new Error("请先选择任务");
  }

  const payload = {
    job_id: state.selectedJobId,
    data_dir: emptyToNull(el.dataDir.value),
    orbit_dir: emptyToNull(el.orbitDir.value),
    skip_data: el.skipData.value === "true",
    skip_orbits: el.skipOrbits.value === "true",
    processes: Number(el.downloadProcesses.value || 2),
    ignore_orbit_errors: el.ignoreOrbitErrors.checked,
    username: emptyToNull(el.earthdataUser.value),
    password: emptyToNull(el.earthdataPass.value),
  };

  const response = await api.createDownloadJob(payload);
  setMessage(`下载任务已排队：job #${response.job.id}`, "success");
  await loadSelectedJobDetail();
}

async function deleteSelectedJob() {
  if (!state.selectedJobId) {
    throw new Error("请先选择任务");
  }

  const selectedJob =
    (state.selectedJobDetail && state.selectedJobDetail.job) ||
    state.jobs.find((job) => job.id === state.selectedJobId) ||
    null;
  const isRunning = Boolean(selectedJob && selectedJob.status === "running");
  const message = isRunning
    ? "当前任务仍显示为运行中。强制删除只会清理记录，不能保证后台下载立刻停止。确定继续删除吗？"
    : `确定删除任务 #${state.selectedJobId} 吗？`;

  if (!window.confirm(message)) {
    return;
  }

  const deletedJobId = state.selectedJobId;
  const response = await api.deleteJob(deletedJobId, isRunning);
  state.selectedJobId = null;
  state.selectedJobDetail = null;
  state.jobs = state.jobs.filter((job) => job.id !== deletedJobId);
  renderJobs();
  renderJobDetail();
  updateSelectionSummary();
  setMessage(`已删除 ${response.deleted_count} 个任务`, "success");
}

async function clearCurrentJobs() {
  if (!state.selectedProjectId) {
    throw new Error("请先选择项目");
  }

  const project = currentProject();
  const projectName = project ? project.name : `#${state.selectedProjectId}`;
  if (!window.confirm(`确定清空项目“${projectName}”下的非运行任务吗？`)) {
    return;
  }

  const response = await api.clearJobs(state.selectedProjectId, false);
  const deletedIds = new Set(response.deleted_job_ids || []);
  if (state.selectedJobId && deletedIds.has(state.selectedJobId)) {
    state.selectedJobId = null;
    state.selectedJobDetail = null;
  }
  state.jobs = state.jobs.filter((job) => !deletedIds.has(job.id));
  renderJobs();
  renderJobDetail();
  updateSelectionSummary();
  setMessage(`已清空 ${response.deleted_count} 个任务`, "success");
}

function stopPolling() {
  if (state.pollTimer) {
    window.clearInterval(state.pollTimer);
    state.pollTimer = null;
  }
}

function syncPolling() {
  const activeJob = state.selectedJobDetail && state.selectedJobDetail.job;
  if (!activeJob || FINAL_STATUSES.has(activeJob.status)) {
    stopPolling();
    return;
  }
  if (state.pollTimer) {
    return;
  }
  state.pollTimer = window.setInterval(async () => {
    if (!state.selectedJobId) {
      stopPolling();
      return;
    }
    try {
      await loadSelectedJobDetail();
    } catch (_) {}
  }, 5000);
}

function runAction(fn, pendingText) {
  return async () => {
    try {
      if (pendingText) {
        setMessage(pendingText, "info");
      }
      await fn();
    } catch (error) {
      setMessage(error.message || String(error), "error");
    }
  };
}

function bindEvents() {
  document.getElementById("saveEarthdataBtn").addEventListener("click", runAction(saveEarthdataSettings, "正在保存 Earthdata 凭据"));
  document.getElementById("clearEarthdataBtn").addEventListener("click", runAction(clearEarthdataSettings, "正在清除 Earthdata 凭据"));
  document.getElementById("importCatalogBtn").addEventListener("click", runAction(importCatalog, "正在导入行政区"));
  document.getElementById("createProjectBtn").addEventListener("click", runAction(createProject, "正在创建项目"));
  document.getElementById("refreshProjectsBtn").addEventListener("click", runAction(loadProjects, "正在刷新项目"));
  document.getElementById("searchRegionsBtn").addEventListener("click", runAction(loadRegions, "正在查询行政区"));
  document.getElementById("clearRegionsBtn").addEventListener("click", () => {
    state.regions = [];
    state.selectedRegion = null;
    state.selectedRegionDetail = null;
    el.regionKeyword.value = "";
    renderRegions();
    renderRegionDetail();
    updateSelectionSummary();
    setMessage("行政区查询已清空", "info");
  });
  document.getElementById("runSearchBtn").addEventListener("click", runAction(createSearchJob, "正在检索 Sentinel-1"));
  document.getElementById("queueDownloadBtn").addEventListener("click", runAction(queueDownloadJob, "正在排队下载任务"));
  document.getElementById("deleteJobBtn").addEventListener("click", runAction(deleteSelectedJob, "正在删除任务"));
  document.getElementById("clearJobsBtn").addEventListener("click", runAction(clearCurrentJobs, "正在清空任务"));
  document.getElementById("refreshJobsBtn").addEventListener("click", runAction(async () => {
    await loadJobs();
    await loadSelectedJobDetail();
  }, "正在刷新任务"));
  document.getElementById("refreshDetailBtn").addEventListener("click", runAction(loadSelectedJobDetail, "正在刷新任务详情"));
}

async function bootstrap() {
  bindEvents();
  if (!el.catalogPath.value) {
    el.catalogPath.value = DEFAULT_CATALOG_PATH;
  }
  el.healthDetail.textContent = window.location.origin;
  setMessage("正在初始化工作台", "info");
  await loadHealth();
  await loadEarthdataSettings();
  await loadProjects();
  await loadRegions();
  await loadJobs();
  await loadSelectedJobDetail();
  setMessage("工作台已就绪", "success");
}

bootstrap().catch((error) => {
  setMessage(error.message || String(error), "error");
});
