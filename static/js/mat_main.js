/**
 * mat_main.js — 多智能体教学地图：表单提交、SSE、进度、历史、文字视图、日志
 */

var AGENT_STEPS = [
    "learning_analysis",
    "teaching_logic_design",
    "main_question_chain",
    "cognitive_check",
    "goal_check",
    "teaching_logic_check",
    "aggregate_main_checks",
    "fan_out_gen",
    "variant_question",
    "scaffold_question",
    "variant_check",
    "scaffold_check",
    "aggregate_sub_pipelines",
    "map_integration",
];

var AGENT_TRACKER_STEPS = [
    "learning_analysis",
    "teaching_logic_design",
    "main_question_chain",
    "cognitive_check",
    "goal_check",
    "teaching_logic_check",
    "variant_question",
    "variant_check",
    "scaffold_question",
    "scaffold_check",
    "map_integration",
];

var AGENT_DISPLAY_NAMES = {
    learning_analysis: "学情与目标解析",
    teaching_logic_design: "教学蓝图规划",
    main_question_chain: "主干问题链构建",
    cognitive_check: "认知对齐检验",
    goal_check: "教学目标对齐检验",
    teaching_logic_check: "教学逻辑检验",
    variant_question: "变式问题生成",
    variant_check: "变式问题检验",
    scaffold_question: "支架问题生成",
    scaffold_check: "支架问题检验",
    map_integration: "教学地图整合",
};

var COGNITIVE_LABELS = {
    remember: "记忆", understand: "理解", apply: "应用",
    analyze: "分析", evaluate: "评价", create: "创造",
};

var currentTaskId = null;
var eventSource = null;
var currentResult = null;
var isGenerating = false;
var currentStepIndex = -1;
var ACTIVE_TASK_STORAGE_KEY = "teaching_map_active_task_id";

var API_PREFIX = "/api/mat";

// ---------------------------------------------------------------------------
// Left panel tabs
// ---------------------------------------------------------------------------
document.querySelectorAll(".mat-left-tab").forEach(function (btn) {
    btn.addEventListener("click", function () {
        document.querySelectorAll(".mat-left-tab").forEach(function (b) { b.classList.remove("active"); });
        document.querySelectorAll(".mat-left-tab-content").forEach(function (c) { c.classList.remove("active"); });
        this.classList.add("active");
        document.getElementById(this.dataset.target).classList.add("active");
        if (this.dataset.target === "historyTab") {
            loadHistory();
            if (isGenerating) {
                document.getElementById("generatingBanner").style.display = "flex";
            }
        }
    });
});

// ---------------------------------------------------------------------------
// View mode tabs (graph / text / logs)
// ---------------------------------------------------------------------------
document.querySelectorAll(".mat-view-tab").forEach(function (btn) {
    btn.addEventListener("click", function () {
        document.querySelectorAll(".mat-view-tab").forEach(function (b) { b.classList.remove("active"); });
        this.classList.add("active");
        var mode = this.dataset.view;
        document.getElementById("graphSection").style.display = mode === "graph" ? "block" : "none";
        document.getElementById("textSection").style.display = mode === "text" ? "block" : "none";
        document.getElementById("logsSection").style.display = mode === "logs" ? "block" : "none";
        if (mode !== "graph") {
            document.getElementById("detailSection").style.display = "none";
        }
        if (mode === "graph" && typeof chartInstance !== "undefined" && chartInstance) {
            chartInstance.resize();
        }
        if (mode === "logs" && currentTaskId) {
            loadAgentLogs(currentTaskId);
        }
    });
});

// ---------------------------------------------------------------------------
// Form submission
// ---------------------------------------------------------------------------
document.getElementById("generateForm").addEventListener("submit", function (e) {
    e.preventDefault();
    startGeneration();
});

document.getElementById("newPlanBtn").addEventListener("click", function () {
    startNewPlan();
});

