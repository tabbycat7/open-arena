/**
 * main.js — Form submission, SSE listener, progress display, history, text view, logs view
 */

// 所有节点（含系统节点），用于进度条百分比计算
const AGENT_STEPS = [
    "learning_analysis",
    "teaching_logic_design",
    "main_question_chain",
    "main_question_check",
    "fan_out_gen",
    "variant_question",
    "scaffold_question",
    "variant_check",
    "scaffold_check",
    "aggregate_sub_pipelines",
    "map_integration",
];

// 只在步骤追踪器中展示的 Agent 节点（过滤掉系统调度节点）
const AGENT_TRACKER_STEPS = [
    "learning_analysis",
    "teaching_logic_design",
    "main_question_chain",
    "main_question_check",
    "variant_question",
    "variant_check",
    "scaffold_question",
    "scaffold_check",
    "map_integration",
];

const AGENT_DISPLAY_NAMES = {
    learning_analysis: "学情与目标解析",
    teaching_logic_design: "教学蓝图规划",
    main_question_chain: "主干问题链构建",
    main_question_check: "主干问题综合校验",
    variant_question: "变式问题生成",
    variant_check: "变式问题检验",
    scaffold_question: "支架问题生成",
    scaffold_check: "支架问题检验",
    map_integration: "教学地图整合",
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
let historyEventsBound = false;
const APP_BASE_PATH = (window.APP_BASE_PATH || "").replace(/\/$/, "");
const workspaceLayoutEl = document.getElementById("workspaceLayout");
const languageStyleSelectEl = document.getElementById("language_style");
const customLanguageWrapEl = document.getElementById("languageStyleCustomWrap");
const customLanguageInputEl = document.getElementById("custom_language_style");
const modelPickerEl = document.getElementById("modelPicker");
const modelPickerTriggerEl = document.getElementById("modelPickerTrigger");
const modelPickerMenuEl = document.getElementById("modelPickerMenu");
const modelPickerLabelEl = document.getElementById("modelPickerLabel");
const modelPickerIconEl = document.getElementById("modelPickerIcon");
const modelIdInputEl = document.getElementById("model_id");
let markdownOptionsApplied = false;

function setUiStage(stage) {
    if (!workspaceLayoutEl) return;
    workspaceLayoutEl.classList.remove("stage-input", "stage-generation");
    if (stage === "generation") {
        workspaceLayoutEl.classList.add("stage-generation");
        return;
    }
    workspaceLayoutEl.classList.add("stage-input");
}

function updateLanguageStyleCustomVisibility() {
    if (!languageStyleSelectEl || !customLanguageWrapEl || !customLanguageInputEl) return;
    var isCustom = languageStyleSelectEl.value === "自定义";
    customLanguageWrapEl.style.display = isCustom ? "block" : "none";
    customLanguageInputEl.required = isCustom;
    if (!isCustom) {
        customLanguageInputEl.value = "";
    }
}

function setStopButtonsState(visible, disabled, text) {
    ["stopBtn", "stopBtnTop"].forEach(function (id) {
        var btn = document.getElementById(id);
        if (!btn) return;
        if (!visible) {
            btn.style.display = "none";
        } else {
            btn.style.display = id === "stopBtn" ? "block" : "inline-flex";
        }
        btn.disabled = !!disabled;
        btn.textContent = text || "强制停止";
    });
}

function setBackToGenerationButtonState(visible) {
    var btn = document.getElementById("backToGenerationBtn");
    if (!btn) return;
    btn.style.display = visible ? "block" : "none";
}

function setModelPickerValue(modelId, label, iconUrl) {
    if (modelIdInputEl) modelIdInputEl.value = modelId || "";
    if (modelPickerLabelEl) modelPickerLabelEl.textContent = label || "请选择模型";
    if (modelPickerIconEl && iconUrl) modelPickerIconEl.src = iconUrl;

    if (!modelPickerMenuEl) return;
    modelPickerMenuEl.querySelectorAll(".model-picker-item").forEach(function (item) {
        var active = item.dataset.value === (modelId || "");
        item.classList.toggle("active", active);
        item.setAttribute("aria-selected", active ? "true" : "false");
    });
}

function closeModelPicker() {
    if (!modelPickerEl || !modelPickerTriggerEl) return;
    modelPickerEl.classList.remove("open");
    modelPickerTriggerEl.setAttribute("aria-expanded", "false");
}

function syncModelPickerFromInput() {
    if (!modelPickerMenuEl || !modelIdInputEl) return;
    var target = modelPickerMenuEl.querySelector('.model-picker-item[data-value="' + modelIdInputEl.value + '"]');
    if (!target) {
        target = modelPickerMenuEl.querySelector(".model-picker-item");
    }
    if (!target) return;
    setModelPickerValue(target.dataset.value, target.dataset.label, target.dataset.icon);
}

function initModelPicker() {
    if (!modelPickerEl || !modelPickerTriggerEl || !modelPickerMenuEl || !modelIdInputEl) return;

    modelPickerTriggerEl.addEventListener("click", function () {
        var willOpen = !modelPickerEl.classList.contains("open");
        if (willOpen) {
            modelPickerEl.classList.add("open");
            modelPickerTriggerEl.setAttribute("aria-expanded", "true");
        } else {
            closeModelPicker();
        }
    });

    modelPickerMenuEl.querySelectorAll(".model-picker-item").forEach(function (item) {
        item.addEventListener("click", function () {
            setModelPickerValue(item.dataset.value, item.dataset.label, item.dataset.icon);
            closeModelPicker();
        });
    });

    document.addEventListener("click", function (event) {
        if (!modelPickerEl.contains(event.target)) {
            closeModelPicker();
        }
    });

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") {
            closeModelPicker();
        }
    });

    syncModelPickerFromInput();
}

