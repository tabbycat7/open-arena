/**
 * main.js — Form submission, SSE listener, progress display, history, text view, logs view
 */

const AGENT_STEPS = [
    "learning_analysis",
    "teaching_logic_design",
    "main_question_chain",
    "cognitive_check",        // 并行-主干检验1
    "goal_check",             // 并行-主干检验2
    "teaching_logic_check",   // 并行-主干检验3
    "aggregate_main_checks",  // 汇总
    "variant_question",
    "scaffold_question",
    "learning_check",
    "aggregate_variant_scaffold_checks",
    "map_integration",
];

const AGENT_DISPLAY_NAMES = {
    learning_analysis: "学情与目标解析Agent",
    teaching_logic_design: "教学地图逻辑规划Agent",
    main_question_chain: "主干问题链构建Agent",
    cognitive_check: "认知对齐检验Agent(V1)",
    goal_check: "教学目标对齐检验Agent(V3)",
    teaching_logic_check: "教学逻辑检验Agent(V5)",
    aggregate_main_checks: "系统-主干问题检验汇总",
    variant_question: "变式问题生成Agent",
    scaffold_question: "支架问题生成Agent",
    learning_check: "学情对齐检验Agent(V2)",
    aggregate_variant_scaffold_checks: "系统-变式/支架检验汇总",
    map_integration: "教学地图整合Agent",
};

const COGNITIVE_LABELS = {
    remember: "记忆", understand: "理解", apply: "应用",
    analyze: "分析", evaluate: "评价", create: "创造",
};

let currentTaskId = null;
let eventSource = null;
let currentResult = null;
let isGenerating = false;
let currentStepIndex = -1;
const ACTIVE_TASK_STORAGE_KEY = "teaching_map_active_task_id";

// ---------------------------------------------------------------------------
// Left panel tabs
// ---------------------------------------------------------------------------
document.querySelectorAll(".left-tab").forEach(function (btn) {
    btn.addEventListener("click", function () {
        document.querySelectorAll(".left-tab").forEach(function (b) { b.classList.remove("active"); });
        document.querySelectorAll(".left-tab-content").forEach(function (c) { c.classList.remove("active"); });
        this.classList.add("active");
        document.getElementById(this.dataset.target).classList.add("active");
        if (this.dataset.target === "historyTab") {
            loadHistory();
            // 若正在生成，右侧显示"返回进度"横幅
            if (isGenerating) {
                document.getElementById("generatingBanner").style.display = "flex";
            }
        }
    });
});

// ---------------------------------------------------------------------------
// View mode tabs (graph / text / logs)
// ---------------------------------------------------------------------------
document.querySelectorAll(".view-tab").forEach(function (btn) {
    btn.addEventListener("click", function () {
        document.querySelectorAll(".view-tab").forEach(function (b) { b.classList.remove("active"); });
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

function startGeneration() {
    var form = document.getElementById("generateForm");
    var formData = new FormData(form);
    var submitBtn = document.getElementById("submitBtn");

    submitBtn.disabled = true;
    submitBtn.textContent = "生成中...";
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
        output_preview: { status: "waiting" },
    });
    currentStepIndex = -1;
    currentResult = null;

    fetch("/api/generate", { method: "POST", body: formData })
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
    eventSource = new EventSource("/api/stream/" + taskId + "?from=" + start);
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
            resetSubmitBtn();
        } else if (data.type === "error") {
            addLogEntry("生成出错: " + data.message, "error");
            localStorage.removeItem(ACTIVE_TASK_STORAGE_KEY);
            updateCurrentAgentCard({
                agent_display_name: "执行失败",
                message: data.message || "工作流执行失败",
                output_preview: { status: "error" },
            });
            eventSource.close();
            resetSubmitBtn();
        }
    };

    eventSource.onerror = function () {
        addLogEntry("连接断开，尝试获取结果...", "error");
        eventSource.close();
        setTimeout(function () {
            fetch("/api/result/" + taskId)
                .then(function (res) { return res.json(); })
                .then(function (data) {
                    if (data.status === "done" && data.result) {
                        localStorage.removeItem(ACTIVE_TASK_STORAGE_KEY);
                        addLogEntry("成功获取结果", "done");
                        showResult(data.result, taskId);
                        resetSubmitBtn();
                        return;
                    }

                    if (data.status === "running") {
                        var progress = Array.isArray(data.progress) ? data.progress : [];
                        connectSSE(taskId, progress.length);
                        return;
                    }

                    localStorage.removeItem(ACTIVE_TASK_STORAGE_KEY);
                    resetSubmitBtn();
                })
                .catch(function () {
                    localStorage.removeItem(ACTIVE_TASK_STORAGE_KEY);
                    resetSubmitBtn();
                });
        }, 1000);
    };
}