function startGeneration() {
    var form = document.getElementById("generateForm");
    var formData = new FormData(form);
    var submitBtn = document.getElementById("submitBtn");

    submitBtn.disabled = true;
    submitBtn.textContent = "生成中...";
    document.getElementById("newPlanBtn").style.display = "none";
    isGenerating = true;

    document.getElementById("placeholder").style.display = "none";
    document.getElementById("progressSection").style.display = "block";
    document.getElementById("viewTabs").style.display = "none";
    document.getElementById("graphSection").style.display = "none";
    document.getElementById("textSection").style.display = "none";
    document.getElementById("logsSection").style.display = "none";
    document.getElementById("detailSection").style.display = "none";
    document.getElementById("progressLog").innerHTML = "";
    document.getElementById("progressBar").style.width = "0%";
    document.getElementById("generatingBanner").style.display = "none";
    document.getElementById("generatingBannerText").textContent = "正在生成教学地图...";
    initProgressTracker();
    updateCurrentAgentCard({
        step_number: 0,
        agent_display_name: "流程初始化",
        message: "已提交任务，正在排队执行。",
        input_preview: null,
        output_preview: { status: "waiting" },
    });
    currentStepIndex = -1;
    currentResult = null;

    fetch(API_PREFIX + "/generate", { method: "POST", body: formData })
        .then(function (res) { return res.json(); })
        .then(function (data) {
            currentTaskId = data.task_id;
            localStorage.setItem(ACTIVE_TASK_STORAGE_KEY, currentTaskId);
            connectSSE(currentTaskId);
        })
        .catch(function (err) {
            addLogEntry("连接失败: " + err.message, "error");
            submitBtn.disabled = false;
            submitBtn.textContent = "开始生成教学地图";
            isGenerating = false;
            localStorage.removeItem(ACTIVE_TASK_STORAGE_KEY);
            updateCurrentAgentCard({
                agent_display_name: "连接异常",
                message: "任务创建失败，请稍后重试。",
                output_preview: { error: err.message },
            });
        });
}

// ---------------------------------------------------------------------------
// SSE streaming
// ---------------------------------------------------------------------------
function connectSSE(taskId, fromIndex) {
    if (eventSource) eventSource.close();
    var start = typeof fromIndex === "number" && fromIndex >= 0 ? fromIndex : 0;
    eventSource = new EventSource(API_PREFIX + "/stream/" + taskId + "?from=" + start);
    var maxStepReached = -1;

    eventSource.onmessage = function (event) {
        var data = JSON.parse(event.data);

        if (data.type === "progress") {
            addLogEntry(data.message, "active");
            var stepIdx = AGENT_STEPS.indexOf(data.agent);
            if (stepIdx > maxStepReached) {
                maxStepReached = stepIdx;
            }
            updateProgressBar(maxStepReached, data.agent);
            updateStepTracker(maxStepReached);
            updateCurrentAgentCard(data);
        } else if (data.type === "done") {
            addLogEntry("教学地图生成完成！", "done");
            document.getElementById("progressBar").style.width = "100%";
            updateStepTracker(AGENT_STEPS.length - 1, true);
            localStorage.removeItem(ACTIVE_TASK_STORAGE_KEY);
            updateCurrentAgentCard({
                step_number: AGENT_STEPS.length,
                agent_display_name: "流程完成",
                message: "教学地图已生成完成。",
                output_preview: {
                    nodes: data.result && data.result.nodes ? data.result.nodes.length : 0,
                    edges: data.result && data.result.edges ? data.result.edges.length : 0,
                },
            });
            eventSource.close();
            if (data.result) showResult(data.result, taskId);
            resetSubmitBtn(true);
        } else if (data.type === "error") {
            addLogEntry("生成出错: " + data.message, "error");
            localStorage.removeItem(ACTIVE_TASK_STORAGE_KEY);
            updateCurrentAgentCard({
                agent_display_name: "执行失败",
                message: data.message || "工作流执行失败",
                output_preview: { status: "error" },
            });
            eventSource.close();
            resetSubmitBtn(false);
        }
    };

    eventSource.onerror = function () {
        addLogEntry("连接断开，尝试获取结果...", "error");
        eventSource.close();
        setTimeout(function () {
            fetch(API_PREFIX + "/result/" + taskId)
                .then(function (res) { return res.json(); })
                .then(function (data) {
                    if (data.status === "done" && data.result) {
                        localStorage.removeItem(ACTIVE_TASK_STORAGE_KEY);
                        addLogEntry("成功获取结果", "done");
                        showResult(data.result, taskId);
                        resetSubmitBtn(true);
                        return;
                    }
                    if (data.status === "running") {
                        var progress = Array.isArray(data.progress) ? data.progress : [];
                        connectSSE(taskId, progress.length);
                        return;
                    }
                    localStorage.removeItem(ACTIVE_TASK_STORAGE_KEY);
                    resetSubmitBtn(false);
                })
                .catch(function () {
                    localStorage.removeItem(ACTIVE_TASK_STORAGE_KEY);
                    resetSubmitBtn(false);
                });
        }, 1000);
    };
}