function buildApiPath(path) {
    return APP_BASE_PATH + path;
}

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
function ensureHistoryResultLoaded(recordId) {
    if (!recordId) return Promise.resolve(null);
    if (currentResult && currentTaskId === recordId) return Promise.resolve(currentResult);

    return fetch(buildApiPath("/api/history/") + recordId)
        .then(function (res) { return res.json(); })
        .then(function (data) {
            if (data && !data.error && data.result) {
                currentResult = data.result;
                return currentResult;
            }
            return null;
        })
        .catch(function () { return null; });
}

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

        if (mode === "graph") {
            if (currentResult) {
                renderGraph(currentResult);
                if (typeof chartInstance !== "undefined" && chartInstance) {
                    chartInstance.resize();
                }
            } else if (currentTaskId) {
                ensureHistoryResultLoaded(currentTaskId).then(function (result) {
                    if (!result) return;
                    renderGraph(result);
                    if (typeof chartInstance !== "undefined" && chartInstance) {
                        chartInstance.resize();
                    }
                });
            }
        }

        if (mode === "text") {
            if (currentResult) {
                renderTextView(currentResult);
            } else if (currentTaskId) {
                ensureHistoryResultLoaded(currentTaskId).then(function (result) {
                    if (!result) return;
                    renderTextView(result);
                });
            }
        }

        if (mode === "logs" && currentTaskId) {
            ensureHistoryResultLoaded(currentTaskId);
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

document.getElementById("stopBtn").addEventListener("click", function () {
    forceStopTask();
});

document.getElementById("stopBtnTop").addEventListener("click", function () {
    forceStopTask();
});

document.getElementById("backToInputBtn").addEventListener("click", function () {
    setUiStage("input");
});

document.getElementById("backToGenerationBtn").addEventListener("click", function () {
    returnToProgress();
});

if (languageStyleSelectEl) {
    languageStyleSelectEl.addEventListener("change", updateLanguageStyleCustomVisibility);
    updateLanguageStyleCustomVisibility();
}

initModelPicker();

function startGeneration() {
    var form = document.getElementById("generateForm");
    var formData = new FormData(form);
    var attachmentInput = document.getElementById("attachment");
    if (attachmentInput && attachmentInput.files && attachmentInput.files.length) {
        formData.delete("attachment");
        Array.prototype.forEach.call(attachmentInput.files, function (file) {
            formData.append("attachment", file, file.name);
        });
    }
    var submitBtn = document.getElementById("submitBtn");

    submitBtn.disabled = true;
    submitBtn.textContent = "生成中...";
    document.getElementById("newPlanBtn").style.display = "none";
    setStopButtonsState(true, false, "强制停止");
    setBackToGenerationButtonState(true);
    isGenerating = true;
    setUiStage("generation");

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

    fetch(buildApiPath("/api/generate"), { method: "POST", body: formData })
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
    eventSource = new EventSource(buildApiPath("/api/stream/") + taskId + "?from=" + start);
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
        } else if (data.type === "cancelled") {
            addLogEntry("任务已强制停止", "error");
            localStorage.removeItem(ACTIVE_TASK_STORAGE_KEY);
            updateCurrentAgentCard({
                agent_display_name: "任务终止",
                message: data.message || "任务已强制停止",
                output_preview: { status: "cancelled" },
            });
            eventSource.close();
            resetSubmitBtn(false);
        }
    };

    eventSource.onerror = function () {
        addLogEntry("连接断开，尝试获取结果...", "error");
        eventSource.close();
        setTimeout(function () {
            fetch(buildApiPath("/api/result/") + taskId)
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

                    if (data.status === "cancelled") {
                        localStorage.removeItem(ACTIVE_TASK_STORAGE_KEY);
                        addLogEntry("任务已强制停止", "error");
                        resetSubmitBtn(false);
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
    setUiStage("generation");
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

function resetSubmitBtn(showNewPlanBtn) {
    var btn = document.getElementById("submitBtn");
    var newPlanBtn = document.getElementById("newPlanBtn");
    btn.disabled = false;
    btn.textContent = "重新生成";
    isGenerating = false;
    setStopButtonsState(false, false, "强制停止");
    setBackToGenerationButtonState(false);
    document.getElementById("generatingBanner").style.display = "none";
    newPlanBtn.style.display = showNewPlanBtn ? "block" : "none";
}

function startNewPlan() {
    if (eventSource) {
        eventSource.close();
        eventSource = null;
    }

    localStorage.removeItem(ACTIVE_TASK_STORAGE_KEY);
    isGenerating = false;
    currentTaskId = null;
    currentResult = null;
    currentStepIndex = -1;
    setUiStage("input");

    document.getElementById("generateForm").reset();
    updateLanguageStyleCustomVisibility();
    syncModelPickerFromInput();

    var btn = document.getElementById("submitBtn");
    btn.disabled = false;
    btn.textContent = "开始生成教学地图";
    document.getElementById("newPlanBtn").style.display = "none";
    setBackToGenerationButtonState(false);

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

    document.querySelectorAll(".left-tab").forEach(function (b) { b.classList.remove("active"); });
    document.querySelectorAll(".left-tab-content").forEach(function (c) { c.classList.remove("active"); });
    document.querySelector('.left-tab[data-target="formTab"]').classList.add("active");
    document.getElementById("formTab").classList.add("active");
}

function restoreTaskProgressOnLoad() {
    var taskId = localStorage.getItem(ACTIVE_TASK_STORAGE_KEY);
    if (!taskId) return;

    fetch(buildApiPath("/api/result/") + taskId)
        .then(function (res) { return res.json(); })
        .then(function (data) {
            if (data.status === "running") {
                currentTaskId = taskId;
                isGenerating = true;
                setUiStage("generation");
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
                setStopButtonsState(true, false, "强制停止");
                setBackToGenerationButtonState(true);

                var progress = Array.isArray(data.progress) ? data.progress : [];
                hydrateProgressSnapshot(progress);
                connectSSE(taskId, progress.length);
                return;
            }

            if (data.status === "done" && data.result) {
                localStorage.removeItem(ACTIVE_TASK_STORAGE_KEY);
                setUiStage("generation");
                addLogEntry("刷新后已恢复完成结果", "done");
                showResult(data.result, taskId);
                resetSubmitBtn(true);
                return;
            }

            localStorage.removeItem(ACTIVE_TASK_STORAGE_KEY);
            setUiStage("input");
            resetSubmitBtn(false);
        })
        .catch(function (err) {
            addLogEntry("恢复任务失败: " + err.message, "error");
            localStorage.removeItem(ACTIVE_TASK_STORAGE_KEY);
            setUiStage("input");
            resetSubmitBtn(false);
        });
}

function forceStopTask() {
    if (!currentTaskId || !isGenerating) return;
    var submitBtn = document.getElementById("submitBtn");
    setStopButtonsState(true, true, "停止中...");
    submitBtn.textContent = "停止中...";

    fetch(buildApiPath("/api/stop/") + currentTaskId, { method: "POST" })
        .then(function (res) { return res.json(); })
        .then(function (data) {
            if (data && data.ok) {
                addLogEntry("已发送强制停止请求", "error");
                updateCurrentAgentCard({
                    agent_display_name: "任务终止中",
                    message: "已发送强制停止请求，等待当前节点中断...",
                    output_preview: { status: "cancelling" },
                });
                return;
            }
            throw new Error((data && data.error) || "停止请求失败");
        })
        .catch(function (err) {
            addLogEntry("强制停止失败: " + err.message, "error");
            setStopButtonsState(true, false, "强制停止");
            submitBtn.textContent = "生成中...";
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
    AGENT_TRACKER_STEPS.forEach(function (step, idx) {
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
    // stepIdx 基于 AGENT_STEPS，需转换为 AGENT_TRACKER_STEPS 的当前进度
    var currentAgentKey = AGENT_STEPS[stepIdx] || "";
    AGENT_TRACKER_STEPS.forEach(function (step, trackerIdx) {
        var item = document.getElementById("stepItem-" + step);
        if (!item) return;
        item.classList.remove("is-active", "is-done");

        if (done) {
            item.classList.add("is-done");
            return;
        }
        var trackerStepInAll = AGENT_STEPS.indexOf(step);
        if (trackerStepInAll < stepIdx) {
            item.classList.add("is-done");
        } else if (step === currentAgentKey) {
            item.classList.add("is-active");
        }
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

    // 状态标签
    if (agentStatus) {
        agentStatus.className = "current-agent-status";
        var failCountMatch = msg.match(/失败\s*[:：]?\s*(\d+)/);
        var failCount = failCountMatch ? parseInt(failCountMatch[1], 10) : null;
        var hasHardFailure = msg.indexOf("未通过") !== -1
            || msg.indexOf("执行失败") !== -1
            || msg.indexOf("生成出错") !== -1
            || msg.indexOf("任务已强制停止") !== -1;
        if (msg.indexOf("通过") !== -1 && msg.indexOf("未通过") === -1) {
            agentStatus.textContent = "通过";
            agentStatus.classList.add("passed");
        } else if (hasHardFailure || (failCount !== null && failCount > 0)) {
            agentStatus.textContent = "未通过";
            agentStatus.classList.add("failed");
        } else if (msg.indexOf("完成") !== -1 || msg.indexOf("生成了") !== -1) {
            agentStatus.textContent = "完成";
            agentStatus.classList.add("passed");
        } else {
            agentStatus.textContent = "运行中";
            agentStatus.classList.add("running");
        }
    }

    if (agentInput) {
        agentInput.innerHTML = renderIoContent(payload.input_preview, "—");
    }
    agentOutput.innerHTML = renderIoContent(payload.output_preview, "等待执行...");
}

function renderIoContent(data, emptyText) {
    if (!data || (typeof data === "object" && Object.keys(data).length === 0)) {
        return '<span class="json-meta">' + emptyText + '</span>';
    }
    if (typeof data === "string") {
        return escapeHtml(data);
    }
    return syntaxHighlight(data);
}

function syntaxHighlight(obj) {
    var json = "";
    try {
        json = JSON.stringify(obj, null, 2);
    } catch (e) {
        return escapeHtml(String(obj));
    }
    return json.replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g, function (match) {
        var cls = "json-num";
        if (/^"/.test(match)) {
            if (/:$/.test(match)) {
                cls = "json-key";
            } else {
                cls = "json-str";
            }
        } else if (/true|false/.test(match)) {
            cls = "json-bool";
        } else if (/null/.test(match)) {
            cls = "json-null";
        }
        return '<span class="' + cls + '">' + escapeHtml(match) + '</span>';
    });
}

// ---------------------------------------------------------------------------
// Show result (graph + text + logs)
// ---------------------------------------------------------------------------
function showResult(result, taskId) {
    currentResult = result;
    if (taskId) currentTaskId = taskId;
    setUiStage("generation");
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

    fetch(buildApiPath("/api/logs/") + taskId)
        .then(function (res) { return res.json(); })
        .then(function (logs) {
            if (!logs || !logs.length) {
                container.innerHTML = '<p class="logs-empty">暂无日志记录</p>';
                return;
            }
            var html = '<div class="logs-summary"><p>共 <strong>' + logs.length + '</strong> 个Agent执行记录</p></div>';
            logs.forEach(function (log, idx) {
                var output = log.output || {};
                var inputData = output.input_preview || null;
                var outputData = output.output || output;
                // 如果 output 含有 input_preview 字段，移除它避免重复
                if (outputData && outputData.input_preview) {
                    outputData = Object.assign({}, outputData);
                    delete outputData.input_preview;
                }

                html += '<div class="log-block">';
                html += '<div class="log-block-header">';
                html += '<span class="log-step">步骤 ' + log.step_number + '</span>';
                html += '<span class="log-agent-name">' + log.agent_name + '</span>';
                html += '<span class="log-time">' + log.created_at + '</span>';
                html += '<button class="log-toggle" onclick="toggleLogDetail(this)">展开</button>';
                html += '</div>';
                html += '<div class="log-block-body" style="display:none;">';
                html += '<div class="log-io-grid">';
                // Input panel
                html += '<div class="log-io-panel">';
                html += '<div class="log-io-head"><span class="io-icon io-in">IN</span>输入</div>';
                html += '<div class="log-io-body">' + renderIoContent(inputData, "无输入预览") + '</div>';
                html += '</div>';
                // Output panel
                html += '<div class="log-io-panel">';
                html += '<div class="log-io-head"><span class="io-icon io-out">OUT</span>输出</div>';
                html += '<div class="log-io-body">' + renderIoContent(outputData, "无输出") + '</div>';
                html += '</div>';
                html += '</div>';
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

function renderMarkdownHtml(text) {
    var source = text == null ? "" : String(text);
    if (!source) return "";

    if (typeof marked !== "undefined" && marked && typeof marked.parse === "function") {
        if (!markdownOptionsApplied && typeof marked.setOptions === "function") {
            marked.setOptions({ gfm: true, breaks: true });
            markdownOptionsApplied = true;
        }
        var rendered = marked.parse(source);
        if (typeof DOMPurify !== "undefined" && DOMPurify && typeof DOMPurify.sanitize === "function") {
            return DOMPurify.sanitize(rendered, { USE_PROFILES: { html: true } });
        }
        return escapeHtml(source).replace(/\n/g, "<br>");
    }

    return escapeHtml(source).replace(/\n/g, "<br>");
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
        html += '<span class="text-id">' + escapeHtml(String(mainNode.id || "")) + '</span>';
        html += '</div>';
        html += '<div class="text-block-body">';
        html += '<div class="text-question markdown-content">' + renderMarkdownHtml(mainNode.content || "") + '</div>';
        html += renderMeta(mainNode);
        html += renderCommentaryBlock(mainNode);
        html += '</div>';

        var relatedVariants = variantNodes.filter(function (v) {
            return (v.main_id || v.parent_id) === mainNode.id;
        });
        if (relatedVariants.length > 0) {
            html += '<div class="text-sub-group">';
            html += '<div class="text-sub-label variant-label">变式问题</div>';
            relatedVariants.forEach(function (v) {
                html += '<div class="text-block text-variant">';
                html += '<div class="text-block-header variant-header">';
                html += '<span class="text-tag tag-variant">变式</span>';
                html += '<span class="text-id">' + escapeHtml(String(v.id || "")) + '</span>';
                if (v.variation_type) html += '<span class="text-vtype">' + escapeHtml(String(v.variation_type)) + '</span>';
                html += '</div>';
                html += '<div class="text-block-body">';
                html += '<div class="text-question markdown-content">' + renderMarkdownHtml(v.content || "") + '</div>';
                html += renderMeta(v);
                html += renderCommentaryBlock(v);
                html += '</div></div>';
            });
            html += '</div>';
        }

        if (idx < mainOrder.length - 1) {
            var nextMain = mainOrder[idx + 1];
            var relatedScaffolds = scaffoldNodes.filter(function (s) {
                var fromId = s.from_id || s.from_main_id;
                var toId = s.to_id || s.to_main_id;
                return fromId === mainNode.id || toId === nextMain.id;
            });
            if (relatedScaffolds.length > 0) {
                html += '<div class="text-sub-group">';
                html += '<div class="text-sub-label scaffold-label">支架问题（过渡到下一主干）</div>';
                relatedScaffolds.forEach(function (s) {
                    html += '<div class="text-block text-scaffold">';
                    html += '<div class="text-block-header scaffold-header">';
                    html += '<span class="text-tag tag-scaffold">支架</span>';
                    html += '<span class="text-id">' + escapeHtml(String(s.id || "")) + '</span>';
                    html += '</div>';
                    html += '<div class="text-block-body">';
                    html += '<div class="text-question markdown-content">' + renderMarkdownHtml(s.content || "") + '</div>';
                    html += renderMeta(s);
                    html += renderCommentaryBlock(s);
                    if (s.bridge_function) html += '<div class="text-bridge markdown-content"><strong>桥梁功能：</strong>' + renderMarkdownHtml(s.bridge_function) + '</div>';
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
    var designIntent = node.design_intent || node.design_rationale || "";
    if (node.knowledge_points && node.knowledge_points.length) {
        html += '<span>知识点：' + escapeHtml(node.knowledge_points.join("、")) + '</span>';
    }
    var cl = node.cognitive_level || node.bloom_level || "";
    var clLabel = COGNITIVE_LABELS[cl] || cl;
    if (clLabel) html += '<span>认知层次：' + escapeHtml(String(clLabel)) + '</span>';
    if (node.difficulty !== undefined) html += '<span>难度：' + escapeHtml(String(node.difficulty)) + '</span>';
    if (designIntent) html += '<span>设计意图：' + escapeHtml(String(designIntent)) + '</span>';
    html += '</div>';
    return html;
}

function getCommentary(node) {
    return (node && (node.lesson_presentation_script || node.commentary || node.Commentary)) || "";
}

function renderCommentaryBlock(node) {
    var commentary = getCommentary(node);
    if (!commentary) return "";
    return '<div class="text-commentary"><div class="text-commentary-title">说课稿</div><div class="text-commentary-body markdown-content">' + renderMarkdownHtml(commentary) + '</div></div>';
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
function bindHistoryListEvents() {
    if (historyEventsBound) return;
    var list = document.getElementById("historyList");
    if (!list) return;
    list.addEventListener("click", function (event) {
        var btn = event.target.closest("button");
        if (!btn) return;
        var item = btn.closest(".history-item");
        if (!item) return;
        var recordId = item.getAttribute("data-id");
        if (!recordId) return;

        if (btn.classList.contains("btn-view")) {
            loadHistoryItem(recordId);
            return;
        }
        if (btn.classList.contains("btn-input")) {
            toggleHistoryInput(recordId, btn, event);
            return;
        }
        if (btn.classList.contains("btn-logs")) {
            loadHistoryLogs(recordId, event);
            return;
        }
        if (btn.classList.contains("btn-delete")) {
            deleteHistoryItem(recordId, event);
        }
    });
    historyEventsBound = true;
}

function loadHistory() {
    bindHistoryListEvents();
    fetch(buildApiPath("/api/history"))
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
                var safeGoals = escapeHtml(goals + (goals.length >= 60 ? "..." : ""));
                var modelDisplayName = escapeHtml(item.model_display_name || "未知模型");
                html += '<div class="history-item" data-id="' + item.id + '">';
                html += '<div class="history-item-header">';
                html += '<span class="history-subject">' + item.subject + ' · ' + item.grade + '</span>';
                html += '<span class="history-time">' + item.created_at + '</span>';
                html += '</div>';
                html += '<div class="history-goals">' + safeGoals + '</div>';
                html += '<div class="history-model">生成模型：' + modelDisplayName + '</div>';
                html += '<div class="history-actions">';
                html += '<button class="btn-sm btn-view" type="button">查看</button>';
                html += '<button class="btn-sm btn-input" type="button">输入</button>';
                html += '<button class="btn-sm btn-logs" type="button">日志</button>';
                html += '<button class="btn-sm btn-delete" type="button">删除</button>';
                html += '</div>';
                html += '<div class="history-input-detail" id="historyInputDetail-' + item.id + '" style="display:none;"></div>';
                html += '</div>';
            });
            container.innerHTML = html;
        });
}

function toggleHistoryInput(recordId, btn, event) {
    if (event && typeof event.stopPropagation === "function") event.stopPropagation();
    var detail = document.getElementById("historyInputDetail-" + recordId);
    if (!detail) return;

    if (detail.style.display === "block") {
        detail.style.display = "none";
        btn.textContent = "输入";
        return;
    }

    if (detail.dataset.loaded === "1") {
        detail.style.display = "block";
        btn.textContent = "收起输入";
        return;
    }

    detail.innerHTML = '<div class="history-input-loading">加载输入信息...</div>';
    detail.style.display = "block";
    btn.textContent = "收起输入";

    fetch(buildApiPath("/api/history/") + recordId)
        .then(function (res) { return res.json(); })
        .then(function (data) {
            if (data.error) {
                detail.innerHTML = '<div class="history-input-loading">加载失败</div>';
                return;
            }

            var goals = escapeHtml(data.teaching_goals || "未填写");
            var profile = escapeHtml(data.student_profile || "未填写");
            var difficulty = escapeHtml(data.difficulty_analysis || "未填写");
            var style = escapeHtml(data.language_style || "未设置");
            var attachment = data.attachment ? escapeHtml(String(data.attachment).substring(0, 200)) : "无";

            var html = '';
            html += '<div class="history-input-title">教师输入信息</div>';
            html += '<div class="history-input-row"><span class="history-input-label">学科：</span><span class="history-input-value">' + escapeHtml(data.subject || "") + '</span></div>';
            html += '<div class="history-input-row"><span class="history-input-label">年级：</span><span class="history-input-value">' + escapeHtml(data.grade || "") + '</span></div>';
            html += '<div class="history-input-row"><span class="history-input-label">语言风格：</span><span class="history-input-value">' + style + '</span></div>';
            html += '<div class="history-input-row"><span class="history-input-label">教学目标：</span><span class="history-input-value">' + goals + '</span></div>';
            html += '<div class="history-input-row"><span class="history-input-label">学情描述：</span><span class="history-input-value">' + profile + '</span></div>';
            html += '<div class="history-input-row"><span class="history-input-label">重难点分析：</span><span class="history-input-value">' + difficulty + '</span></div>';
            html += '<div class="history-input-row"><span class="history-input-label">附件：</span><span class="history-input-value">' + attachment + '</span></div>';

            detail.innerHTML = html;
            detail.dataset.loaded = "1";
        })
        .catch(function () {
            detail.innerHTML = '<div class="history-input-loading">加载失败</div>';
        });
}

function loadHistoryItem(recordId) {
    currentTaskId = recordId;
    fetch(buildApiPath("/api/history/") + recordId)
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
    if (event && typeof event.stopPropagation === "function") event.stopPropagation();
    currentTaskId = recordId;
    setUiStage("generation");
    document.getElementById("placeholder").style.display = "none";
    document.getElementById("progressSection").style.display = "none";
    document.getElementById("viewTabs").style.display = "flex";
    document.querySelectorAll(".view-tab").forEach(function (b) { b.classList.remove("active"); });
    document.querySelector('.view-tab[data-view="logs"]').classList.add("active");
    document.getElementById("graphSection").style.display = "none";
    document.getElementById("textSection").style.display = "none";
    document.getElementById("logsSection").style.display = "block";
    document.getElementById("detailSection").style.display = "none";
    ensureHistoryResultLoaded(recordId);
    loadAgentLogs(recordId);
}

function deleteHistoryItem(recordId, event) {
    if (event && typeof event.stopPropagation === "function") event.stopPropagation();
    if (!confirm("确定删除此记录？")) return;
    fetch(buildApiPath("/api/history/") + recordId, { method: "DELETE" })
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