function returnToProgress() {
    // 切回"新建教案"tab
    document.querySelectorAll(".left-tab").forEach(function (b) { b.classList.remove("active"); });
    document.querySelectorAll(".left-tab-content").forEach(function (c) { c.classList.remove("active"); });
    document.querySelector('.left-tab[data-target="formTab"]').classList.add("active");
    document.getElementById("formTab").classList.add("active");

    // 右侧恢复进度视图
    document.getElementById("placeholder").style.display = "none";
    document.getElementById("progressSection").style.display = "block";
    document.getElementById("viewTabs").style.display = "none";
    document.getElementById("graphSection").style.display = "none";
    document.getElementById("textSection").style.display = "none";
    document.getElementById("logsSection").style.display = "none";
    document.getElementById("detailSection").style.display = "none";
    document.getElementById("generatingBanner").style.display = "none";
}

function resetSubmitBtn() {
    var btn = document.getElementById("submitBtn");
    btn.disabled = false;
    btn.textContent = "重新生成";
    isGenerating = false;
    document.getElementById("generatingBanner").style.display = "none";
}

function restoreTaskProgressOnLoad() {
    var taskId = localStorage.getItem(ACTIVE_TASK_STORAGE_KEY);
    if (!taskId) return;

    fetch("/api/result/" + taskId)
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
                resetSubmitBtn();
                return;
            }

            localStorage.removeItem(ACTIVE_TASK_STORAGE_KEY);
            resetSubmitBtn();
        })
        .catch(function (err) {
            addLogEntry("恢复任务失败: " + err.message, "error");
            localStorage.removeItem(ACTIVE_TASK_STORAGE_KEY);
            resetSubmitBtn();
        });
}