function returnToProgress() {
    document.querySelectorAll(".mat-left-tab").forEach(function (b) { b.classList.remove("active"); });
    document.querySelectorAll(".mat-left-tab-content").forEach(function (c) { c.classList.remove("active"); });
    document.querySelector('.mat-left-tab[data-target="formTab"]').classList.add("active");
    document.getElementById("formTab").classList.add("active");

    document.getElementById("placeholder").style.display = "none";
    document.getElementById("progressSection").style.display = "block";
    document.getElementById("viewTabs").style.display = "none";
    document.getElementById("graphSection").style.display = "none";
    document.getElementById("textSection").style.display = "none";
    document.getElementById("logsSection").style.display = "none";
    document.getElementById("detailSection").style.display = "none";
    document.getElementById("generatingBanner").style.display = "none";
}

function resetSubmitBtn(showNewPlanBtn) {
    var btn = document.getElementById("submitBtn");
    var newPlanBtn = document.getElementById("newPlanBtn");
    btn.disabled = false;
    btn.textContent = "重新生成";
    isGenerating = false;
    document.getElementById("generatingBanner").style.display = "none";
    newPlanBtn.style.display = showNewPlanBtn ? "block" : "none";
}

function startNewPlan() {
    if (eventSource) { eventSource.close(); eventSource = null; }
    localStorage.removeItem(ACTIVE_TASK_STORAGE_KEY);
    isGenerating = false;
    currentTaskId = null;
    currentResult = null;
    currentStepIndex = -1;

    document.getElementById("generateForm").reset();
    var btn = document.getElementById("submitBtn");
    btn.disabled = false;
    btn.textContent = "开始生成教学地图";
    document.getElementById("newPlanBtn").style.display = "none";
    document.getElementById("progressLog").innerHTML = "";
    document.getElementById("progressBar").style.width = "0%";
    document.getElementById("stepTracker").innerHTML = "";

    document.getElementById("placeholder").style.display = "flex";
    document.getElementById("progressSection").style.display = "none";
    document.getElementById("viewTabs").style.display = "none";
    document.getElementById("graphSection").style.display = "none";
    document.getElementById("textSection").style.display = "none";
    document.getElementById("logsSection").style.display = "none";
    document.getElementById("detailSection").style.display = "none";
    document.getElementById("generatingBanner").style.display = "none";

    document.querySelectorAll(".mat-left-tab").forEach(function (b) { b.classList.remove("active"); });
    document.querySelectorAll(".mat-left-tab-content").forEach(function (c) { c.classList.remove("active"); });
    document.querySelector('.mat-left-tab[data-target="formTab"]').classList.add("active");
    document.getElementById("formTab").classList.add("active");
}

function restoreTaskProgressOnLoad() {
    var taskId = localStorage.getItem(ACTIVE_TASK_STORAGE_KEY);
    if (!taskId) return;

    fetch(API_PREFIX + "/result/" + taskId)
        .then(function (res) { return res.json(); })
        .then(function (data) {
            if (data.status === "running") {
                currentTaskId = taskId;
                isGenerating = true;
                document.getElementById("placeholder").style.display = "none";
                document.getElementById("progressSection").style.display = "block";
                document.getElementById("viewTabs").style.display = "none";
                document.getElementById("graphSection").style.display = "none";
                document.getElementById("textSection").style.display = "none";
                document.getElementById("logsSection").style.display = "none";
                document.getElementById("detailSection").style.display = "none";
                document.getElementById("progressLog").innerHTML = "";
                initProgressTracker();
                updateCurrentAgentCard({
                    agent_display_name: "恢复任务",
                    message: "检测到未完成任务，正在恢复进度...",
                    output_preview: { task_id: taskId },
                });
                var btn = document.getElementById("submitBtn");
                btn.disabled = true;
                btn.textContent = "生成中...";
                var progress = Array.isArray(data.progress) ? data.progress : [];
                hydrateProgressSnapshot(progress);
                connectSSE(taskId, progress.length);
                return;
            }
            if (data.status === "done" && data.result) {
                localStorage.removeItem(ACTIVE_TASK_STORAGE_KEY);
                addLogEntry("刷新后已恢复完成结果", "done");
                showResult(data.result, taskId);
                resetSubmitBtn(true);
                return;
            }
            localStorage.removeItem(ACTIVE_TASK_STORAGE_KEY);
            resetSubmitBtn(false);
        })
        .catch(function (err) {
            addLogEntry("恢复任务失败: " + err.message, "error");
            localStorage.removeItem(ACTIVE_TASK_STORAGE_KEY);
            resetSubmitBtn(false);
        });
}

