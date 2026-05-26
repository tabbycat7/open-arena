/**
 * mat_nav.js — Teaching Map Navigation Controller
 */

(function () {
    "use strict";

    var TASK_ID = window.NAV_TASK_ID || "";
    var API_PREFIX = "/api/mat/nav";

    var TYPE_LABELS = { main: "主干问题", variant: "变式问题", scaffold: "支架问题" };
    var SCENARIO_LABELS = {
        "high_high": "纵向认知进阶",
        "high_low": "保热修障",
        "low_high": "激活参与",
        "low_low": "修障激活",
    };

    // State
    var teachingMap = null;
    var currentNodeId = null;
    var currentNode = null;
    var visited = [];
    var participation = "high";
    var accuracy = "high";
    var isTransitioning = false;
    var navigationCompleted = false;

    // DOM Elements
    var loadingEl = document.getElementById("navLoading");
    var errorEl = document.getElementById("navError");
    var errorTextEl = document.getElementById("navErrorText");
    var mainEl = document.getElementById("navMain");
    var controlsEl = document.getElementById("navControls");
    var statusBadgeEl = document.getElementById("navStatusBadge");
    var progressTextEl = document.getElementById("navProgressText");
    var questionCardEl = document.getElementById("navQuestionCard");
    var questionBadgeEl = document.getElementById("navQuestionBadge");
    var questionTypeEl = document.getElementById("navQuestionType");
    var questionDifficultyEl = document.getElementById("navQuestionDifficulty");
    var questionTextEl = document.getElementById("navQuestionText");
    var scriptToggleEl = document.getElementById("navScriptToggle");
    var scriptContentEl = document.getElementById("navScriptContent");
    var explanationEl = document.getElementById("navExplanation");
    var explanationBodyEl = document.getElementById("navExplanationBody");
    var closeExplanationEl = document.getElementById("closeExplanation");
    var completedCardEl = document.getElementById("navCompletedCard");
    var trailEl = document.getElementById("navTrail");
    var dispatchBtnEl = document.getElementById("navDispatchBtn");
    var restartBtnEl = document.getElementById("navRestartBtn");
    var scenarioTextEl = document.getElementById("navScenarioText");
    var participationToggleEl = document.getElementById("participationToggle");
    var accuracyToggleEl = document.getElementById("accuracyToggle");

    // --- Initialization ---
    function init() {
        if (!TASK_ID) {
            showError("缺少任务 ID");
            return;
        }
        bindEvents();
        loadTeachingMap();
    }

    function bindEvents() {
        dispatchBtnEl.addEventListener("click", handleDispatch);
        restartBtnEl.addEventListener("click", handleRestart);
        scriptToggleEl.addEventListener("click", toggleScript);
        closeExplanationEl.addEventListener("click", hideExplanation);

        var explBtn = document.getElementById("navExplainToggle");
        if (explBtn) {
            explBtn.addEventListener("click", function () {
                if (explanationEl.style.display !== "none") {
                    hideExplanation();
                } else if (currentNodeId) {
                    showExplanation(currentNodeId);
                }
            });
        }

        setupToggle(participationToggleEl, function (val) {
            participation = val;
            updateScenarioLabel();
        });
        setupToggle(accuracyToggleEl, function (val) {
            accuracy = val;
            updateScenarioLabel();
        });
    }

    function setupToggle(container, onChange) {
        var buttons = container.querySelectorAll(".nav-toggle-btn");
        buttons.forEach(function (btn) {
            btn.addEventListener("click", function () {
                buttons.forEach(function (b) { b.classList.remove("active"); });
                btn.classList.add("active");
                onChange(btn.dataset.value);
            });
        });
    }

    // --- API ---
    function loadTeachingMap() {
        fetch(API_PREFIX + "/load/" + TASK_ID)
            .then(function (res) {
                if (!res.ok) throw new Error("Failed to load");
                return res.json();
            })
            .then(function (data) {
                if (data.error) {
                    showError(data.error);
                    return;
                }
                teachingMap = data.teaching_map;
                var firstNodeId = data.first_node_id;
                if (!firstNodeId || !teachingMap || !teachingMap.nodes || !teachingMap.nodes.length) {
                    showError("教学地图为空或格式错误");
                    return;
                }
                startNavigation(firstNodeId);
            })
            .catch(function (err) {
                showError("加载教学地图失败：" + err.message);
            });
    }

    function requestDispatch() {
        return fetch(API_PREFIX + "/dispatch", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                teaching_map: teachingMap,
                current_node_id: currentNodeId,
                participation: participation,
                accuracy: accuracy,
                visited: visited,
            }),
        }).then(function (res) {
            if (!res.ok) throw new Error("Dispatch failed");
            return res.json();
        });
    }

    // --- Navigation Logic ---
    function startNavigation(firstNodeId) {
        loadingEl.style.display = "none";
        mainEl.style.display = "flex";
        controlsEl.style.display = "block";
        statusBadgeEl.textContent = "导航中";
        statusBadgeEl.classList.add("active");
        navigationCompleted = false;

        currentNodeId = firstNodeId;
        visited = [firstNodeId];
        currentNode = findNode(firstNodeId);
        displayCurrentQuestion();
        updateTrail();
        updateProgress();
        updateScenarioLabel();
    }

    function handleDispatch() {
        if (isTransitioning || navigationCompleted) return;

        triggerRipple();
        isTransitioning = true;
        dispatchBtnEl.disabled = true;

        requestDispatch()
            .then(function (result) {
                if (result.completed || !result.next_node_id) {
                    showCompleted();
                    return;
                }

                var nextNodeId = result.next_node_id;
                visited.push(nextNodeId);
                currentNodeId = nextNodeId;
                currentNode = result.next_node || findNode(nextNodeId);

                animateTransition(function () {
                    displayCurrentQuestion();
                    updateTrail();
                    updateProgress();
                });
            })
            .catch(function (err) {
                console.error("Dispatch error:", err);
                isTransitioning = false;
                dispatchBtnEl.disabled = false;
            });
    }

    function handleRestart() {
        navigationCompleted = false;
        completedCardEl.style.display = "none";
        questionCardEl.style.display = "block";
        statusBadgeEl.textContent = "导航中";
        statusBadgeEl.classList.remove("completed");
        statusBadgeEl.classList.add("active");
        dispatchBtnEl.disabled = false;
        hideExplanation();

        var firstNode = getFirstMainNode();
        if (firstNode) {
            currentNodeId = firstNode.id;
            visited = [firstNode.id];
            currentNode = firstNode;
            displayCurrentQuestion();
            updateTrail();
            updateProgress();
        }
    }

    // --- Display ---
    function displayCurrentQuestion() {
        if (!currentNode) return;

        var qType = currentNode.question_type || "main";
        questionBadgeEl.textContent = currentNode.id || "";
        questionBadgeEl.className = "nav-question-badge type-" + qType;
        questionTypeEl.textContent = TYPE_LABELS[qType] || qType;

        var difficulty = currentNode.difficulty;
        if (typeof difficulty === "number") {
            questionDifficultyEl.textContent = "难度 " + (difficulty * 100).toFixed(0) + "%";
        } else {
            questionDifficultyEl.textContent = "";
        }

        questionTextEl.textContent = currentNode.content || "（无题目内容）";

        var script = currentNode.lesson_presentation_script || "";
        if (script) {
            scriptToggleEl.style.display = "inline-flex";
            scriptContentEl.innerHTML = renderMarkdown(script);
            scriptContentEl.style.display = "none";
            scriptToggleEl.classList.remove("expanded");
        } else {
            scriptToggleEl.style.display = "none";
            scriptContentEl.style.display = "none";
        }

        // Show/hide explanation button
        var explBtn = document.getElementById("navExplainToggle");
        var explanation = currentNode.explanation || "";
        if (explBtn) {
            explBtn.style.display = explanation ? "inline-flex" : "none";
        }

        hideExplanation();
    }

    function showExplanation(nodeId) {
        var node = findNode(nodeId);
        if (!node) return;

        var explanation = node.explanation || node.lesson_presentation_script || "";
        if (!explanation) return;
        explanationBodyEl.innerHTML = renderMarkdown(
            "<strong>" + escapeHtml(node.id) + " 解析：</strong> " + explanation
        );
        explanationEl.style.display = "block";
    }

    function hideExplanation() {
        explanationEl.style.display = "none";
    }

    function showCompleted() {
        navigationCompleted = true;
        isTransitioning = false;
        questionCardEl.style.display = "none";
        completedCardEl.style.display = "block";
        dispatchBtnEl.disabled = true;
        statusBadgeEl.textContent = "已完成";
        statusBadgeEl.classList.remove("active");
        statusBadgeEl.classList.add("completed");
    }

    function toggleScript() {
        var isShown = scriptContentEl.style.display !== "none";
        scriptContentEl.style.display = isShown ? "none" : "block";
        scriptToggleEl.classList.toggle("expanded", !isShown);
    }

    function updateTrail() {
        var html = "";
        for (var i = 0; i < visited.length; i++) {
            var nid = visited[i];
            var node = findNode(nid);
            var qType = node ? (node.question_type || "main") : "main";
            var isCurrent = nid === currentNodeId;
            html += '<span class="nav-trail-item type-' + qType +
                (isCurrent ? " current" : "") + '">' + escapeHtml(nid) + "</span>";
            if (i < visited.length - 1) {
                html += '<span class="nav-trail-arrow">→</span>';
            }
        }
        trailEl.innerHTML = html;
        // Scroll to end
        trailEl.parentElement.scrollLeft = trailEl.parentElement.scrollWidth;
    }

    function updateProgress() {
        var totalNodes = teachingMap ? teachingMap.nodes.length : 0;
        progressTextEl.textContent = "已访问 " + visited.length + " / " + totalNodes + " 个节点";
    }

    function updateScenarioLabel() {
        var key = participation + "_" + accuracy;
        scenarioTextEl.textContent = SCENARIO_LABELS[key] || "";
    }

    // --- Animations ---
    function animateTransition(callback) {
        questionCardEl.classList.add("animating-out");

        setTimeout(function () {
            questionCardEl.classList.remove("animating-out");
            callback();
            questionCardEl.classList.add("animating-in");

            setTimeout(function () {
                questionCardEl.classList.remove("animating-in");
                isTransitioning = false;
                dispatchBtnEl.disabled = false;
            }, 450);
        }, 300);
    }

    function triggerRipple() {
        dispatchBtnEl.classList.remove("ripple");
        void dispatchBtnEl.offsetWidth;
        dispatchBtnEl.classList.add("ripple");
        setTimeout(function () {
            dispatchBtnEl.classList.remove("ripple");
        }, 600);
    }

    // --- Utilities ---
    function findNode(id) {
        if (!teachingMap || !teachingMap.nodes) return null;
        for (var i = 0; i < teachingMap.nodes.length; i++) {
            if (teachingMap.nodes[i].id === id) return teachingMap.nodes[i];
        }
        return null;
    }

    function getFirstMainNode() {
        if (!teachingMap || !teachingMap.nodes) return null;
        var mainNodes = teachingMap.nodes.filter(function (n) {
            return n.question_type === "main";
        });
        mainNodes.sort(function (a, b) {
            return extractNumber(a.id) - extractNumber(b.id);
        });
        return mainNodes[0] || null;
    }

    function extractNumber(id) {
        var m = (id || "").match(/\d+/);
        return m ? parseInt(m[0], 10) : 0;
    }

    function renderMarkdown(text) {
        if (!text) return "";
        if (typeof marked !== "undefined" && marked && typeof marked.parse === "function") {
            var rendered = marked.parse(String(text));
            if (typeof DOMPurify !== "undefined" && DOMPurify && typeof DOMPurify.sanitize === "function") {
                return DOMPurify.sanitize(rendered, { USE_PROFILES: { html: true } });
            }
            return escapeHtml(text).replace(/\n/g, "<br>");
        }
        return escapeHtml(text).replace(/\n/g, "<br>");
    }

    function escapeHtml(text) {
        var div = document.createElement("div");
        div.textContent = text == null ? "" : String(text);
        return div.innerHTML;
    }

    function showError(message) {
        loadingEl.style.display = "none";
        errorTextEl.textContent = message;
        errorEl.style.display = "flex";
    }

    // --- Start ---
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
