/**
 * mat_nav.js — Teaching Map Navigation Controller
 */

(function () {
    "use strict";

    var TASK_ID = window.NAV_TASK_ID || "";
    var API_PREFIX = "/api/mat/nav";
    var NOTE_PREFIX = "openArena.nav.note.";
    var TIMER_DEFAULT = 180;

    var TYPE_LABELS = { main: "主干问题", variant: "变式问题", scaffold: "支架问题" };
    var SCENARIO_LABELS = {
        "high_high": "纵向认知进阶",
        "high_low": "保热修障",
        "low_high": "激活参与",
        "low_low": "修障激活",
    };

    var teachingMap = null;
    var currentNodeId = null;
    var currentNode = null;
    var visited = [];
    var participation = "high";
    var accuracy = "high";
    var isTransitioning = false;
    var navigationCompleted = false;
    var timerRemaining = TIMER_DEFAULT;
    var timerHandle = null;

    var pageEl = document.getElementById("navPage");
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
    var scriptContentEl = document.getElementById("navScriptContent");
    var explanationBodyEl = document.getElementById("navExplanationBody");
    var noteEl = document.getElementById("navTeacherNote");
    var toolPanelEl = document.getElementById("navToolPanel");
    var completedCardEl = document.getElementById("navCompletedCard");
    var trailEl = document.getElementById("navTrail");
    var trailShellEl = trailEl ? trailEl.parentElement : null;
    var dispatchBtnEl = document.getElementById("navDispatchBtn");
    var backBtnEl = document.getElementById("navBackBtn");
    var restartBtnEl = document.getElementById("navRestartBtn");
    var scenarioTextEl = document.getElementById("navScenarioText");
    var participationToggleEl = document.getElementById("participationToggle");
    var accuracyToggleEl = document.getElementById("accuracyToggle");
    var largeTextToggleEl = document.getElementById("navLargeTextToggle");
    var projectorToggleEl = document.getElementById("navProjectorToggle");
    var timerDisplayEl = document.getElementById("navTimerDisplay");
    var timerToggleEl = document.getElementById("navTimerToggle");
    var timerResetEl = document.getElementById("navTimerReset");
    var visualAidEl = document.getElementById("navVisualAid");
    var visualAidFrameEl = document.getElementById("navVisualAidFrame");
    var visualAidImgEl = document.getElementById("navVisualAidImg");
    var visualAidZoomEl = document.getElementById("navVisualAidZoom");
    var visualAidHintEl = document.getElementById("navVisualAidHint");
    var visualAidHintTextEl = document.getElementById("navVisualAidHintText");
    var lightboxEl = document.getElementById("navLightbox");
    var lightboxFrameEl = document.getElementById("navLightboxFrame");
    var lightboxImgEl = document.getElementById("navLightboxImg");
    var lightboxTextEl = document.getElementById("navLightboxText");
    var lightboxCloseEl = document.getElementById("navLightboxClose");

    function init() {
        if (!TASK_ID) {
            showError("缺少任务 ID");
            return;
        }
        bindEvents();
        renderTimer();
        loadTeachingMap();
    }

    function bindEvents() {
        if (dispatchBtnEl) dispatchBtnEl.addEventListener("click", handleDispatch);
        if (backBtnEl) backBtnEl.addEventListener("click", handleGoBack);
        if (restartBtnEl) restartBtnEl.addEventListener("click", handleRestart);
        if (largeTextToggleEl) largeTextToggleEl.addEventListener("click", toggleLargeText);
        if (projectorToggleEl) projectorToggleEl.addEventListener("click", toggleProjectorMode);
        if (timerToggleEl) timerToggleEl.addEventListener("click", toggleTimer);
        if (timerResetEl) timerResetEl.addEventListener("click", function () { resetTimer(true); });
        if (noteEl) noteEl.addEventListener("input", persistNote);

        setupToggle(participationToggleEl, function (val) {
            participation = val;
            updateScenarioLabel();
        });
        setupToggle(accuracyToggleEl, function (val) {
            accuracy = val;
            updateScenarioLabel();
        });
        setupTabs();
        setupLightbox();
        setupTrailClicks();
    }

    function setupToggle(container, onChange) {
        if (!container) return;
        var buttons = container.querySelectorAll(".nav-toggle-btn");
        buttons.forEach(function (btn) {
            btn.addEventListener("click", function () {
                buttons.forEach(function (b) { b.classList.remove("active"); });
                btn.classList.add("active");
                onChange(btn.dataset.value);
            });
        });
    }

    function setupTabs() {
        var tabs = document.querySelectorAll(".nav-tool-tab");
        tabs.forEach(function (tab) {
            tab.addEventListener("click", function () {
                activateToolPanel(tab.dataset.panel || "script");
            });
        });
    }

    function setupTrailClicks() {
        if (!trailEl) return;
        trailEl.addEventListener("click", function (event) {
            var target = event.target.closest(".nav-trail-item");
            if (!target || navigationCompleted || isTransitioning) return;
            var nodeId = target.dataset.nodeId;
            var index = visited.indexOf(nodeId);
            if (index < 0 || nodeId === currentNodeId) return;
            currentNodeId = nodeId;
            currentNode = findNode(nodeId);
            visited = visited.slice(0, index + 1);
            animateTransition(function () {
                displayCurrentQuestion();
                updateTrail();
                updateProgress();
                updateNavActionButtons();
            });
        });
    }

    function setupLightbox() {
        if (visualAidZoomEl) {
            visualAidZoomEl.addEventListener("click", function (event) {
                event.stopPropagation();
                openLightbox(getCurrentVisualHtml(), visualAidImgEl ? visualAidImgEl.src : "", "");
            });
        }
        if (visualAidEl) {
            visualAidEl.addEventListener("click", function () {
                openLightbox(getCurrentVisualHtml(), visualAidImgEl ? visualAidImgEl.src : "", "");
            });
        }
        if (visualAidHintEl) {
            visualAidHintEl.addEventListener("click", function () {
                openLightbox("", "", visualAidHintTextEl ? visualAidHintTextEl.textContent : "");
            });
        }
        if (lightboxCloseEl) lightboxCloseEl.addEventListener("click", closeLightbox);
        if (lightboxEl) {
            var backdrop = lightboxEl.querySelector(".nav-lightbox-backdrop");
            if (backdrop) backdrop.addEventListener("click", closeLightbox);
        }
        document.addEventListener("keydown", function (event) {
            if (event.key === "Escape") closeLightbox();
        });
    }

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
                if (!data.first_node_id || !teachingMap || !teachingMap.nodes || !teachingMap.nodes.length) {
                    showError("教学地图为空或格式错误");
                    return;
                }
                startNavigation(data.first_node_id);
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

    function startNavigation(firstNodeId) {
        loadingEl.style.display = "none";
        mainEl.style.display = "grid";
        controlsEl.style.display = "block";
        statusBadgeEl.textContent = "导航中";
        statusBadgeEl.classList.add("active");
        navigationCompleted = false;
        currentNodeId = firstNodeId;
        visited = [firstNodeId];
        currentNode = findNode(firstNodeId);
        if (completedCardEl) completedCardEl.style.display = "none";
        if (questionCardEl) questionCardEl.style.display = "flex";
        if (toolPanelEl) toolPanelEl.style.display = "flex";
        if (trailShellEl) trailShellEl.style.display = "block";
        displayCurrentQuestion();
        updateTrail();
        updateProgress();
        updateScenarioLabel();
        updateNavActionButtons();
    }

    function handleGoBack() {
        if (isTransitioning || navigationCompleted || visited.length <= 1) return;
        isTransitioning = true;
        updateNavActionButtons();
        visited.pop();
        currentNodeId = visited[visited.length - 1];
        currentNode = findNode(currentNodeId);
        animateTransition(function () {
            displayCurrentQuestion();
            updateTrail();
            updateProgress();
            updateNavActionButtons();
        });
    }

    function handleDispatch() {
        if (isTransitioning || navigationCompleted) return;
        isTransitioning = true;
        updateNavActionButtons();
        requestDispatch()
            .then(function (result) {
                if (result.completed || !result.next_node_id) {
                    showCompleted();
                    return;
                }
                currentNodeId = result.next_node_id;
                visited.push(currentNodeId);
                currentNode = result.next_node || findNode(currentNodeId);
                animateTransition(function () {
                    displayCurrentQuestion();
                    updateTrail();
                    updateProgress();
                });
            })
            .catch(function (err) {
                console.error("Dispatch error:", err);
                isTransitioning = false;
                updateNavActionButtons();
            });
    }

    function handleRestart() {
        stopTimer();
        navigationCompleted = false;
        if (completedCardEl) completedCardEl.style.display = "none";
        if (questionCardEl) questionCardEl.style.display = "flex";
        if (toolPanelEl) toolPanelEl.style.display = "flex";
        if (trailShellEl) trailShellEl.style.display = "block";
        statusBadgeEl.textContent = "导航中";
        statusBadgeEl.classList.remove("completed");
        statusBadgeEl.classList.add("active");
        var firstNode = getFirstMainNode();
        if (!firstNode) return;
        currentNodeId = firstNode.id;
        visited = [firstNode.id];
        currentNode = firstNode;
        displayCurrentQuestion();
        updateTrail();
        updateProgress();
        updateNavActionButtons();
    }

    function displayCurrentQuestion() {
        if (!currentNode) return;
        resetTimer(false);
        var qType = currentNode.question_type || "main";
        questionBadgeEl.textContent = currentNode.id || "";
        questionBadgeEl.className = "nav-question-badge type-" + qType;
        questionTypeEl.textContent = TYPE_LABELS[qType] || qType;
        questionDifficultyEl.textContent = formatDifficulty(currentNode.difficulty);
        questionTextEl.textContent = currentNode.content || "（无题目内容）";
        displayVisualAid(currentNode);
        renderToolPanels(currentNode);
        restoreNote();
    }

    function displayVisualAid(node) {
        var html = node.visual_aid_html || "";
        var urls = node.visual_aid_urls || [];
        var prompt = node.visual_aid_prompt || "";
        var vaType = node.visual_aid_type || "";
        var hasInteractive = !!(html && visualAidFrameEl);
        var hasImage = !hasInteractive && urls.length > 0 && urls[0];
        var hasHint = !hasInteractive && !hasImage && prompt && vaType !== "none";
        questionCardEl.classList.toggle("has-visual-aid", !!(hasInteractive || hasImage || hasHint));
        questionCardEl.classList.toggle("is-text-only", !(hasInteractive || hasImage || hasHint));

        if (visualAidFrameEl) {
            visualAidFrameEl.removeAttribute("srcdoc");
            visualAidFrameEl.style.display = "none";
        }
        visualAidImgEl.removeAttribute("src");
        visualAidImgEl.style.display = "none";

        if (hasInteractive) {
            visualAidFrameEl.srcdoc = html;
            visualAidFrameEl.style.display = "block";
            visualAidEl.style.display = "flex";
            visualAidHintEl.style.display = "none";
            return;
        }

        if (hasImage) {
            visualAidImgEl.src = urls[0];
            visualAidImgEl.style.display = "block";
            visualAidEl.style.display = "flex";
            visualAidHintEl.style.display = "none";
            return;
        }

        visualAidEl.style.display = "none";
        if (hasHint) {
            visualAidHintTextEl.textContent = prompt;
            visualAidHintEl.style.display = "flex";
        } else {
            visualAidHintTextEl.textContent = "";
            visualAidHintEl.style.display = "none";
        }
    }

    function renderToolPanels(node) {
        var script = node.lesson_presentation_script || "";
        var explanation = node.explanation || "";
        scriptContentEl.innerHTML = script ? renderMarkdown(script) : '<p class="nav-empty-text">暂无说课稿。</p>';
        explanationBodyEl.innerHTML = explanation ? renderMarkdown(explanation) : '<p class="nav-empty-text">暂无解析。</p>';
    }

    function activateToolPanel(panelName) {
        document.querySelectorAll(".nav-tool-tab").forEach(function (tab) {
            tab.classList.toggle("active", tab.dataset.panel === panelName);
        });
        document.querySelectorAll(".nav-tool-pane").forEach(function (pane) {
            pane.classList.toggle("active", pane.dataset.panel === panelName);
        });
    }

    function updateTrail() {
        var html = "";
        for (var i = 0; i < visited.length; i++) {
            var nid = visited[i];
            var node = findNode(nid);
            var qType = node ? (node.question_type || "main") : "main";
            var current = nid === currentNodeId ? " current" : "";
            html += '<button type="button" class="nav-trail-item type-' + qType + current +
                '" data-node-id="' + escapeHtml(nid) + '">' + escapeHtml(nid) + '</button>';
            if (i < visited.length - 1) html += '<span class="nav-trail-arrow">→</span>';
        }
        trailEl.innerHTML = html;
        trailEl.parentElement.scrollLeft = trailEl.parentElement.scrollWidth;
    }

    function updateProgress() {
        var total = teachingMap ? teachingMap.nodes.length : 0;
        progressTextEl.textContent = "已访问 " + visited.length + " / " + total;
    }

    function updateScenarioLabel() {
        var key = participation + "_" + accuracy;
        scenarioTextEl.textContent = SCENARIO_LABELS[key] || "";
    }

    function updateNavActionButtons() {
        var canGoBack = visited.length > 1 && !navigationCompleted && !isTransitioning;
        if (backBtnEl) backBtnEl.disabled = !canGoBack;
        if (dispatchBtnEl && !navigationCompleted) dispatchBtnEl.disabled = isTransitioning;
    }

    function showCompleted() {
        stopTimer();
        navigationCompleted = true;
        isTransitioning = false;
        if (questionCardEl) questionCardEl.style.display = "none";
        if (toolPanelEl) toolPanelEl.style.display = "none";
        if (trailShellEl) trailShellEl.style.display = "none";
        if (completedCardEl) completedCardEl.style.display = "block";
        statusBadgeEl.textContent = "已完成";
        statusBadgeEl.classList.remove("active");
        statusBadgeEl.classList.add("completed");
        updateNavActionButtons();
    }

    function animateTransition(callback) {
        questionCardEl.classList.add("animating-out");
        setTimeout(function () {
            questionCardEl.classList.remove("animating-out");
            callback();
            questionCardEl.classList.add("animating-in");
            setTimeout(function () {
                questionCardEl.classList.remove("animating-in");
                isTransitioning = false;
                updateNavActionButtons();
            }, 280);
        }, 180);
    }

    function toggleLargeText() {
        var active = pageEl.classList.toggle("nav-large-text");
        largeTextToggleEl.classList.toggle("is-active", active);
        largeTextToggleEl.setAttribute("aria-pressed", active ? "true" : "false");
    }

    function toggleProjectorMode() {
        var active = pageEl.classList.toggle("nav-projector");
        projectorToggleEl.classList.toggle("is-active", active);
        projectorToggleEl.setAttribute("aria-pressed", active ? "true" : "false");
    }

    function toggleTimer() {
        if (timerHandle) {
            stopTimer();
            return;
        }
        if (timerRemaining <= 0) timerRemaining = TIMER_DEFAULT;
        timerToggleEl.textContent = "暂停";
        timerHandle = setInterval(function () {
            timerRemaining -= 1;
            if (timerRemaining <= 0) {
                timerRemaining = 0;
                stopTimer();
            }
            renderTimer();
        }, 1000);
    }

    function stopTimer() {
        if (timerHandle) clearInterval(timerHandle);
        timerHandle = null;
        if (timerToggleEl) timerToggleEl.textContent = "开始";
    }

    function resetTimer(shouldStop) {
        if (shouldStop) stopTimer();
        timerRemaining = TIMER_DEFAULT;
        renderTimer();
    }

    function renderTimer() {
        if (!timerDisplayEl) return;
        var min = Math.floor(timerRemaining / 60);
        var sec = timerRemaining % 60;
        timerDisplayEl.textContent = pad2(min) + ":" + pad2(sec);
        timerDisplayEl.classList.toggle("is-done", timerRemaining === 0);
    }

    function persistNote() {
        if (!currentNodeId || !noteEl) return;
        localStorage.setItem(noteKey(currentNodeId), noteEl.value);
    }

    function restoreNote() {
        if (!noteEl || !currentNodeId) return;
        noteEl.value = localStorage.getItem(noteKey(currentNodeId)) || "";
    }

    function noteKey(nodeId) {
        return NOTE_PREFIX + TASK_ID + "." + nodeId;
    }

    function getCurrentVisualHtml() {
        return currentNode && currentNode.visual_aid_html ? currentNode.visual_aid_html : "";
    }

    function openLightbox(html, src, text) {
        if (!lightboxEl) return;
        if (html && lightboxFrameEl) {
            lightboxFrameEl.srcdoc = html;
            lightboxFrameEl.style.display = "block";
        } else if (lightboxFrameEl) {
            lightboxFrameEl.removeAttribute("srcdoc");
            lightboxFrameEl.style.display = "none";
        }
        if (src) {
            lightboxImgEl.src = src;
            lightboxImgEl.style.display = "block";
        } else {
            lightboxImgEl.removeAttribute("src");
            lightboxImgEl.style.display = "none";
        }
        lightboxTextEl.textContent = text || "";
        lightboxEl.style.display = "flex";
    }

    function closeLightbox() {
        if (lightboxEl) lightboxEl.style.display = "none";
        if (lightboxFrameEl) lightboxFrameEl.removeAttribute("srcdoc");
    }

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
        return mainNodes[0] || teachingMap.nodes[0] || null;
    }

    function extractNumber(id) {
        var m = (id || "").match(/\d+/);
        return m ? parseInt(m[0], 10) : 0;
    }

    function formatDifficulty(value) {
        if (typeof value === "number") return "难度 " + Math.round(value * 100) + "%";
        return "";
    }

    function pad2(num) {
        return num < 10 ? "0" + num : String(num);
    }

    function renderMarkdown(text) {
        if (!text) return "";
        if (typeof marked !== "undefined" && marked && typeof marked.parse === "function") {
            if (typeof marked.setOptions === "function") marked.setOptions({ gfm: true, breaks: true });
            var rendered = marked.parse(String(text));
            if (typeof DOMPurify !== "undefined" && DOMPurify && typeof DOMPurify.sanitize === "function") {
                return DOMPurify.sanitize(rendered, { USE_PROFILES: { html: true } });
            }
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

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