function hydrateProgressSnapshot(progressItems) {
    var maxStepReached = -1;
    progressItems.forEach(function (item) {
        if (typeof item === "string") { addLogEntry(item, "active"); return; }
        addLogEntry(item.message || "", "active");
        var stepIdx = AGENT_STEPS.indexOf(item.agent);
        if (stepIdx > maxStepReached) maxStepReached = stepIdx;
        updateCurrentAgentCard(item);
    });
    if (maxStepReached >= 0) {
        updateProgressBar(maxStepReached);
        updateStepTracker(maxStepReached);
    }
}

function initProgressTracker() {
    var tracker = document.getElementById("stepTracker");
    var html = "";
    AGENT_TRACKER_STEPS.forEach(function (step, idx) {
        var display = AGENT_DISPLAY_NAMES[step] || step;
        html += '<div class="mat-step-item" id="stepItem-' + step + '">';
        html += '<span class="mat-step-index">' + (idx + 1) + '</span>';
        html += '<span class="mat-step-name">' + display + '</span>';
        html += '</div>';
    });
    tracker.innerHTML = html;
}

function updateStepTracker(stepIdx, done) {
    currentStepIndex = stepIdx;
    var currentAgentKey = AGENT_STEPS[stepIdx] || "";
    AGENT_TRACKER_STEPS.forEach(function (step) {
        var item = document.getElementById("stepItem-" + step);
        if (!item) return;
        item.classList.remove("is-active", "is-done");
        if (done) { item.classList.add("is-done"); return; }
        var trackerStepInAll = AGENT_STEPS.indexOf(step);
        if (trackerStepInAll < stepIdx) { item.classList.add("is-done"); }
        else if (step === currentAgentKey) { item.classList.add("is-active"); }
    });
}

function updateCurrentAgentCard(payload) {
    var stepBadge = document.getElementById("currentStepBadge");
    var agentName = document.getElementById("currentAgentName");
    var agentStatus = document.getElementById("currentAgentStatus");
    var agentMessage = document.getElementById("currentAgentMessage");
    var agentInput = document.getElementById("currentAgentInput");
    var agentOutput = document.getElementById("currentAgentOutput");
    var stepNumber = payload.step_number || (currentStepIndex >= 0 ? (currentStepIndex + 1) : 0);
    var total = AGENT_STEPS.length;
    var displayAgent = payload.agent_display_name || AGENT_DISPLAY_NAMES[payload.agent] || payload.agent || "处理中";
    var msg = payload.message || "正在执行...";

    stepBadge.textContent = stepNumber > 0 ? ("步骤 " + stepNumber + " / " + total) : "等待开始";
    agentName.textContent = displayAgent;
    agentMessage.textContent = msg;

    if (agentStatus) {
        agentStatus.className = "mat-current-agent-status";
        if (msg.indexOf("通过") !== -1 && msg.indexOf("未通过") === -1) {
            agentStatus.textContent = "通过"; agentStatus.classList.add("passed");
        } else if (msg.indexOf("未通过") !== -1 || msg.indexOf("失败") !== -1) {
            agentStatus.textContent = "未通过"; agentStatus.classList.add("failed");
        } else if (msg.indexOf("完成") !== -1 || msg.indexOf("生成了") !== -1) {
            agentStatus.textContent = "完成"; agentStatus.classList.add("passed");
        } else {
            agentStatus.textContent = "运行中"; agentStatus.classList.add("running");
        }
    }

    if (agentInput) { agentInput.innerHTML = renderIoContent(payload.input_preview, "—"); }
    agentOutput.innerHTML = renderIoContent(payload.output_preview, "等待执行...");
}