function hydrateProgressSnapshot(progressItems) {
    var maxStepReached = -1;
    progressItems.forEach(function (item) {
        if (typeof item === "string") {
            addLogEntry(item, "active");
            return;
        }
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
    AGENT_STEPS.forEach(function (step, idx) {
        var display = AGENT_DISPLAY_NAMES[step] || step;
        html += '<div class="step-item" id="stepItem-' + step + '">';
        html += '<span class="step-index">' + (idx + 1) + '</span>';
        html += '<span class="step-name">' + display + '</span>';
        html += '</div>';
    });
    tracker.innerHTML = html;
}

function updateStepTracker(stepIdx, done) {
    currentStepIndex = stepIdx;
    AGENT_STEPS.forEach(function (step, idx) {
        var item = document.getElementById("stepItem-" + step);
        if (!item) return;
        item.classList.remove("is-active");
        item.classList.remove("is-done");

        if (done || idx < stepIdx) {
            item.classList.add("is-done");
            return;
        }
        if (idx === stepIdx) {
            item.classList.add("is-active");
        }
    });
}

function updateCurrentAgentCard(payload) {
    var stepBadge = document.getElementById("currentStepBadge");
    var agentName = document.getElementById("currentAgentName");
    var agentMessage = document.getElementById("currentAgentMessage");
    var agentOutput = document.getElementById("currentAgentOutput");
    var stepNumber = payload.step_number || (currentStepIndex >= 0 ? (currentStepIndex + 1) : 0);
    var total = AGENT_STEPS.length;
    var displayAgent = payload.agent_display_name || AGENT_DISPLAY_NAMES[payload.agent] || payload.agent || "处理中";

    stepBadge.textContent = stepNumber > 0 ? ("步骤 " + stepNumber + " / " + total) : "等待开始";
    agentName.textContent = displayAgent;
    agentMessage.textContent = payload.message || "正在执行...";
    agentOutput.textContent = formatOutputPreview(payload.output_preview);
}

function formatOutputPreview(output) {
    if (!output) return "当前步骤尚无可展示输出。";
    if (typeof output === "string") return output;
    try {
        return JSON.stringify(output, null, 2);
    } catch (err) {
        return String(output);
    }
}

// ---------------------------------------------------------------------------
// Show result (graph + text + logs)
// ---------------------------------------------------------------------------
function showResult(result, taskId) {
    currentResult = result;
    if (taskId) currentTaskId = taskId;
    document.getElementById("viewTabs").style.display = "flex";
    document.querySelectorAll(".view-tab").forEach(function (b) { b.classList.remove("active"); });
    document.querySelector('.view-tab[data-view="graph"]').classList.add("active");
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
    container.innerHTML = '<p class="logs-loading">加载日志中...</p>';

    fetch("/api/logs/" + taskId)
        .then(function (res) { return res.json(); })
        .then(function (logs) {
            if (!logs || !logs.length) {
                container.innerHTML = '<p class="logs-empty">暂无日志记录</p>';
                return;
            }
            var html = '<div class="logs-summary"><p>共 <strong>' + logs.length + '</strong> 个Agent执行记录</p></div>';
            logs.forEach(function (log, idx) {
                html += '<div class="log-block">';
                html += '<div class="log-block-header">';
                html += '<span class="log-step">步骤 ' + log.step_number + '</span>';
                html += '<span class="log-agent-name">' + log.agent_name + '</span>';
                html += '<span class="log-time">' + log.created_at + '</span>';
                html += '<button class="log-toggle" onclick="toggleLogDetail(this)">展开</button>';
                html += '</div>';
                html += '<div class="log-block-body" style="display:none;">';
                html += '<pre class="log-json">' + escapeHtml(JSON.stringify(log.output, null, 2)) + '</pre>';
                html += '</div>';
                html += '</div>';
            });
            container.innerHTML = html;
        })
        .catch(function (err) {
            container.innerHTML = '<p class="logs-error">加载日志失败: ' + err.message + '</p>';
        });
}

function toggleLogDetail(btn) {
    var body = btn.parentElement.nextElementSibling;
    if (body.style.display === "none") {
        body.style.display = "block";
        btn.textContent = "收起";
    } else {
        body.style.display = "none";
        btn.textContent = "展开";
    }
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

    var html = "";

    html += '<div class="text-summary">';
    html += '<p>共 <strong>' + nodes.length + '</strong> 个问题节点（主干 ' + mainNodes.length + ' 个、变式 ' + variantNodes.length + ' 个、支架 ' + scaffoldNodes.length + ' 个），<strong>' + edges.length + '</strong> 条连接关系</p>';
    html += '</div>';

    mainOrder.forEach(function (mainNode, idx) {
        html += '<div class="text-block text-main">';
        html += '<div class="text-block-header main-header">';
        html += '<span class="text-num">' + (idx + 1) + '</span>';
        html += '<span class="text-tag tag-main">主干问题</span>';
        html += '<span class="text-id">' + mainNode.id + '</span>';
        html += '</div>';
        html += '<div class="text-block-body">';
        html += '<p class="text-question">' + (mainNode.content || "") + '</p>';
        html += renderMeta(mainNode);
        html += '</div>';

        var relatedVariants = variantNodes.filter(function (v) { return v.parent_id === mainNode.id; });
        if (relatedVariants.length > 0) {
            html += '<div class="text-sub-group">';
            html += '<div class="text-sub-label variant-label">变式问题</div>';
            relatedVariants.forEach(function (v) {
                html += '<div class="text-block text-variant">';
                html += '<div class="text-block-header variant-header">';
                html += '<span class="text-tag tag-variant">变式</span>';
                html += '<span class="text-id">' + v.id + '</span>';
                if (v.variation_type) html += '<span class="text-vtype">' + v.variation_type + '</span>';
                html += '</div>';
                html += '<div class="text-block-body">';
                html += '<p class="text-question">' + (v.content || "") + '</p>';
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
                html += '<div class="text-sub-group">';
                html += '<div class="text-sub-label scaffold-label">支架问题（过渡到下一主干）</div>';
                relatedScaffolds.forEach(function (s) {
                    html += '<div class="text-block text-scaffold">';
                    html += '<div class="text-block-header scaffold-header">';
                    html += '<span class="text-tag tag-scaffold">支架</span>';
                    html += '<span class="text-id">' + s.id + '</span>';
                    html += '</div>';
                    html += '<div class="text-block-body">';
                    html += '<p class="text-question">' + (s.content || "") + '</p>';
                    html += renderMeta(s);
                    if (s.bridge_function) html += '<p class="text-bridge">桥梁功能：' + s.bridge_function + '</p>';
                    html += '</div></div>';
                });
                html += '</div>';
            }

            html += '<div class="text-arrow">&#8595;</div>';
        }

        html += '</div>';
    });

    container.innerHTML = html;
}

function renderMeta(node) {
    var html = '<div class="text-meta">';
    if (node.knowledge_points && node.knowledge_points.length) {
        html += '<span>知识点：' + node.knowledge_points.join("、") + '</span>';
    }
    var cl = node.cognitive_level || node.bloom_level || "";
    var clLabel = COGNITIVE_LABELS[cl] || cl;
    if (clLabel) html += '<span>认知层次：' + clLabel + '</span>';
    if (node.difficulty !== undefined) html += '<span>难度：' + node.difficulty + '</span>';
    if (node.design_rationale) html += '<span>设计意图：' + node.design_rationale + '</span>';
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
        (adj[cur] || []).forEach(function (next) {
            inDeg[next]--;
            if (inDeg[next] === 0) queue.push(next);
        });
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
    fetch("/api/history")
        .then(function (res) { return res.json(); })
        .then(function (list) {
            var container = document.getElementById("historyList");
            if (!list.length) {
                container.innerHTML = '<p class="history-empty">暂无历史记录</p>';
                return;
            }
            var html = "";
            list.forEach(function (item) {
                var goals = (item.teaching_goals || "").substring(0, 60);
                html += '<div class="history-item" data-id="' + item.id + '">';
                html += '<div class="history-item-header">';
                html += '<span class="history-subject">' + item.subject + ' · ' + item.grade + '</span>';
                html += '<span class="history-time">' + item.created_at + '</span>';
                html += '</div>';
                html += '<div class="history-goals">' + goals + (goals.length >= 60 ? "..." : "") + '</div>';
                html += '<div class="history-actions">';
                html += '<button class="btn-sm btn-view" onclick="loadHistoryItem(\'' + item.id + '\')">查看</button>';
                html += '<button class="btn-sm btn-logs" onclick="loadHistoryLogs(\'' + item.id + '\', event)">日志</button>';
                html += '<button class="btn-sm btn-delete" onclick="deleteHistoryItem(\'' + item.id + '\', event)">删除</button>';
                html += '</div>';
                html += '</div>';
            });
            container.innerHTML = html;
        });
}

function loadHistoryItem(recordId) {
    currentTaskId = recordId;
    fetch("/api/history/" + recordId)
        .then(function (res) { return res.json(); })
        .then(function (data) {
            if (data.error) return;
            document.getElementById("placeholder").style.display = "none";
            document.getElementById("progressSection").style.display = "none";
            showResult(data.result, recordId);
            // 若正在生成，保持横幅可见
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
    document.querySelectorAll(".view-tab").forEach(function (b) { b.classList.remove("active"); });
    document.querySelector('.view-tab[data-view="logs"]').classList.add("active");
    document.getElementById("graphSection").style.display = "none";
    document.getElementById("textSection").style.display = "none";
    document.getElementById("logsSection").style.display = "block";
    document.getElementById("detailSection").style.display = "none";
    loadAgentLogs(recordId);
}

function deleteHistoryItem(recordId, event) {
    event.stopPropagation();
    if (!confirm("确定删除此记录？")) return;
    fetch("/api/history/" + recordId, { method: "DELETE" })
        .then(function () { loadHistory(); });
}

// ---------------------------------------------------------------------------
// Progress helpers
// ---------------------------------------------------------------------------
function addLogEntry(message, status) {
    var log = document.getElementById("progressLog");
    var entry = document.createElement("div");
    entry.className = "log-entry";
    var dot = document.createElement("span");
    dot.className = "log-dot";
    if (status === "done") dot.classList.add("done");
    if (status === "error") dot.classList.add("error");
    var text = document.createElement("span");
    text.className = "log-text";
    text.textContent = message;
    entry.appendChild(dot);
    entry.appendChild(text);
    log.appendChild(entry);
    log.scrollTop = log.scrollHeight;
}

function updateProgressBar(stepIdx, agent) {
    var total = AGENT_STEPS.length;
    var pct;
    if (stepIdx < 0) {
        // agent 不在主流程列表（如 bump_retry 节点），保持当前进度不变
        return;
    }
    // 到达第 stepIdx 步（0-indexed），进度 = (stepIdx + 1) / total * 95
    pct = Math.min(((stepIdx + 1) / total) * 95, 95);
    document.getElementById("progressBar").style.width = pct + "%";
}

restoreTaskProgressOnLoad();
