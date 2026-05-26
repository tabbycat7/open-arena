/**
 * mat_main.js — 多智能体教学地图：表单提交、SSE、进度、历史、文字视图、日志
 */

var AGENT_STEPS = [
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
    "priority_assignment",
];

var AGENT_TRACKER_STEPS = [
    "learning_analysis",
    "teaching_logic_design",
    "main_question_chain",
    "main_question_check",
    "variant_question",
    "variant_check",
    "scaffold_question",
    "scaffold_check",
    "map_integration",
    "priority_assignment",
];

var AGENT_DISPLAY_NAMES = {
    learning_analysis: "学情与目标解析",
    teaching_logic_design: "教学蓝图规划",
    main_question_chain: "主干问题链构建",
    main_question_check: "主干问题综合校验",
    variant_question: "变式问题生成",
    variant_check: "变式问题检验",
    scaffold_question: "支架问题生成",
    scaffold_check: "支架问题检验",
    map_integration: "教学地图整合",
    priority_assignment: "调度优先级分配",
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
var generationStartTimestampMs = null;
var generationDurationFinalSeconds = null;
var generationDurationTimer = null;
var ACTIVE_TASK_STORAGE_KEY = "teaching_map_active_task_id";
var historyEventsBound = false;
var workspaceLayoutEl = document.getElementById("workspaceLayout");
var languageStyleSelectEl = document.getElementById("language_style");
var customLanguageWrapEl = document.getElementById("languageStyleCustomWrap");
var customLanguageInputEl = document.getElementById("custom_language_style");
var modelPickerEl = document.getElementById("modelPicker");
var modelPickerTriggerEl = document.getElementById("modelPickerTrigger");
var modelPickerMenuEl = document.getElementById("modelPickerMenu");
var modelPickerLabelEl = document.getElementById("modelPickerLabel");
var modelPickerIconEl = document.getElementById("modelPickerIcon");
var modelIdInputEl = document.getElementById("model_id");
var temperatureInputEl = document.getElementById("temperature");
var temperatureValueEl = document.getElementById("temperatureValue");
var temperatureHintEl = document.getElementById("temperatureHint");
var fixedTemperatureModels = window.MAT_FIXED_TEMPERATURE_MODELS || {};
var defaultTemperature = Number(window.MAT_DEFAULT_TEMPERATURE);
var markdownOptionsApplied = false;
var managedFiles = [];
var lastInputRecordId = null;

var LANGUAGE_STYLE_PRESETS = ["严谨学术", "生动活泼", "通俗易懂", "启发引导"];

var API_PREFIX = "/api/mat";

function formatDurationClock(totalSeconds) {
    var safeSeconds = Math.max(0, Math.round(totalSeconds));
    var hours = Math.floor(safeSeconds / 3600);
    var minutes = Math.floor((safeSeconds % 3600) / 60);
    var seconds = safeSeconds % 60;
    if (hours > 0) {
        return String(hours).padStart(2, "0") + ":" + String(minutes).padStart(2, "0") + ":" + String(seconds).padStart(2, "0");
    }
    return String(minutes).padStart(2, "0") + ":" + String(seconds).padStart(2, "0");
}

function renderGenerationDurationText() {
    var el = document.getElementById("generationDurationText");
    if (!el) return;

    if (typeof generationDurationFinalSeconds === "number" && isFinite(generationDurationFinalSeconds)) {
        el.textContent = "本次用时：" + formatDurationClock(generationDurationFinalSeconds);
        return;
    }

    if (typeof generationStartTimestampMs === "number" && isFinite(generationStartTimestampMs)) {
        var elapsedSeconds = (Date.now() - generationStartTimestampMs) / 1000;
        el.textContent = "本次用时：" + formatDurationClock(elapsedSeconds);
        return;
    }

    el.textContent = "本次用时：--";
}

function clearGenerationDurationTicker() {
    if (generationDurationTimer) {
        clearInterval(generationDurationTimer);
        generationDurationTimer = null;
    }
}

function startGenerationDurationTimer(startTimestampMs) {
    var parsedStart = Number(startTimestampMs);
    if (!isFinite(parsedStart) || parsedStart <= 0) {
        parsedStart = Date.now();
    }
    generationStartTimestampMs = parsedStart;
    generationDurationFinalSeconds = null;
    clearGenerationDurationTicker();
    renderGenerationDurationText();
    generationDurationTimer = setInterval(function () {
        renderGenerationDurationText();
    }, 1000);
}

function finalizeGenerationDuration(durationSeconds) {
    var parsedDuration = Number(durationSeconds);
    if (isFinite(parsedDuration) && parsedDuration >= 0) {
        generationDurationFinalSeconds = parsedDuration;
    } else if (typeof generationStartTimestampMs === "number" && isFinite(generationStartTimestampMs)) {
        generationDurationFinalSeconds = Math.max(0, (Date.now() - generationStartTimestampMs) / 1000);
    } else {
        generationDurationFinalSeconds = null;
    }
    clearGenerationDurationTicker();
    renderGenerationDurationText();
}

function resetGenerationDurationDisplay() {
    generationStartTimestampMs = null;
    generationDurationFinalSeconds = null;
    clearGenerationDurationTicker();
    renderGenerationDurationText();
}

function normalizeStartedAtMs(rawStartedAtTs) {
    var parsed = Number(rawStartedAtTs);
    if (!isFinite(parsed) || parsed <= 0) {
        return Date.now();
    }
    return parsed * 1000;
}

function setUiStage(stage) {
    if (!workspaceLayoutEl) return;
    workspaceLayoutEl.classList.remove("mat-stage-input", "mat-stage-generation");
    if (stage === "generation") {
        workspaceLayoutEl.classList.add("mat-stage-generation");
        return;
    }
    workspaceLayoutEl.classList.add("mat-stage-input");
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

function normalizeTemperatureValue(value, fallback) {
    var parsed = Number(value);
    if (!isFinite(parsed)) parsed = fallback;
    if (!isFinite(parsed)) parsed = 0.7;
    if (parsed < 0) parsed = 0;
    if (parsed > 2) parsed = 2;
    return parsed;
}

function formatTemperatureValue(value) {
    var normalized = normalizeTemperatureValue(value, 0.7);
    return String(Math.round(normalized * 100) / 100);
}

function syncTemperatureSliderUi() {
    if (!temperatureInputEl) return;
    var fallback = normalizeTemperatureValue(defaultTemperature, 0.7);
    var normalized = normalizeTemperatureValue(temperatureInputEl.value, fallback);
    temperatureInputEl.value = formatTemperatureValue(normalized);
    if (temperatureValueEl) {
        temperatureValueEl.textContent = formatTemperatureValue(normalized);
    }
    var min = normalizeTemperatureValue(temperatureInputEl.min, 0);
    var max = normalizeTemperatureValue(temperatureInputEl.max, 2);
    var percent = 0;
    if (max > min) {
        percent = ((normalized - min) / (max - min)) * 100;
    }
    if (!isFinite(percent)) {
        percent = 0;
    }
    percent = Math.max(0, Math.min(100, percent));
    temperatureInputEl.style.setProperty("--value-percent", percent.toFixed(2) + "%");
}

function handleTemperatureInputChange() {
    if (!temperatureInputEl) return;
    var locked = temperatureInputEl.dataset.locked === "1";
    if (locked) {
        var fixedValue = temperatureInputEl.dataset.fixedValue || "1";
        temperatureInputEl.value = fixedValue;
    } else {
        var fallback = normalizeTemperatureValue(defaultTemperature, 0.7);
        temperatureInputEl.value = formatTemperatureValue(
            normalizeTemperatureValue(temperatureInputEl.value, fallback)
        );
    }
    syncTemperatureSliderUi();
}

function updateTemperatureControlForModel(modelId) {
    if (!temperatureInputEl) return;

    var key = modelId || "";
    var hasFixed = Object.prototype.hasOwnProperty.call(fixedTemperatureModels, key);
    if (hasFixed) {
        var fixedValue = normalizeTemperatureValue(fixedTemperatureModels[key], 1);
        temperatureInputEl.value = formatTemperatureValue(fixedValue);
        temperatureInputEl.dataset.locked = "1";
        temperatureInputEl.dataset.fixedValue = formatTemperatureValue(fixedValue);
        temperatureInputEl.setAttribute("aria-disabled", "true");
        temperatureInputEl.classList.add("is-locked");
        syncTemperatureSliderUi();
        if (temperatureHintEl) {
            temperatureHintEl.textContent = "当前模型固定 temperature=" + formatTemperatureValue(fixedValue) + "，不可修改。";
        }
        return;
    }

    temperatureInputEl.dataset.locked = "0";
    delete temperatureInputEl.dataset.fixedValue;
    temperatureInputEl.removeAttribute("aria-disabled");
    temperatureInputEl.classList.remove("is-locked");
    if (!temperatureInputEl.value) {
        var fallback = normalizeTemperatureValue(defaultTemperature, 0.7);
        temperatureInputEl.value = formatTemperatureValue(fallback);
    }
    syncTemperatureSliderUi();
    if (temperatureHintEl) {
        temperatureHintEl.textContent = "控制生成随机性，范围 0~2，数值越高越发散。";
    }
}

function setModelPickerValue(modelId, label, iconUrl) {
    if (modelIdInputEl) modelIdInputEl.value = modelId || "";
    if (modelPickerLabelEl) modelPickerLabelEl.textContent = label || "请选择模型";
    if (modelPickerIconEl && iconUrl) modelPickerIconEl.src = iconUrl;
    updateTemperatureControlForModel(modelId || "");

    if (!modelPickerMenuEl) return;
    modelPickerMenuEl.querySelectorAll(".mat-model-picker-item").forEach(function (item) {
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
    var target = modelPickerMenuEl.querySelector('.mat-model-picker-item[data-value="' + modelIdInputEl.value + '"]');
    if (!target) {
        target = modelPickerMenuEl.querySelector(".mat-model-picker-item");
    }
    if (!target) return;
    setModelPickerValue(target.dataset.value, target.dataset.label, target.dataset.icon);
}

function initModelPicker() {
    if (!modelPickerEl || !modelPickerTriggerEl || !modelPickerMenuEl || !modelIdInputEl) {
        updateTemperatureControlForModel(modelIdInputEl ? modelIdInputEl.value : "");
        return;
    }

    modelPickerTriggerEl.addEventListener("click", function () {
        var willOpen = !modelPickerEl.classList.contains("open");
        if (willOpen) {
            modelPickerEl.classList.add("open");
            modelPickerTriggerEl.setAttribute("aria-expanded", "true");
        } else {
            closeModelPicker();
        }
    });

    modelPickerMenuEl.querySelectorAll(".mat-model-picker-item").forEach(function (item) {
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

if (temperatureInputEl) {
    if (!isFinite(defaultTemperature)) {
        defaultTemperature = 0.7;
    }
    if (!temperatureInputEl.value) {
        temperatureInputEl.value = formatTemperatureValue(defaultTemperature);
    }
    syncTemperatureSliderUi();
    temperatureInputEl.addEventListener("input", handleTemperatureInputChange);
    temperatureInputEl.addEventListener("change", handleTemperatureInputChange);
}

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
function ensureHistoryResultLoaded(recordId) {
    if (!recordId) return Promise.resolve(null);
    if (currentResult && currentTaskId === recordId) return Promise.resolve(currentResult);

    return fetch(API_PREFIX + "/history/" + recordId)
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

// ---------------------------------------------------------------------------
// Form step indicator + scroll highlight (IntersectionObserver)
// ---------------------------------------------------------------------------
(function initFormStepper() {
    var stepButtons = document.querySelectorAll(".mat-form-step");
    var sections = document.querySelectorAll(".mat-form-section[data-section]");
    if (!stepButtons.length || !sections.length) return;

    stepButtons.forEach(function (btn) {
        btn.addEventListener("click", function () {
            var stepNum = btn.dataset.step;
            var target = document.querySelector('.mat-form-section[data-section="' + stepNum + '"]');
            if (target) target.scrollIntoView({ behavior: "smooth", block: "center" });
        });
    });

    if ("IntersectionObserver" in window) {
        var observer = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (entry.isIntersecting) {
                    var secNum = entry.target.dataset.section;
                    stepButtons.forEach(function (b) {
                        b.classList.toggle("is-active", b.dataset.step === secNum);
                    });
                }
            });
        }, { rootMargin: "-30% 0px -50% 0px", threshold: 0 });

        sections.forEach(function (sec) { observer.observe(sec); });
    }
})();

// ---------------------------------------------------------------------------
// Progress ring — tracks required-field completion
// ---------------------------------------------------------------------------
(function initProgressRing() {
    var ring = document.getElementById("formProgressRing");
    var text = document.getElementById("formProgressText");
    if (!ring || !text) return;

    var CIRCUMFERENCE = 2 * Math.PI * 16;
    ring.setAttribute("stroke-dasharray", CIRCUMFERENCE.toFixed(2));
    ring.setAttribute("stroke-dashoffset", CIRCUMFERENCE.toFixed(2));

    var requiredFields = document.querySelectorAll("#generateForm [required]");

    function update() {
        if (!requiredFields.length) return;
        var filled = 0;
        requiredFields.forEach(function (f) {
            if (f.tagName === "SELECT") { if (f.value) filled++; }
            else if (f.value && f.value.trim()) filled++;
        });
        var ratio = filled / requiredFields.length;
        var offset = CIRCUMFERENCE * (1 - ratio);
        ring.setAttribute("stroke-dashoffset", offset.toFixed(2));
        text.textContent = Math.round(ratio * 100) + "%";

        var stepButtons = document.querySelectorAll(".mat-form-step");
        stepButtons.forEach(function (btn) {
            var secNum = btn.dataset.step;
            var sec = document.querySelector('.mat-form-section[data-section="' + secNum + '"]');
            if (!sec) return;
            var fields = sec.querySelectorAll("[required]");
            var allFilled = fields.length > 0;
            fields.forEach(function (f) {
                if (f.tagName === "SELECT") { if (!f.value) allFilled = false; }
                else if (!f.value || !f.value.trim()) allFilled = false;
            });
            btn.classList.toggle("is-done", allFilled && fields.length > 0);
        });
    }

    requiredFields.forEach(function (f) {
        f.addEventListener("input", update);
        f.addEventListener("change", update);
    });
    update();
})();

// ---------------------------------------------------------------------------
// Drag-and-drop upload zone
// ---------------------------------------------------------------------------
(function initDropzone() {
    var dropzone = document.getElementById("dropzone");
    var fileInput = document.getElementById("attachment");
    var tagsContainer = document.getElementById("fileTags");
    if (!dropzone || !fileInput || !tagsContainer) return;

    function syncInputFiles() {
        var dt = new DataTransfer();
        managedFiles.forEach(function (f) { dt.items.add(f); });
        fileInput.files = dt.files;
    }

    function renderTags() {
        var html = "";
        managedFiles.forEach(function (file, idx) {
            html += '<span class="mat-file-tag">' + escapeHtml(file.name) +
                '<button type="button" class="mat-file-tag-remove" data-idx="' + idx + '">&times;</button></span>';
        });
        tagsContainer.innerHTML = html;
    }

    function addFiles(fileList) {
        var existingNames = managedFiles.map(function (f) { return f.name; });
        Array.prototype.forEach.call(fileList, function (f) {
            if (existingNames.indexOf(f.name) === -1) {
                managedFiles.push(f);
                existingNames.push(f.name);
            }
        });
        syncInputFiles();
        renderTags();
    }

    fileInput.addEventListener("change", function () {
        if (fileInput.files.length) addFiles(fileInput.files);
    });

    dropzone.addEventListener("dragover", function (e) {
        e.preventDefault();
        dropzone.classList.add("is-dragover");
    });
    dropzone.addEventListener("dragleave", function () {
        dropzone.classList.remove("is-dragover");
    });
    dropzone.addEventListener("drop", function (e) {
        e.preventDefault();
        dropzone.classList.remove("is-dragover");
        if (e.dataTransfer && e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
    });

    tagsContainer.addEventListener("click", function (e) {
        var btn = e.target.closest(".mat-file-tag-remove");
        if (!btn) return;
        var idx = parseInt(btn.dataset.idx, 10);
        if (!isNaN(idx) && idx >= 0 && idx < managedFiles.length) {
            managedFiles.splice(idx, 1);
            syncInputFiles();
            renderTags();
        }
    });
})();

// ---------------------------------------------------------------------------
// Load last input from history
// ---------------------------------------------------------------------------
function clearManagedAttachments() {
    managedFiles = [];
    var fileTags = document.getElementById("fileTags");
    if (fileTags) fileTags.innerHTML = "";
    var attachment = document.getElementById("attachment");
    if (attachment) attachment.value = "";
}

function triggerFormProgressRefresh() {
    document.querySelectorAll("#generateForm [required]").forEach(function (field) {
        field.dispatchEvent(new Event("input", { bubbles: true }));
        field.dispatchEvent(new Event("change", { bubbles: true }));
    });
}

function applyMatInputRecord(record) {
    if (!record) return;

    var subjectEl = document.getElementById("subject");
    var gradeEl = document.getElementById("grade");
    var goalsEl = document.getElementById("teaching_goals");
    var profileEl = document.getElementById("student_profile");
    var difficultyEl = document.getElementById("difficulty_analysis");

    if (subjectEl) subjectEl.value = record.subject || "";
    if (gradeEl) gradeEl.value = record.grade || "";
    if (goalsEl) goalsEl.value = record.teaching_goals || "";
    if (profileEl) profileEl.value = record.student_profile || "";
    if (difficultyEl) difficultyEl.value = record.difficulty_analysis || "";

    var style = (record.language_style || "").trim() || "严谨学术";
    if (languageStyleSelectEl) {
        if (LANGUAGE_STYLE_PRESETS.indexOf(style) >= 0) {
            languageStyleSelectEl.value = style;
            if (customLanguageInputEl) customLanguageInputEl.value = "";
        } else {
            languageStyleSelectEl.value = "自定义";
            if (customLanguageInputEl) customLanguageInputEl.value = style;
        }
        updateLanguageStyleCustomVisibility();
    }

    var modelId = (record.model_id || "").trim();
    if (modelId && modelPickerMenuEl) {
        var pickerItem = null;
        modelPickerMenuEl.querySelectorAll(".mat-model-picker-item").forEach(function (el) {
            if (el.dataset.value === modelId) pickerItem = el;
        });
        if (pickerItem) {
            setModelPickerValue(modelId, pickerItem.dataset.label, pickerItem.dataset.icon);
        } else if (modelIdInputEl) {
            modelIdInputEl.value = modelId;
            if (modelPickerLabelEl) modelPickerLabelEl.textContent = modelId;
            updateTemperatureControlForModel(modelId);
        }
    }

    clearManagedAttachments();
    triggerFormProgressRefresh();
}

function switchToFormTab() {
    var formTabBtn = document.querySelector('.mat-left-tab[data-target="formTab"]');
    if (formTabBtn && !formTabBtn.classList.contains("active")) {
        formTabBtn.click();
    }
}

function setLoadLastInputButtonMeta(enabled, title) {
    var btn = document.getElementById("loadLastInputBtn");
    if (!btn) return;
    btn.disabled = !enabled;
    if (title) btn.title = title;
}

function refreshLoadLastInputAvailability() {
    return fetch(API_PREFIX + "/history")
        .then(function (res) {
            return res.json().then(function (data) {
                return { ok: res.ok, status: res.status, data: data };
            });
        })
        .then(function (payload) {
            if (payload.status === 401) {
                lastInputRecordId = null;
                setLoadLastInputButtonMeta(false, "请先登录后使用");
                return;
            }
            if (!payload.ok || !Array.isArray(payload.data) || !payload.data.length) {
                lastInputRecordId = null;
                setLoadLastInputButtonMeta(false, "暂无历史记录可加载");
                return;
            }
            var item = payload.data[0];
            lastInputRecordId = item.id || null;
            var hint = [item.subject, item.grade, item.created_at].filter(Boolean).join(" · ");
            setLoadLastInputButtonMeta(true, hint ? "恢复最近一次输入：" + hint + "（不含附件）" : "恢复最近一次填写的教学信息（不含附件）");
        })
        .catch(function () {
            lastInputRecordId = null;
            setLoadLastInputButtonMeta(false, "历史记录暂不可用");
        });
}

function loadLastInput() {
    var btn = document.getElementById("loadLastInputBtn");
    if (!btn || btn.disabled) return;

    var textEl = btn.querySelector(".mat-load-last-text");
    var origText = textEl ? textEl.textContent : "加载上次输入";
    btn.classList.add("is-loading");
    btn.disabled = true;
    if (textEl) textEl.textContent = "加载中...";

    function finishSuccess(record) {
        applyMatInputRecord(record);
        switchToFormTab();
        btn.classList.remove("is-loading");
        btn.classList.add("is-success");
        if (textEl) textEl.textContent = "已加载";
        setTimeout(function () {
            btn.classList.remove("is-success");
            refreshLoadLastInputAvailability().then(function () {
                if (textEl) textEl.textContent = origText;
            });
        }, 1800);
    }

    function finishError(message) {
        btn.classList.remove("is-loading");
        if (textEl) textEl.textContent = origText;
        refreshLoadLastInputAvailability();
        alert(message || "加载失败");
    }

    if (lastInputRecordId) {
        fetch(API_PREFIX + "/history/" + lastInputRecordId)
            .then(function (res) { return res.json().then(function (data) { return { ok: res.ok, data: data }; }); })
            .then(function (payload) {
                if (!payload.ok || payload.data.error) {
                    finishError("无法读取上次输入记录");
                    return;
                }
                finishSuccess(payload.data);
            })
            .catch(function () { finishError("加载失败，请稍后重试"); });
        return;
    }

    fetch(API_PREFIX + "/history")
        .then(function (res) {
            return res.json().then(function (data) {
                return { ok: res.ok, status: res.status, data: data };
            });
        })
        .then(function (payload) {
            if (payload.status === 401) {
                finishError("请先登录后使用此功能");
                return;
            }
            if (!payload.ok || !Array.isArray(payload.data) || !payload.data.length) {
                finishError("暂无历史记录");
                return;
            }
            finishSuccess(payload.data[0]);
        })
        .catch(function () { finishError("加载失败，请稍后重试"); });
}

(function initLoadLastInput() {
    var btn = document.getElementById("loadLastInputBtn");
    if (!btn) return;
    btn.addEventListener("click", loadLastInput);
    refreshLoadLastInputAvailability();
})();

function setSubmitLoading(loading) {
    var btn = document.getElementById("submitBtn");
    if (!btn) return;
    var iconEl = btn.querySelector(".mat-btn-icon");
    var textEl = btn.querySelector(".mat-btn-text");
    var spinnerEl = btn.querySelector(".mat-btn-spinner");
    if (loading) {
        btn.classList.add("is-loading");
        btn.disabled = true;
        if (iconEl) iconEl.style.display = "none";
        if (textEl) textEl.textContent = "AI 正在规划...";
        if (spinnerEl) spinnerEl.style.display = "inline-flex";
    } else {
        btn.classList.remove("is-loading");
        if (iconEl) iconEl.style.display = "";
        if (spinnerEl) spinnerEl.style.display = "none";
    }
}

function startGeneration() {
    var form = document.getElementById("generateForm");
    var formData = new FormData(form);
    if (managedFiles.length) {
        formData.delete("attachment");
        managedFiles.forEach(function (file) {
            formData.append("attachment", file, file.name);
        });
    }
    var submitBtn = document.getElementById("submitBtn");

    setSubmitLoading(true);
    document.getElementById("newPlanBtn").style.display = "none";
    setStopButtonsState(true, false, "强制停止");
    setBackToGenerationButtonState(true);
    isGenerating = true;
    setUiStage("generation");

    document.getElementById("placeholder").style.display = "none";
    document.getElementById("progressSection").style.display = "block";
    document.getElementById("viewTabs").style.display = "none";
    hideNavEntryBar();
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
    startGenerationDurationTimer(Date.now());

    fetch(API_PREFIX + "/generate", { method: "POST", body: formData })
        .then(function (res) { return res.json(); })
        .then(function (data) {
            currentTaskId = data.task_id;
            localStorage.setItem(ACTIVE_TASK_STORAGE_KEY, currentTaskId);
            connectSSE(currentTaskId);
        })
        .catch(function (err) {
            addLogEntry("连接失败: " + err.message, "error");
            setSubmitLoading(false);
            submitBtn.disabled = false;
            var btnText = submitBtn.querySelector(".mat-btn-text");
            if (btnText) btnText.textContent = "开始生成教学地图";
            isGenerating = false;
            resetGenerationDurationDisplay();
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
            finalizeGenerationDuration(data.duration_seconds);
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
            finalizeGenerationDuration(data.duration_seconds);
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
            finalizeGenerationDuration(data.duration_seconds);
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
            fetch(API_PREFIX + "/result/" + taskId)
                .then(function (res) { return res.json(); })
                .then(function (data) {
                    if (data.status === "done" && data.result) {
                        finalizeGenerationDuration(data.duration_seconds);
                        localStorage.removeItem(ACTIVE_TASK_STORAGE_KEY);
                        addLogEntry("成功获取结果", "done");
                        showResult(data.result, taskId);
                        resetSubmitBtn(true);
                        return;
                    }
                    if (data.status === "running") {
                        startGenerationDurationTimer(normalizeStartedAtMs(data.started_at_ts));
                        var progress = Array.isArray(data.progress) ? data.progress : [];
                        connectSSE(taskId, progress.length);
                        return;
                    }
                    if (data.status === "cancelled") {
                        finalizeGenerationDuration(data.duration_seconds);
                        localStorage.removeItem(ACTIVE_TASK_STORAGE_KEY);
                        addLogEntry("任务已强制停止", "error");
                        resetSubmitBtn(false);
                        return;
                    }
                    finalizeGenerationDuration(data.duration_seconds);
                    localStorage.removeItem(ACTIVE_TASK_STORAGE_KEY);
                    resetSubmitBtn(false);
                })
                .catch(function () {
                    finalizeGenerationDuration();
                    localStorage.removeItem(ACTIVE_TASK_STORAGE_KEY);
                    resetSubmitBtn(false);
                });
        }, 1000);
    };
}

function returnToProgress() {
    setUiStage("generation");
    document.querySelectorAll(".mat-left-tab").forEach(function (b) { b.classList.remove("active"); });
    document.querySelectorAll(".mat-left-tab-content").forEach(function (c) { c.classList.remove("active"); });
    document.querySelector('.mat-left-tab[data-target="formTab"]').classList.add("active");
    document.getElementById("formTab").classList.add("active");

    document.getElementById("placeholder").style.display = "none";
    document.getElementById("progressSection").style.display = "block";
    document.getElementById("viewTabs").style.display = "none";
    hideNavEntryBar();
    document.getElementById("graphSection").style.display = "none";
    document.getElementById("textSection").style.display = "none";
    document.getElementById("logsSection").style.display = "none";
    document.getElementById("detailSection").style.display = "none";
    document.getElementById("generatingBanner").style.display = "none";
}

function resetSubmitBtn(showNewPlanBtn) {
    var btn = document.getElementById("submitBtn");
    var newPlanBtn = document.getElementById("newPlanBtn");
    setSubmitLoading(false);
    btn.disabled = false;
    var btnText = btn.querySelector(".mat-btn-text");
    if (btnText) btnText.textContent = "重新生成";
    isGenerating = false;
    if (showNewPlanBtn) refreshLoadLastInputAvailability();
    clearGenerationDurationTicker();
    setStopButtonsState(false, false, "强制停止");
    setBackToGenerationButtonState(false);
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
    resetGenerationDurationDisplay();
    setUiStage("input");

    document.getElementById("generateForm").reset();
    clearManagedAttachments();
    updateLanguageStyleCustomVisibility();
    syncModelPickerFromInput();
    var btn = document.getElementById("submitBtn");
    setSubmitLoading(false);
    btn.disabled = false;
    var btnText = btn.querySelector(".mat-btn-text");
    if (btnText) btnText.textContent = "开始生成教学地图";
    document.getElementById("newPlanBtn").style.display = "none";
    setBackToGenerationButtonState(false);
    document.getElementById("progressLog").innerHTML = "";
    document.getElementById("progressBar").style.width = "0%";
    document.getElementById("stepTracker").innerHTML = "";

    document.getElementById("placeholder").style.display = "flex";
    document.getElementById("progressSection").style.display = "none";
    document.getElementById("viewTabs").style.display = "none";
    hideNavEntryBar();
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

function getRecordIdFromQuery() {
    try {
        return new URLSearchParams(window.location.search).get("record");
    } catch (e) {
        return null;
    }
}

function openRecordFromQueryOnLoad() {
    var recordId = getRecordIdFromQuery();
    if (!recordId) return false;
    loadHistoryItem(recordId);
    return true;
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
                startGenerationDurationTimer(normalizeStartedAtMs(data.started_at_ts));
                setUiStage("generation");
                document.getElementById("placeholder").style.display = "none";
                document.getElementById("progressSection").style.display = "block";
                document.getElementById("viewTabs").style.display = "none";
                hideNavEntryBar();
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
                setSubmitLoading(true);
                setStopButtonsState(true, false, "强制停止");
                setBackToGenerationButtonState(true);
                var progress = Array.isArray(data.progress) ? data.progress : [];
                hydrateProgressSnapshot(progress);
                connectSSE(taskId, progress.length);
                return;
            }
            if (data.status === "done" && data.result) {
                finalizeGenerationDuration(data.duration_seconds);
                localStorage.removeItem(ACTIVE_TASK_STORAGE_KEY);
                setUiStage("generation");
                addLogEntry("刷新后已恢复完成结果", "done");
                showResult(data.result, taskId);
                resetSubmitBtn(true);
                return;
            }
            finalizeGenerationDuration(data.duration_seconds);
            localStorage.removeItem(ACTIVE_TASK_STORAGE_KEY);
            setUiStage("input");
            resetSubmitBtn(false);
        })
        .catch(function (err) {
            addLogEntry("恢复任务失败: " + err.message, "error");
            resetGenerationDurationDisplay();
            localStorage.removeItem(ACTIVE_TASK_STORAGE_KEY);
            setUiStage("input");
            resetSubmitBtn(false);
        });
}

function forceStopTask() {
    if (!currentTaskId || !isGenerating) return;
    setStopButtonsState(true, true, "停止中...");

    fetch(API_PREFIX + "/stop/" + currentTaskId, { method: "POST" })
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
    var agentIdxInFlow = AGENT_STEPS.indexOf(payload.agent || "");
    var displayStep = 0;
    if (agentIdxInFlow >= 0) {
        displayStep = agentIdxInFlow + 1;
    } else if (currentStepIndex >= 0) {
        displayStep = currentStepIndex + 1;
    } else if (stepNumber > 0) {
        displayStep = Math.min(stepNumber, total);
    }
    var displayAgent = payload.agent_display_name || AGENT_DISPLAY_NAMES[payload.agent] || payload.agent || "处理中";
    var msg = payload.message || "正在执行...";

    stepBadge.textContent = displayStep > 0 ? ("步骤 " + displayStep + " / " + total) : "等待开始";
    agentName.textContent = displayAgent;
    agentMessage.textContent = msg;

    if (agentStatus) {
        agentStatus.className = "mat-current-agent-status";
        var failCountMatch = msg.match(/失败\s*[:：]?\s*(\d+)/);
        var failCount = failCountMatch ? parseInt(failCountMatch[1], 10) : null;
        var hasHardFailure = msg.indexOf("未通过") !== -1
            || msg.indexOf("执行失败") !== -1
            || msg.indexOf("生成出错") !== -1
            || msg.indexOf("任务已强制停止") !== -1;
        if (msg.indexOf("通过") !== -1 && msg.indexOf("未通过") === -1) {
            agentStatus.textContent = "通过"; agentStatus.classList.add("passed");
        } else if (hasHardFailure || (failCount !== null && failCount > 0)) {
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
    setUiStage("generation");
    document.getElementById("viewTabs").style.display = "flex";
    document.querySelectorAll(".mat-view-tab").forEach(function (b) { b.classList.remove("active"); });
    document.querySelector('.mat-view-tab[data-view="graph"]').classList.add("active");
    document.getElementById("graphSection").style.display = "block";
    document.getElementById("textSection").style.display = "none";
    document.getElementById("logsSection").style.display = "none";
    document.getElementById("detailSection").style.display = "none";
    renderGraph(result);
    renderTextView(result);
    showNavEntryButton(taskId);
}

function showNavEntryButton(taskId) {
    var bar = document.getElementById("navEntryBar");
    var btn = document.getElementById("startNavBtn");
    if (!bar || !btn) return;
    var tid = taskId || currentTaskId;
    if (tid) {
        btn.href = "/app/teaching-nav/" + tid;
        bar.style.display = "flex";
    } else {
        bar.style.display = "none";
    }
}

function hideNavEntryBar() {
    var bar = document.getElementById("navEntryBar");
    if (bar) bar.style.display = "none";
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

    var html = '<div class="mat-text-summary">';
    html += '<p>共 <strong>' + nodes.length + '</strong> 个问题节点（主干 ' + mainNodes.length + ' 个、变式 ' + variantNodes.length + ' 个、支架 ' + scaffoldNodes.length + ' 个），<strong>' + edges.length + '</strong> 条连接关系</p>';
    html += '</div>';

    mainOrder.forEach(function (mainNode, idx) {
        html += '<div class="mat-text-block mat-text-main">';
        html += '<div class="mat-text-block-header mat-main-header">';
        html += '<span class="mat-text-num">' + (idx + 1) + '</span>';
        html += '<span class="mat-text-tag mat-tag-main">主干问题</span>';
        html += '<span class="mat-text-id">' + escapeHtml(String(mainNode.id || "")) + '</span>';
        html += '</div>';
        html += '<div class="mat-text-block-body">';
        html += '<div class="mat-text-question mat-markdown-content">' + renderMarkdownHtml(mainNode.content || "") + '</div>';
        html += renderMeta(mainNode);
        html += renderCommentaryBlock(mainNode);
        html += '</div>';

        var relatedVariants = variantNodes.filter(function (v) {
            return (v.main_id || v.parent_id) === mainNode.id;
        });
        if (relatedVariants.length > 0) {
            html += '<div class="mat-text-sub-group">';
            html += '<div class="mat-text-sub-label mat-variant-label">变式问题</div>';
            relatedVariants.forEach(function (v) {
                html += '<div class="mat-text-block mat-text-variant">';
                html += '<div class="mat-text-block-header mat-variant-header">';
                html += '<span class="mat-text-tag mat-tag-variant">变式</span>';
                html += '<span class="mat-text-id">' + escapeHtml(String(v.id || "")) + '</span>';
                if (v.variation_type) html += '<span class="mat-text-vtype">' + escapeHtml(String(v.variation_type)) + '</span>';
                html += '</div>';
                html += '<div class="mat-text-block-body">';
                html += '<div class="mat-text-question mat-markdown-content">' + renderMarkdownHtml(v.content || "") + '</div>';
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
                html += '<div class="mat-text-sub-group">';
                html += '<div class="mat-text-sub-label mat-scaffold-label">支架问题（过渡到下一主干）</div>';
                relatedScaffolds.forEach(function (s) {
                    html += '<div class="mat-text-block mat-text-scaffold">';
                    html += '<div class="mat-text-block-header mat-scaffold-header">';
                    html += '<span class="mat-text-tag mat-tag-scaffold">支架</span>';
                    html += '<span class="mat-text-id">' + escapeHtml(String(s.id || "")) + '</span>';
                    html += '</div>';
                    html += '<div class="mat-text-block-body">';
                    html += '<div class="mat-text-question mat-markdown-content">' + renderMarkdownHtml(s.content || "") + '</div>';
                    html += renderMeta(s);
                    html += renderCommentaryBlock(s);
                    if (s.bridge_function) html += '<div class="mat-text-bridge mat-markdown-content"><strong>桥梁功能：</strong>' + renderMarkdownHtml(s.bridge_function) + '</div>';
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
    return '<div class="mat-text-commentary"><div class="mat-text-commentary-title">说课稿</div><div class="mat-text-commentary-body mat-markdown-content">' + renderMarkdownHtml(commentary) + '</div></div>';
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
function closeAllMoreMenus() {
    document.querySelectorAll(".mat-more-menu.is-open").forEach(function (m) {
        m.classList.remove("is-open");
    });
}

function bindHistoryListEvents() {
    if (historyEventsBound) return;
    var list = document.getElementById("historyList");
    if (!list) return;

    document.addEventListener("click", function (e) {
        if (!e.target.closest(".mat-history-more-wrap")) closeAllMoreMenus();
    });

    list.addEventListener("click", function (event) {
        var moreBtn = event.target.closest(".mat-btn-more");
        if (moreBtn) {
            event.stopPropagation();
            var menu = moreBtn.nextElementSibling;
            var isOpen = menu && menu.classList.contains("is-open");
            closeAllMoreMenus();
            if (menu && !isOpen) {
                menu.classList.remove("mat-more-menu--below");
                menu.classList.add("is-open");
                var btnRect = moreBtn.getBoundingClientRect();
                var listEl = document.getElementById("historyList");
                var listTop = listEl ? listEl.getBoundingClientRect().top : 0;
                var menuHeight = menu.offsetHeight || 150;
                if (btnRect.top - listTop < menuHeight + 12) {
                    menu.classList.add("mat-more-menu--below");
                }
            }
            return;
        }

        var btn = event.target.closest("button");
        if (!btn) return;
        var item = btn.closest(".mat-history-item");
        if (!item) return;
        var recordId = item.getAttribute("data-id");
        if (!recordId) return;

        closeAllMoreMenus();

        if (btn.classList.contains("mat-btn-view")) {
            loadHistoryItem(recordId);
            return;
        }
        if (btn.classList.contains("mat-btn-export")) {
            exportHistoryItem(recordId, event, btn);
            return;
        }
        if (btn.classList.contains("mat-btn-input")) {
            toggleHistoryInput(recordId, btn, event);
            return;
        }
        if (btn.classList.contains("mat-btn-logs")) {
            loadHistoryLogs(recordId, event);
            return;
        }
        if (btn.classList.contains("mat-btn-delete")) {
            deleteHistoryItem(recordId, event);
        }
    });
    historyEventsBound = true;
}

function loadHistory() {
    bindHistoryListEvents();
    var container = document.getElementById("historyList");
    if (!container) return;
    container.innerHTML = '<p class="mat-history-empty">加载中...</p>';

    fetch(API_PREFIX + "/history")
        .then(function (res) {
            return res.json().then(function (data) {
                return { ok: res.ok, status: res.status, data: data };
            });
        })
        .then(function (payload) {
            var list = payload.data;
            if (!payload.ok) {
                var errMsg = (list && list.msg) ? list.msg : "历史记录加载失败（HTTP " + payload.status + "）";
                container.innerHTML = '<p class="mat-history-empty mat-history-error">' + escapeHtml(errMsg) + "</p>";
                return;
            }
            if (!Array.isArray(list)) {
                container.innerHTML = '<p class="mat-history-empty mat-history-error">历史接口返回格式异常</p>';
                return;
            }
            if (!list.length) {
                container.innerHTML = '<div class="mat-history-empty">'
                    + '<svg class="mat-history-empty-illustration" viewBox="0 0 64 64" fill="none" width="48" height="48">'
                    + '<rect x="12" y="8" width="40" height="48" rx="6" stroke="currentColor" stroke-width="2"/>'
                    + '<line x1="22" y1="22" x2="42" y2="22" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
                    + '<line x1="22" y1="30" x2="38" y2="30" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
                    + '<line x1="22" y1="38" x2="34" y2="38" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
                    + '</svg>'
                    + '<p>暂无历史记录</p>'
                    + '<p class="mat-history-empty-hint">生成教学地图后，记录将出现在这里</p>'
                    + '</div>';
                return;
            }
            var html = "";
            list.forEach(function (item) {
                var goals = (item.teaching_goals || "").substring(0, 60);
                var safeGoals = escapeHtml(goals + (goals.length >= 60 ? "..." : ""));
                var modelDisplayName = escapeHtml(item.model_display_name || "未知模型");
                var durationSeconds = Number(item.duration_seconds);
                var hasDuration = isFinite(durationSeconds) && durationSeconds >= 0;
                var subjectAttr = escapeHtml(item.subject || "");
                html += '<div class="mat-history-item" data-id="' + item.id + '" data-subject-color="' + subjectAttr + '">';
                html += '<div class="mat-history-item-header">';
                html += '<span class="mat-history-subject">' + escapeHtml(item.subject || "") + ' · ' + escapeHtml(item.grade || "") + '</span>';
                html += '<span class="mat-history-time">' + escapeHtml(item.created_at || "") + '</span>';
                html += '</div>';
                html += '<div class="mat-history-goals">' + safeGoals + '</div>';
                html += '<div class="mat-history-model">生成模型：' + modelDisplayName;
                if (hasDuration) html += ' · 用时 ' + formatDurationClock(durationSeconds);
                html += '</div>';
                html += '<div class="mat-history-actions">';
                html += '<button class="mat-btn-sm mat-btn-view" type="button">查看</button>';
                html += '<a class="mat-btn-sm mat-btn-nav" href="/app/teaching-nav/' + item.id + '">导航</a>';
                html += '<div class="mat-history-more-wrap">';
                html += '<button class="mat-btn-more" type="button" aria-label="更多操作">&#8943;</button>';
                html += '<div class="mat-more-menu">';
                html += '<button class="mat-btn-sm mat-btn-export" type="button">导出教案</button>';
                html += '<button class="mat-btn-sm mat-btn-input" type="button">查看输入</button>';
                html += '<button class="mat-btn-sm mat-btn-logs" type="button">查看日志</button>';
                html += '<button class="mat-btn-sm mat-btn-delete" type="button">删除记录</button>';
                html += '</div></div>';
                html += '</div>';
                html += '<div class="mat-history-input-detail" id="historyInputDetail-' + item.id + '" style="display:none;"></div>';
                html += '</div>';
            });
            container.innerHTML = html;
            refreshLoadLastInputAvailability();
        })
        .catch(function (err) {
            container.innerHTML = '<p class="mat-history-empty mat-history-error">历史记录加载失败：' + escapeHtml(String(err && err.message ? err.message : err)) + "</p>";
            refreshLoadLastInputAvailability();
        });
}

function toggleHistoryInput(recordId, btn, event) {
    if (event && typeof event.stopPropagation === "function") event.stopPropagation();
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
            html += '<div class="mat-history-input-row"><span class="mat-history-input-label">重难点分析：</span><span class="mat-history-input-value">' + escapeHtml(data.difficulty_analysis || "未填写") + '</span></div>';
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
    if (event && typeof event.stopPropagation === "function") event.stopPropagation();
    currentTaskId = recordId;
    setUiStage("generation");
    document.getElementById("placeholder").style.display = "none";
    document.getElementById("progressSection").style.display = "none";
    document.getElementById("viewTabs").style.display = "flex";
    document.querySelectorAll(".mat-view-tab").forEach(function (b) { b.classList.remove("active"); });
    document.querySelector('.mat-view-tab[data-view="logs"]').classList.add("active");
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
    fetch(API_PREFIX + "/history/" + recordId, { method: "DELETE" })
        .then(function () { loadHistory(); });
}

function exportHistoryItem(recordId, event, btn) {
    if (event && typeof event.stopPropagation === "function") event.stopPropagation();
    if (btn) { btn.disabled = true; btn.textContent = "导出中..."; }

    fetch(API_PREFIX + "/history/" + recordId)
        .then(function (res) { return res.json(); })
        .then(function (data) {
            if (data.error || !data.result) {
                alert("导出失败：无法获取数据");
                return;
            }
            var md = teachingMapToMarkdown(data);
            var rawDate = String(data.created_at || recordId).replace(/[: ]/g, "-").replace(/[^\w\-]/g, "");
            var filename = (data.subject || "教学地图") + "_" + (data.grade || "") + "_" + rawDate + ".md";
            downloadTextFile(md, filename);
        })
        .catch(function (err) { alert("导出失败：" + err.message); })
        .then(function () {
            if (btn) { btn.disabled = false; btn.textContent = "导出教案"; }
        });
}

var CN_NUMBERS = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
    "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十"];

function teachingMapToMarkdown(data) {
    var teachingMap = data.result || {};
    var nodes = teachingMap.nodes || [];
    var edges = teachingMap.edges || [];

    var mainNodes = nodes.filter(function (n) { return n.question_type === "main"; });
    var variantNodes = nodes.filter(function (n) { return n.question_type === "variant"; });
    var scaffoldNodes = nodes.filter(function (n) { return n.question_type === "scaffold"; });
    var mainOrder = orderMainNodes(mainNodes, edges);

    var lines = [];

    lines.push("# " + (data.subject || "") + (data.grade || "") + " 教学地图");
    lines.push("");

    lines.push("## 基本信息");
    lines.push("");
    if (data.subject) lines.push("- **学科**：" + data.subject);
    if (data.grade) lines.push("- **年级**：" + data.grade);
    if (data.teaching_goals) lines.push("- **教学目标**：" + data.teaching_goals);
    if (data.student_profile) lines.push("- **学情描述**：" + data.student_profile);
    if (data.difficulty_analysis) lines.push("- **重难点分析**：" + data.difficulty_analysis);
    if (data.language_style) lines.push("- **语言风格**：" + data.language_style);
    if (data.model_display_name || data.model_id) lines.push("- **生成模型**：" + (data.model_display_name || data.model_id || ""));
    var durationSeconds = Number(data.duration_seconds);
    if (isFinite(durationSeconds) && durationSeconds >= 0) {
        lines.push("- **生成时长**：" + formatDurationClock(durationSeconds));
    }
    if (data.created_at) lines.push("- **生成时间**：" + data.created_at);
    lines.push("");

    lines.push("## 教学地图概览");
    lines.push("");
    lines.push("共 **" + nodes.length + "** 个问题节点（主干 " + mainNodes.length + " 个、变式 " + variantNodes.length + " 个、支架 " + scaffoldNodes.length + " 个），**" + edges.length + "** 条连接关系");
    lines.push("");

    lines.push("---");
    lines.push("");

    mainOrder.forEach(function (mainNode, idx) {
        var cnNum = CN_NUMBERS[idx] || String(idx + 1);
        lines.push("## " + cnNum + "、主干问题 " + (idx + 1));
        lines.push("");
        lines.push(mainNode.content || "");
        lines.push("");

        var metaLine = buildMetaLine(mainNode);
        if (metaLine) { lines.push(metaLine); lines.push(""); }

        var commentary = getCommentary(mainNode);
        if (commentary) {
            lines.push("### 说课稿");
            lines.push("");
            lines.push(commentary);
            lines.push("");
        }

        var relatedVariants = variantNodes.filter(function (v) {
            return (v.main_id || v.parent_id) === mainNode.id;
        });
        if (relatedVariants.length > 0) {
            lines.push("### 变式问题");
            lines.push("");
            relatedVariants.forEach(function (v, vi) {
                lines.push("#### 变式 " + (vi + 1) + (v.variation_type ? "（" + v.variation_type + "）" : ""));
                lines.push("");
                lines.push(v.content || "");
                lines.push("");
                var vm = buildMetaLine(v);
                if (vm) { lines.push(vm); lines.push(""); }
                var vc = getCommentary(v);
                if (vc) { lines.push("**说课稿：**"); lines.push(""); lines.push(vc); lines.push(""); }
            });
        }

        if (idx < mainOrder.length - 1) {
            var nextMain = mainOrder[idx + 1];
            var relatedScaffolds = scaffoldNodes.filter(function (s) {
                var fromId = s.from_id || s.from_main_id;
                var toId = s.to_id || s.to_main_id;
                return fromId === mainNode.id || toId === nextMain.id;
            });
            if (relatedScaffolds.length > 0) {
                lines.push("### 支架问题（过渡到下一主干）");
                lines.push("");
                relatedScaffolds.forEach(function (s, si) {
                    lines.push("#### 支架 " + (si + 1));
                    lines.push("");
                    lines.push(s.content || "");
                    lines.push("");
                    var sm = buildMetaLine(s);
                    if (sm) { lines.push(sm); lines.push(""); }
                    var sc = getCommentary(s);
                    if (sc) { lines.push("**说课稿：**"); lines.push(""); lines.push(sc); lines.push(""); }
                    if (s.bridge_function) { lines.push("**桥梁功能：**" + s.bridge_function); lines.push(""); }
                });
            }
            lines.push("---");
            lines.push("");
        }
    });

    return lines.join("\n");
}

function buildMetaLine(node) {
    var parts = [];
    if (node.knowledge_points && node.knowledge_points.length) {
        parts.push("知识点：" + node.knowledge_points.join("、"));
    }
    var cl = node.cognitive_level || node.bloom_level || "";
    var clLabel = COGNITIVE_LABELS[cl] || cl;
    if (clLabel) parts.push("认知层次：" + clLabel);
    if (node.difficulty !== undefined) parts.push("难度：" + node.difficulty);
    var di = node.design_intent || node.design_rationale || "";
    if (di) parts.push("设计意图：" + di);
    if (!parts.length) return "";
    return parts.map(function (p) { return "- " + p; }).join("  \n");
}

function downloadTextFile(text, filename) {
    var blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
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

renderGenerationDurationText();
if (!openRecordFromQueryOnLoad()) {
    restoreTaskProgressOnLoad();
}