function renderIoContent(data, emptyText) {
    if (!data || (typeof data === "object" && Object.keys(data).length === 0)) {
        return '<span class="mat-json-meta">' + emptyText + '</span>';
    }
    if (typeof data === "string") { return escapeHtml(data); }
    return syntaxHighlight(data);
}

function syntaxHighlight(obj) {
    var json = "";
    try { json = JSON.stringify(obj, null, 2); } catch (e) { return escapeHtml(String(obj)); }
    return json.replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g, function (match) {
        var cls = "mat-json-num";
        if (/^"/.test(match)) {
            if (/:$/.test(match)) { cls = "mat-json-key"; } else { cls = "mat-json-str"; }
        } else if (/true|false/.test(match)) { cls = "mat-json-bool"; }
        else if (/null/.test(match)) { cls = "mat-json-null"; }
        return '<span class="' + cls + '">' + escapeHtml(match) + '</span>';
    });
}

// ---------------------------------------------------------------------------
// Show result (graph + text + logs)
// ---------------------------------------------------------------------------
function showResult(result, taskId) {
    currentResult = result;
    if (taskId) currentTaskId = taskId;
    document.getElementById("viewTabs").style.display = "flex";
    document.querySelectorAll(".mat-view-tab").forEach(function (b) { b.classList.remove("active"); });
    document.querySelector('.mat-view-tab[data-view="graph"]').classList.add("active");
    document.getElementById("graphSection").style.display = "block";
    document.getElementById("textSection").style.display = "none";
    document.getElementById("logsSection").style.display = "none";
    document.getElementById("detailSection").style.display = "none";
    renderGraph(result);
    renderTextView(result);
}

// ---------------------------------------------------------------------------
// Agent Logs View
// ---------------------------------------------------------------------------
function loadAgentLogs(taskId) {
    var container = document.getElementById("logsContent");
    container.innerHTML = '<p class="mat-logs-loading">加载日志中...</p>';

    fetch(API_PREFIX + "/logs/" + taskId)
        .then(function (res) { return res.json(); })
        .then(function (logs) {
            if (!logs || !logs.length) {
                container.innerHTML = '<p class="mat-logs-empty">暂无日志记录</p>';
                return;
            }
            var html = '<div class="mat-logs-summary"><p>共 <strong>' + logs.length + '</strong> 个Agent执行记录</p></div>';
            logs.forEach(function (log) {
                var output = log.output || {};
                var inputData = output.input_preview || null;
                var outputData = output.output || output;
                if (outputData && outputData.input_preview) {
                    outputData = Object.assign({}, outputData);
                    delete outputData.input_preview;
                }
                html += '<div class="mat-log-block">';
                html += '<div class="mat-log-block-header">';
                html += '<span class="mat-log-step">步骤 ' + log.step_number + '</span>';
                html += '<span class="mat-log-agent-name">' + log.agent_name + '</span>';
                html += '<span class="mat-log-time">' + log.created_at + '</span>';
                html += '<button class="mat-log-toggle" onclick="toggleLogDetail(this)">展开</button>';
                html += '</div>';
                html += '<div class="mat-log-block-body" style="display:none;">';
                html += '<div class="mat-log-io-grid">';
                html += '<div class="mat-log-io-panel">';
                html += '<div class="mat-log-io-head"><span class="mat-io-icon mat-io-in">IN</span>输入</div>';
                html += '<div class="mat-log-io-body">' + renderIoContent(inputData, "无输入预览") + '</div>';
                html += '</div>';
                html += '<div class="mat-log-io-panel">';
                html += '<div class="mat-log-io-head"><span class="mat-io-icon mat-io-out">OUT</span>输出</div>';
                html += '<div class="mat-log-io-body">' + renderIoContent(outputData, "无输出") + '</div>';
                html += '</div>';
                html += '</div></div></div>';
            });
            container.innerHTML = html;
        })
        .catch(function (err) {
            container.innerHTML = '<p class="mat-logs-error">加载日志失败: ' + err.message + '</p>';
        });
}

function toggleLogDetail(btn) {
    var body = btn.parentElement.nextElementSibling;
    if (body.style.display === "none") { body.style.display = "block"; btn.textContent = "收起"; }
    else { body.style.display = "none"; btn.textContent = "展开"; }
}

function escapeHtml(text) {
    var div = document.createElement("div");
    div.innerText = text;
    return div.innerHTML;
}

// ---------------------------------------------------------------------------
// Text view rendering
// ---------------------------------------------------------------------------
function renderTextView(teachingMap) {
    var container = document.getElementById("textContent");
    var nodes = teachingMap.nodes || [];
    var edges = teachingMap.edges || [];

    var mainNodes = nodes.filter(function (n) { return n.question_type === "main"; });
    var variantNodes = nodes.filter(function (n) { return n.question_type === "variant"; });
    var scaffoldNodes = nodes.filter(function (n) { return n.question_type === "scaffold"; });
    var mainOrder = orderMainNodes(mainNodes, edges);

    var html = '<div class="mat-text-summary">';
    html += '<p>共 <strong>' + nodes.length + '</strong> 个问题节点（主干 ' + mainNodes.length + ' 个、变式 ' + variantNodes.length + ' 个、支架 ' + scaffoldNodes.length + ' 个），<strong>' + edges.length + '</strong> 条连接关系</p>';
    html += '</div>';

    mainOrder.forEach(function (mainNode, idx) {
        html += '<div class="mat-text-block mat-text-main">';
        html += '<div class="mat-text-block-header mat-main-header">';
        html += '<span class="mat-text-num">' + (idx + 1) + '</span>';
        html += '<span class="mat-text-tag mat-tag-main">主干问题</span>';
        html += '<span class="mat-text-id">' + mainNode.id + '</span>';
        html += '</div>';
        html += '<div class="mat-text-block-body">';
        html += '<p class="mat-text-question">' + (mainNode.content || "") + '</p>';
        html += renderMeta(mainNode);
        html += '</div>';

        var relatedVariants = variantNodes.filter(function (v) { return v.parent_id === mainNode.id; });
        if (relatedVariants.length > 0) {
            html += '<div class="mat-text-sub-group">';
            html += '<div class="mat-text-sub-label mat-variant-label">变式问题</div>';
            relatedVariants.forEach(function (v) {
                html += '<div class="mat-text-block mat-text-variant">';
                html += '<div class="mat-text-block-header mat-variant-header">';
                html += '<span class="mat-text-tag mat-tag-variant">变式</span>';
                html += '<span class="mat-text-id">' + v.id + '</span>';
                if (v.variation_type) html += '<span class="mat-text-vtype">' + v.variation_type + '</span>';
                html += '</div>';
                html += '<div class="mat-text-block-body">';
                html += '<p class="mat-text-question">' + (v.content || "") + '</p>';
                html += renderMeta(v);
                html += '</div></div>';
            });
            html += '</div>';
        }

        if (idx < mainOrder.length - 1) {
            var nextMain = mainOrder[idx + 1];
            var relatedScaffolds = scaffoldNodes.filter(function (s) {
                return s.from_main_id === mainNode.id || s.to_main_id === nextMain.id;
            });
            if (relatedScaffolds.length > 0) {
                html += '<div class="mat-text-sub-group">';
                html += '<div class="mat-text-sub-label mat-scaffold-label">支架问题（过渡到下一主干）</div>';
                relatedScaffolds.forEach(function (s) {
                    html += '<div class="mat-text-block mat-text-scaffold">';
                    html += '<div class="mat-text-block-header mat-scaffold-header">';
                    html += '<span class="mat-text-tag mat-tag-scaffold">支架</span>';
                    html += '<span class="mat-text-id">' + s.id + '</span>';
                    html += '</div>';
                    html += '<div class="mat-text-block-body">';
                    html += '<p class="mat-text-question">' + (s.content || "") + '</p>';
                    html += renderMeta(s);
                    if (s.bridge_function) html += '<p class="mat-text-bridge">桥梁功能：' + s.bridge_function + '</p>';
                    html += '</div></div>';
                });
                html += '</div>';
            }
            html += '<div class="mat-text-arrow">&#8595;</div>';
        }
        html += '</div>';
    });

    container.innerHTML = html;
}

function renderMeta(node) {
    var html = '<div class="mat-text-meta">';
    var designIntent = node.design_intent || node.design_rationale || "";
    if (node.knowledge_points && node.knowledge_points.length) {
        html += '<span>知识点：' + node.knowledge_points.join("、") + '</span>';
    }
    var cl = node.cognitive_level || node.bloom_level || "";
    var clLabel = COGNITIVE_LABELS[cl] || cl;
    if (clLabel) html += '<span>认知层次：' + clLabel + '</span>';
    if (node.difficulty !== undefined) html += '<span>难度：' + node.difficulty + '</span>';
    if (designIntent) html += '<span>设计意图：' + designIntent + '</span>';
    html += '</div>';
    return html;
}

function orderMainNodes(mainNodes, edges) {
    if (mainNodes.length <= 1) return mainNodes;
    var seqEdges = edges.filter(function (e) { return e.relation === "sequence"; });
    var mainIds = new Set(mainNodes.map(function (n) { return n.id; }));
    var adj = {};
    var inDeg = {};
    mainIds.forEach(function (id) { adj[id] = []; inDeg[id] = 0; });
    seqEdges.forEach(function (e) {
        if (mainIds.has(e.source) && mainIds.has(e.target)) {
            adj[e.source].push(e.target);
            inDeg[e.target] = (inDeg[e.target] || 0) + 1;
        }
    });
    var queue = [];
    mainIds.forEach(function (id) { if (!inDeg[id]) queue.push(id); });
    var ordered = [];
    while (queue.length) {
        var cur = queue.shift();
        ordered.push(cur);
        (adj[cur] || []).forEach(function (next) { inDeg[next]--; if (inDeg[next] === 0) queue.push(next); });
    }
    var byId = {};
    mainNodes.forEach(function (n) { byId[n.id] = n; });
    var result = ordered.filter(function (id) { return byId[id]; }).map(function (id) { return byId[id]; });
    mainNodes.forEach(function (n) { if (ordered.indexOf(n.id) === -1) result.push(n); });
    return result;
}

// ---------------------------------------------------------------------------
// History
// ---------------------------------------------------------------------------
function loadHistory() {
    fetch(API_PREFIX + "/history")
        .then(function (res) { return res.json(); })
        .then(function (list) {
            var container = document.getElementById("historyList");
            if (!list.length) {
                container.innerHTML = '<p class="mat-history-empty">暂无历史记录</p>';
                return;
            }
            var html = "";
            list.forEach(function (item) {
                var goals = (item.teaching_goals || "").substring(0, 60);
                var safeGoals = escapeHtml(goals + (goals.length >= 60 ? "..." : ""));
                html += '<div class="mat-history-item" data-id="' + item.id + '">';
                html += '<div class="mat-history-item-header">';
                html += '<span class="mat-history-subject">' + item.subject + ' · ' + item.grade + '</span>';
                html += '<span class="mat-history-time">' + item.created_at + '</span>';
                html += '</div>';
                html += '<div class="mat-history-goals">' + safeGoals + '</div>';
                html += '<div class="mat-history-actions">';
                html += '<button class="mat-btn-sm mat-btn-view" onclick="loadHistoryItem(\'' + item.id + '\')">查看</button>';
                html += '<button class="mat-btn-sm mat-btn-input" onclick="toggleHistoryInput(\'' + item.id + '\', this, event)">输入</button>';
                html += '<button class="mat-btn-sm mat-btn-logs" onclick="loadHistoryLogs(\'' + item.id + '\', event)">日志</button>';
                html += '<button class="mat-btn-sm mat-btn-delete" onclick="deleteHistoryItem(\'' + item.id + '\', event)">删除</button>';
                html += '</div>';
                html += '<div class="mat-history-input-detail" id="historyInputDetail-' + item.id + '" style="display:none;"></div>';
                html += '</div>';
            });
            container.innerHTML = html;
        });
}

function toggleHistoryInput(recordId, btn, event) {
    event.stopPropagation();
    var detail = document.getElementById("historyInputDetail-" + recordId);
    if (!detail) return;
    if (detail.style.display === "block") { detail.style.display = "none"; btn.textContent = "输入"; return; }
    if (detail.dataset.loaded === "1") { detail.style.display = "block"; btn.textContent = "收起输入"; return; }

    detail.innerHTML = '<div class="mat-history-input-loading">加载输入信息...</div>';
    detail.style.display = "block";
    btn.textContent = "收起输入";

    fetch(API_PREFIX + "/history/" + recordId)
        .then(function (res) { return res.json(); })
        .then(function (data) {
            if (data.error) { detail.innerHTML = '<div class="mat-history-input-loading">加载失败</div>'; return; }
            var html = '';
            html += '<div class="mat-history-input-title">教师输入信息</div>';
            html += '<div class="mat-history-input-row"><span class="mat-history-input-label">学科：</span><span class="mat-history-input-value">' + escapeHtml(data.subject || "") + '</span></div>';
            html += '<div class="mat-history-input-row"><span class="mat-history-input-label">年级：</span><span class="mat-history-input-value">' + escapeHtml(data.grade || "") + '</span></div>';
            html += '<div class="mat-history-input-row"><span class="mat-history-input-label">语言风格：</span><span class="mat-history-input-value">' + escapeHtml(data.language_style || "未设置") + '</span></div>';
            html += '<div class="mat-history-input-row"><span class="mat-history-input-label">教学目标：</span><span class="mat-history-input-value">' + escapeHtml(data.teaching_goals || "未填写") + '</span></div>';
            html += '<div class="mat-history-input-row"><span class="mat-history-input-label">学情描述：</span><span class="mat-history-input-value">' + escapeHtml(data.student_profile || "未填写") + '</span></div>';
            detail.innerHTML = html;
            detail.dataset.loaded = "1";
        })
        .catch(function () { detail.innerHTML = '<div class="mat-history-input-loading">加载失败</div>'; });
}

function loadHistoryItem(recordId) {
    currentTaskId = recordId;
    fetch(API_PREFIX + "/history/" + recordId)
        .then(function (res) { return res.json(); })
        .then(function (data) {
            if (data.error) return;
            document.getElementById("placeholder").style.display = "none";
            document.getElementById("progressSection").style.display = "none";
            showResult(data.result, recordId);
            if (isGenerating) {
                document.getElementById("generatingBanner").style.display = "flex";
                document.getElementById("generatingBannerText").textContent = "正在生成教学地图，当前查看的是历史记录";
            }
        });
}

function loadHistoryLogs(recordId, event) {
    event.stopPropagation();
    currentTaskId = recordId;
    document.getElementById("placeholder").style.display = "none";
    document.getElementById("progressSection").style.display = "none";
    document.getElementById("viewTabs").style.display = "flex";
    document.querySelectorAll(".mat-view-tab").forEach(function (b) { b.classList.remove("active"); });
    document.querySelector('.mat-view-tab[data-view="logs"]').classList.add("active");
    document.getElementById("graphSection").style.display = "none";
    document.getElementById("textSection").style.display = "none";
    document.getElementById("logsSection").style.display = "block";
    document.getElementById("detailSection").style.display = "none";
    loadAgentLogs(recordId);
}

function deleteHistoryItem(recordId, event) {
    event.stopPropagation();
    if (!confirm("确定删除此记录？")) return;
    fetch(API_PREFIX + "/history/" + recordId, { method: "DELETE" })
        .then(function () { loadHistory(); });
}

// ---------------------------------------------------------------------------
// Progress helpers
// ---------------------------------------------------------------------------
function addLogEntry(message, status) {
    var log = document.getElementById("progressLog");
    var entry = document.createElement("div");
    entry.className = "mat-log-entry";
    var dot = document.createElement("span");
    dot.className = "mat-log-dot";
    if (status === "done") dot.classList.add("done");
    if (status === "error") dot.classList.add("error");
    var text = document.createElement("span");
    text.className = "mat-log-text";
    text.textContent = message;
    entry.appendChild(dot);
    entry.appendChild(text);
    log.appendChild(entry);
    log.scrollTop = log.scrollHeight;
}

function updateProgressBar(stepIdx) {
    var total = AGENT_STEPS.length;
    if (stepIdx < 0) return;
    var pct = Math.min(((stepIdx + 1) / total) * 95, 95);
    document.getElementById("progressBar").style.width = pct + "%";
}

restoreTaskProgressOnLoad();
