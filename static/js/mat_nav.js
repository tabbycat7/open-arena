/**
 * mat_nav.js — Teaching Map Navigation Controller
 */

(function () {
    "use strict";

    var TASK_ID = window.NAV_TASK_ID || "";
    var API_PREFIX = "/api/mat/nav";
    var NOTE_PREFIX = "openArena.nav.note.";
    var TIMER_DEFAULT = 180;

    // 交互动画「桌面 4:3 设计视口」尺寸：iframe 以此尺寸渲染保持桌面横排布局，
    // 再用 transform 等比缩放塞进面板，确保整幅动画完整可见。与生成模板的 880/4:3 匹配。
    var VA_DESIGN_W = 960;
    var VA_DESIGN_H = 720;

    var MINI_MAP_ZOOM_MIN = 1;
    var MINI_MAP_ZOOM_MAX = 3;
    var MINI_MAP_ZOOM_STEP = 0.2;
    var miniMapView = { scale: 1, panX: 0, panY: 0, base: null };
    var miniMapPanState = null;

    var TYPE_LABELS = { main: "主干问题", variant: "变式问题", scaffold: "支架问题" };
    var SCENARIO_LABELS = {
        "high_high": "纵向认知进阶",
        "high_low": "保热修障",
        "low_high": "激活参与",
        "low_low": "修障激活",
    };
    var SCENARIO_DETAILS = {
        "high_high": {
            label: "纵向认知进阶",
            action: "继续进阶",
            hint: "学生参与和准确率都较好，适合推进到下一组更高阶问题。",
        },
        "high_low": {
            label: "修复认知障碍",
            action: "先修复",
            hint: "学生愿意投入但出现误差，优先用支架题定位并修复关键断点。",
        },
        "low_high": {
            label: "变式激活参与",
            action: "换变式激活",
            hint: "学生能答对但参与不足，适合用变式或新情境提高卷入度。",
        },
        "low_low": {
            label: "支架修复并激活",
            action: "支架+激活",
            hint: "参与和准确率都偏低，先降低入口门槛，再逐步唤回思考。",
        },
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
    var navEvents = [];
    var nodeTimeStats = {};
    var strategyHistory = [];
    var currentNodeEnteredAt = null;
    var lastDispatchMeta = null;

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
    var dispatchReasonEl = document.getElementById("navDispatchReason");
    var dispatchReasonLabelEl = document.getElementById("navDispatchReasonLabel");
    var dispatchReasonTextEl = document.getElementById("navDispatchReasonText");
    var scriptContentEl = document.getElementById("navScriptContent");
    var explanationBodyEl = document.getElementById("navExplanationBody");
    var noteEl = document.getElementById("navTeacherNote");
    var toolPanelEl = document.getElementById("navToolPanel");
    var completedCardEl = document.getElementById("navCompletedCard");
    var dispatchBtnEl = document.getElementById("navDispatchBtn");
    var backBtnEl = document.getElementById("navBackBtn");
    var restartBtnEl = document.getElementById("navRestartBtn");
    var reviewBtnEl = document.getElementById("navReviewBtn");
    var scenarioTextEl = document.getElementById("navScenarioText");
    var scenarioHintEl = document.getElementById("navScenarioHint");
    var scenarioIndicatorEl = document.getElementById("navScenarioIndicator");
    var scenarioStateEl = document.getElementById("navScenarioState");
    var strategyMatrixEl = document.getElementById("navStrategyMatrix");
    var miniMapShellEl = document.getElementById("navMiniMapShell");
    var miniMapEl = document.getElementById("navMiniMap");
    var miniMapToggleEl = document.getElementById("navMiniMapToggle");
    var miniMapZoomInEl = document.getElementById("navMiniMapZoomIn");
    var miniMapZoomOutEl = document.getElementById("navMiniMapZoomOut");
    var miniMapZoomResetEl = document.getElementById("navMiniMapZoomReset");
    var miniMapZoomLabelEl = document.getElementById("navMiniMapZoomLabel");
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
        if (reviewBtnEl) reviewBtnEl.addEventListener("click", downloadReviewMarkdown);
        if (miniMapToggleEl) miniMapToggleEl.addEventListener("click", toggleMiniMap);
        if (miniMapZoomInEl) miniMapZoomInEl.addEventListener("click", function () { zoomMiniMapByStep(MINI_MAP_ZOOM_STEP); });
        if (miniMapZoomOutEl) miniMapZoomOutEl.addEventListener("click", function () { zoomMiniMapByStep(-MINI_MAP_ZOOM_STEP); });
        if (miniMapZoomResetEl) miniMapZoomResetEl.addEventListener("click", resetMiniMapView);
        if (largeTextToggleEl) largeTextToggleEl.addEventListener("click", toggleLargeText);
        if (projectorToggleEl) projectorToggleEl.addEventListener("click", toggleProjectorMode);
        if (timerToggleEl) timerToggleEl.addEventListener("click", toggleTimer);
        if (timerResetEl) timerResetEl.addEventListener("click", function () { resetTimer(true); });
        if (noteEl) noteEl.addEventListener("input", persistNote);

        setupStrategyMatrix();
        setupTabs();
        setupLightbox();
        setupMiniMapInteraction();

        window.addEventListener("resize", fitVisualAidFrame);
        if (typeof ResizeObserver !== "undefined" && visualAidEl) {
            new ResizeObserver(fitVisualAidFrame).observe(visualAidEl);
        }
        if (typeof ResizeObserver !== "undefined" && controlsEl) {
            new ResizeObserver(syncDeckHeight).observe(controlsEl);
        }
    }

    function syncDeckHeight() {
        if (!controlsEl) return;
        var h = controlsEl.offsetHeight || 0;
        if (h > 0) {
            document.documentElement.style.setProperty("--nav-bottom-height", h + "px");
        }
    }

    function setupStrategyMatrix() {
        if (!strategyMatrixEl) return;
        var buttons = strategyMatrixEl.querySelectorAll(".nav-signal-choice");
        buttons.forEach(function (btn) {
            btn.addEventListener("click", function () {
                var group = btn.closest(".nav-signal-toggle");
                var metric = group ? group.dataset.metric || "" : "";
                var nextValue = btn.dataset.value || "high";
                var prev = getScenarioKey();
                if (metric === "participation") {
                    participation = nextValue;
                } else if (metric === "accuracy") {
                    accuracy = nextValue;
                }
                recordStrategyChange(prev);
                updateScenarioLabel();
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

    function setupMiniMapInteraction() {
        if (!miniMapEl) return;

        miniMapEl.addEventListener("wheel", function (event) {
            if (!miniMapView.base) return;
            event.preventDefault();
            var delta = event.deltaY > 0 ? -MINI_MAP_ZOOM_STEP : MINI_MAP_ZOOM_STEP;
            zoomMiniMapAt(event.clientX, event.clientY, delta);
        }, { passive: false });

        miniMapEl.addEventListener("pointerdown", function (event) {
            if (event.button !== 0 || !miniMapView.base) return;
            var nodeTarget = event.target.closest(".nav-mini-node");
            miniMapPanState = {
                pointerId: event.pointerId,
                startX: event.clientX,
                startY: event.clientY,
                startPanX: miniMapView.panX,
                startPanY: miniMapView.panY,
                moved: false,
                nodeTarget: nodeTarget,
                nodeId: nodeTarget ? nodeTarget.dataset.nodeId : null,
            };
            if (miniMapView.scale > 1 && miniMapEl.setPointerCapture) {
                miniMapEl.setPointerCapture(event.pointerId);
            }
        });

        miniMapEl.addEventListener("pointermove", function (event) {
            if (!miniMapPanState || miniMapPanState.pointerId !== event.pointerId) return;
            var dx = event.clientX - miniMapPanState.startX;
            var dy = event.clientY - miniMapPanState.startY;
            if (!miniMapPanState.moved && (Math.abs(dx) > 5 || Math.abs(dy) > 5)) {
                miniMapPanState.moved = true;
            }
            if (!miniMapPanState.moved || miniMapView.scale <= 1) return;
            var svg = getMiniMapSvg();
            if (!svg) return;
            var rect = svg.getBoundingClientRect();
            if (!rect.width || !rect.height) return;
            var vb = getCurrentMiniMapViewBox();
            miniMapView.panX = miniMapPanState.startPanX - dx * (vb.width / rect.width);
            miniMapView.panY = miniMapPanState.startPanY - dy * (vb.height / rect.height);
            miniMapEl.classList.add("is-panning");
            applyMiniMapView();
        });

        function finishMiniMapPointer(event) {
            if (!miniMapPanState || miniMapPanState.pointerId !== event.pointerId) return;
            miniMapEl.classList.remove("is-panning");
            if (miniMapEl.releasePointerCapture && miniMapEl.hasPointerCapture(event.pointerId)) {
                miniMapEl.releasePointerCapture(event.pointerId);
            }
            if (!miniMapPanState.moved && miniMapPanState.nodeTarget) {
                var nodeId = miniMapPanState.nodeId;
                if (nodeId && visited.indexOf(nodeId) >= 0 && nodeId !== currentNodeId &&
                    !navigationCompleted && !isTransitioning) {
                    jumpToVisitedNode(nodeId, "mini_map");
                }
            }
            miniMapPanState = null;
        }

        miniMapEl.addEventListener("pointerup", finishMiniMapPointer);
        miniMapEl.addEventListener("pointercancel", finishMiniMapPointer);
    }

    function getMiniMapSvg() {
        return miniMapEl ? miniMapEl.querySelector(".nav-mini-graph") : null;
    }

    function getCurrentMiniMapViewBox() {
        var base = miniMapView.base;
        return {
            x: miniMapView.panX,
            y: miniMapView.panY,
            width: base.width / miniMapView.scale,
            height: base.height / miniMapView.scale,
        };
    }

    function applyMiniMapView() {
        var svg = getMiniMapSvg();
        if (!svg || !miniMapView.base) return;
        var base = miniMapView.base;
        if (miniMapView.scale <= 1) {
            miniMapView.scale = 1;
            miniMapView.panX = 0;
            miniMapView.panY = 0;
        }
        var width = base.width / miniMapView.scale;
        var height = base.height / miniMapView.scale;
        var maxPanX = Math.max(0, base.width - width);
        var maxPanY = Math.max(0, base.height - height);
        miniMapView.panX = Math.max(0, Math.min(maxPanX, miniMapView.panX));
        miniMapView.panY = Math.max(0, Math.min(maxPanY, miniMapView.panY));
        svg.setAttribute("viewBox", miniMapView.panX + " " + miniMapView.panY + " " + width + " " + height);
        updateMiniMapZoomLabel();
        if (miniMapEl) {
            miniMapEl.classList.toggle("is-zoomed", miniMapView.scale > 1);
        }
    }

    function updateMiniMapZoomLabel() {
        if (miniMapZoomLabelEl) {
            miniMapZoomLabelEl.textContent = Math.round(miniMapView.scale * 100) + "%";
        }
    }

    function resetMiniMapView() {
        miniMapView.scale = 1;
        miniMapView.panX = 0;
        miniMapView.panY = 0;
        applyMiniMapView();
    }

    function zoomMiniMapByStep(stepDelta) {
        if (!miniMapEl) return;
        var rect = miniMapEl.getBoundingClientRect();
        zoomMiniMapAt(rect.left + rect.width / 2, rect.top + rect.height / 2, stepDelta);
    }

    function zoomMiniMapAt(clientX, clientY, stepDelta) {
        if (!miniMapView.base) return;
        var oldScale = miniMapView.scale;
        var newScale = Math.max(MINI_MAP_ZOOM_MIN, Math.min(MINI_MAP_ZOOM_MAX, oldScale + stepDelta));
        if (newScale === oldScale) return;

        var svg = getMiniMapSvg();
        if (!svg) return;
        var rect = svg.getBoundingClientRect();
        if (!rect.width || !rect.height) return;
        var vb = getCurrentMiniMapViewBox();
        var focalX = (clientX - rect.left) / rect.width * vb.width + vb.x;
        var focalY = (clientY - rect.top) / rect.height * vb.height + vb.y;

        miniMapView.scale = newScale;
        if (newScale <= 1) {
            miniMapView.scale = 1;
            miniMapView.panX = 0;
            miniMapView.panY = 0;
        } else {
            var newWidth = miniMapView.base.width / newScale;
            var newHeight = miniMapView.base.height / newScale;
            var oldWidth = miniMapView.base.width / oldScale;
            var oldHeight = miniMapView.base.height / oldScale;
            miniMapView.panX = focalX - (focalX - miniMapView.panX) * (newWidth / oldWidth);
            miniMapView.panY = focalY - (focalY - miniMapView.panY) * (newHeight / oldHeight);
        }
        applyMiniMapView();
    }

    function jumpToVisitedNode(nodeId, source) {
        var index = visited.indexOf(nodeId);
        if (index < 0 || nodeId === currentNodeId || navigationCompleted || isTransitioning) return;
        finishCurrentNodeVisit();
        recordEvent(source + "_jump", { from_node_id: currentNodeId, to_node_id: nodeId });
        currentNodeId = nodeId;
        currentNode = findNode(nodeId);
        visited = visited.slice(0, index + 1);
        animateTransition(function () {
            displayCurrentQuestion();
            beginNodeVisit(currentNodeId, source);
            updateProgress();
            renderMiniMap();
            updateNavActionButtons();
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
        controlsEl.style.display = "grid";
        if (pageEl) pageEl.classList.remove("is-completed");
        statusBadgeEl.textContent = "导航中";
        statusBadgeEl.classList.add("active");
        navigationCompleted = false;
        currentNodeId = firstNodeId;
        visited = [firstNodeId];
        currentNode = findNode(firstNodeId);
        resetReviewState();
        hideDispatchReason();
        if (completedCardEl) completedCardEl.style.display = "none";
        if (questionCardEl) questionCardEl.style.display = "flex";
        if (toolPanelEl) toolPanelEl.style.display = "flex";
        if (miniMapShellEl) miniMapShellEl.style.display = "block";
        displayCurrentQuestion();
        beginNodeVisit(firstNodeId, "start");
        updateProgress();
        updateScenarioLabel();
        renderMiniMap();
        updateNavActionButtons();
    }

    function handleGoBack() {
        if (isTransitioning || navigationCompleted || visited.length <= 1) return;
        isTransitioning = true;
        finishCurrentNodeVisit();
        updateNavActionButtons();
        var fromNodeId = currentNodeId;
        visited.pop();
        currentNodeId = visited[visited.length - 1];
        currentNode = findNode(currentNodeId);
        recordEvent("back", { from_node_id: fromNodeId, to_node_id: currentNodeId });
        animateTransition(function () {
            displayCurrentQuestion();
            beginNodeVisit(currentNodeId, "back");
            updateProgress();
            renderMiniMap();
            updateNavActionButtons();
        });
    }

    function handleDispatch() {
        if (isTransitioning || navigationCompleted) return;
        isTransitioning = true;
        finishCurrentNodeVisit();
        var fromNodeId = currentNodeId;
        recordEvent("dispatch_request", {
            from_node_id: fromNodeId,
            participation: participation,
            accuracy: accuracy,
            scenario_key: getScenarioKey(),
        });
        updateNavActionButtons();
        requestDispatch()
            .then(function (result) {
                lastDispatchMeta = result.dispatch_meta || buildFallbackDispatchMeta(result);
                showDispatchReason(lastDispatchMeta, result.next_node || findNode(result.next_node_id));
                if (result.completed || !result.next_node_id) {
                    recordEvent("completed", { from_node_id: fromNodeId, dispatch_meta: lastDispatchMeta });
                    showCompleted();
                    return;
                }
                currentNodeId = result.next_node_id;
                visited.push(currentNodeId);
                currentNode = result.next_node || findNode(currentNodeId);
                recordEvent("dispatch_result", {
                    from_node_id: fromNodeId,
                    to_node_id: currentNodeId,
                    dispatch_meta: lastDispatchMeta,
                });
                animateTransition(function () {
                    displayCurrentQuestion();
                    beginNodeVisit(currentNodeId, "dispatch");
                    updateProgress();
                    renderMiniMap();
                });
            })
            .catch(function (err) {
                console.error("Dispatch error:", err);
                beginNodeVisit(currentNodeId, "dispatch_error");
                isTransitioning = false;
                updateNavActionButtons();
            });
    }

    function handleRestart() {
        stopTimer();
        finishCurrentNodeVisit();
        navigationCompleted = false;
        if (pageEl) pageEl.classList.remove("is-completed");
        if (controlsEl) controlsEl.style.display = "grid";
        resetReviewState();
        hideDispatchReason();
        if (completedCardEl) completedCardEl.style.display = "none";
        if (questionCardEl) questionCardEl.style.display = "flex";
        if (toolPanelEl) toolPanelEl.style.display = "flex";
        if (miniMapShellEl) miniMapShellEl.style.display = "block";
        statusBadgeEl.textContent = "导航中";
        statusBadgeEl.classList.remove("completed");
        statusBadgeEl.classList.add("active");
        var firstNode = getFirstMainNode();
        if (!firstNode) return;
        currentNodeId = firstNode.id;
        visited = [firstNode.id];
        currentNode = firstNode;
        displayCurrentQuestion();
        beginNodeVisit(firstNode.id, "restart");
        updateProgress();
        updateScenarioLabel();
        renderMiniMap();
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
            visualAidFrameEl.onload = fitVisualAidFrame;
            visualAidFrameEl.srcdoc = html;
            visualAidFrameEl.style.display = "block";
            visualAidEl.style.display = "flex";
            visualAidHintEl.style.display = "none";
            requestAnimationFrame(fitVisualAidFrame);
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

    function fitVisualAidFrame() {
        if (!visualAidFrameEl || !visualAidEl) return;
        if (visualAidEl.style.display === "none" || visualAidFrameEl.style.display === "none") return;
        var pw = visualAidEl.clientWidth;
        var ph = visualAidEl.clientHeight;
        if (!pw || !ph) return;
        var scale = Math.min(pw / VA_DESIGN_W, ph / VA_DESIGN_H);
        var x = (pw - VA_DESIGN_W * scale) / 2;
        var y = (ph - VA_DESIGN_H * scale) / 2;
        visualAidFrameEl.style.setProperty("--va-w", VA_DESIGN_W + "px");
        visualAidFrameEl.style.setProperty("--va-h", VA_DESIGN_H + "px");
        visualAidFrameEl.style.setProperty("--va-scale", scale);
        visualAidFrameEl.style.setProperty("--va-x", x + "px");
        visualAidFrameEl.style.setProperty("--va-y", y + "px");
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

    function updateProgress() {
        var total = teachingMap ? teachingMap.nodes.length : 0;
        progressTextEl.textContent = "已访问 " + visited.length + " / " + total;
    }

    function updateScenarioLabel() {
        var key = getScenarioKey();
        var detail = SCENARIO_DETAILS[key] || {};
        if (scenarioTextEl) scenarioTextEl.textContent = detail.label || SCENARIO_LABELS[key] || "";
        if (scenarioHintEl) scenarioHintEl.textContent = detail.hint || "";
        if (scenarioStateEl) scenarioStateEl.textContent = formatScenarioState(participation, accuracy);
        if (scenarioIndicatorEl) scenarioIndicatorEl.dataset.scenario = key;
        if (strategyMatrixEl) {
            strategyMatrixEl.dataset.scenario = key;
            strategyMatrixEl.querySelectorAll(".nav-signal-toggle").forEach(function (btn) {
                var metric = btn.dataset.metric || "";
                var value = metric === "participation" ? participation : accuracy;
                var isHigh = value === "high";
                btn.dataset.state = value;
                btn.classList.toggle("is-high", isHigh);
                btn.classList.toggle("is-low", !isHigh);
                btn.querySelectorAll(".nav-signal-choice").forEach(function (choice) {
                    var active = choice.dataset.value === value;
                    choice.classList.toggle("is-active", active);
                    choice.setAttribute("aria-pressed", active ? "true" : "false");
                });
            });
        }
    }

    function formatScenarioState(participationValue, accuracyValue) {
        return "参与" + (participationValue === "high" ? "高" : "低") +
            " / 准确" + (accuracyValue === "high" ? "高" : "低");
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
        if (pageEl) pageEl.classList.add("is-completed");
        if (questionCardEl) questionCardEl.style.display = "none";
        if (toolPanelEl) toolPanelEl.style.display = "none";
        if (miniMapShellEl) miniMapShellEl.style.display = "none";
        if (controlsEl) controlsEl.style.display = "none";
        if (completedCardEl) completedCardEl.style.display = "block";
        statusBadgeEl.textContent = "已完成";
        statusBadgeEl.classList.remove("active");
        statusBadgeEl.classList.add("completed");
        updateNavActionButtons();
    }

    function showDispatchReason(meta, nextNode) {
        if (!dispatchReasonEl || !dispatchReasonTextEl) return;
        var detail = meta || {};
        var nodeLabel = nextNode && nextNode.id ? " → " + nextNode.id : "";
        if (dispatchReasonLabelEl) {
            dispatchReasonLabelEl.textContent = (detail.action_label || "调度理由") + nodeLabel;
        }
        dispatchReasonTextEl.textContent = detail.reason_text || "系统已根据当前课堂状态完成下一步调度。";
        dispatchReasonEl.style.display = "flex";
    }

    function hideDispatchReason() {
        lastDispatchMeta = null;
        if (dispatchReasonEl) dispatchReasonEl.style.display = "none";
        if (dispatchReasonTextEl) dispatchReasonTextEl.textContent = "";
    }

    function buildFallbackDispatchMeta(result) {
        var key = getScenarioKey();
        var detail = SCENARIO_DETAILS[key] || {};
        var completed = !!(result && (result.completed || !result.next_node_id));
        var nextNode = result && result.next_node ? result.next_node : findNode(result && result.next_node_id);
        var qType = nextNode ? (nextNode.question_type || "main") : "";
        return {
            scenario_key: key,
            scenario_label: detail.label || SCENARIO_LABELS[key] || "",
            action_label: completed ? "导航完成" : (detail.action || "调度下一题"),
            reason_text: completed ? "当前教学地图中可继续调度的节点已经完成，系统结束本次导航。" : buildDispatchReasonText(key, qType),
        };
    }

    function buildDispatchReasonText(key, qType) {
        var typeText = TYPE_LABELS[qType] || "问题";
        if (key === "high_high") return "当前参与度和准确率都较高，系统优先调度" + typeText + "，推动学生继续进阶。";
        if (key === "high_low") return "当前参与度较高但准确率偏低，系统优先调度" + typeText + "，帮助学生修复关键认知断点。";
        if (key === "low_high") return "当前准确率较高但参与度偏低，系统优先调度" + typeText + "，用新情境或变式重新激活学生。";
        return "当前参与度和准确率都偏低，系统优先调度" + typeText + "，先降低入口门槛再恢复课堂思考。";
    }

    function renderMiniMap() {
        if (!miniMapEl || !teachingMap || !teachingMap.nodes) return;
        var graph = buildMiniGraphModel();
        if (!graph.nodes.length) {
            miniMapEl.innerHTML = '<p class="nav-empty-text">暂无可展示的节点。</p>';
            miniMapView.base = null;
            return;
        }
        var bounds = graph.bounds;
        var edgeHtml = graph.edges.map(renderMiniGraphEdge).join("");
        var nodeHtml = graph.nodes.map(renderMiniGraphNode).join("");
        var padX = bounds.padX || 0;
        var padY = bounds.padY || 0;
        miniMapEl.innerHTML = '<svg class="nav-mini-graph" viewBox="0 0 ' + bounds.width + " " + bounds.height +
            '" preserveAspectRatio="xMidYMid meet" role="img" aria-label="教学导航节点图">' +
            '<defs><marker id="navMiniArrow" markerWidth="4" markerHeight="4" refX="3.5" refY="2" orient="auto" markerUnits="strokeWidth">' +
            '<path d="M0,0 L4,2 L0,4 Z" fill="currentColor"></path></marker></defs>' +
            '<g class="nav-mini-graph-edges" transform="translate(' + padX + ',' + padY + ')">' + edgeHtml + '</g>' +
            '<g class="nav-mini-graph-nodes" transform="translate(' + padX + ',' + padY + ')">' + nodeHtml + '</g>' +
            '</svg>';
        miniMapView.base = { width: bounds.width, height: bounds.height };
        applyMiniMapView();
    }

    function buildMiniGraphModel() {
        var rawNodes = (teachingMap.nodes || []).filter(function (node) { return node && node.id; });
        var mainNodes = rawNodes.filter(function (node) {
            return (node.question_type || "main") === "main";
        }).sort(sortNodeById);

        var variantBuckets = {};
        var scaffoldBuckets = {};
        var fallbackMainId = mainNodes[0] && mainNodes[0].id;
        rawNodes.forEach(function (node) {
            var qType = node.question_type || "main";
            if (qType === "main") return;
            var unitId = getNodeUnitId(node, fallbackMainId);
            if (qType === "variant") {
                if (!variantBuckets[unitId]) variantBuckets[unitId] = [];
                variantBuckets[unitId].push(node);
            } else if (qType === "scaffold") {
                if (!scaffoldBuckets[unitId]) scaffoldBuckets[unitId] = [];
                scaffoldBuckets[unitId].push(node);
            }
        });

        Object.keys(variantBuckets).forEach(function (key) { variantBuckets[key].sort(sortNodeById); });
        Object.keys(scaffoldBuckets).forEach(function (key) { scaffoldBuckets[key].sort(sortNodeById); });

        var layout = layoutMiniGraph(rawNodes, mainNodes, variantBuckets, scaffoldBuckets);
        var edges = getMiniGraphEdges(rawNodes, layout.nodeMap);
        return { nodes: layout.nodes, edges: edges, bounds: layout.bounds };
    }

    function layoutMiniGraph(rawNodes, mainNodes, variantBuckets, scaffoldBuckets) {
        var laneTop = 42;
        var laneMain = 118;
        var laneBottom = 194;
        var marginX = 56;
        var stepX = 104;
        var variantStep = 42;
        var scaffoldStep = 42;
        var nodeMap = {};
        var positioned = [];

        mainNodes.forEach(function (node, index) {
            addPositionedNode(node, marginX + index * stepX, laneMain, positioned, nodeMap);
        });

        mainNodes.forEach(function (mainNode, index) {
            var baseX = marginX + index * stepX;
            var variants = variantBuckets[mainNode.id] || [];
            var variantStart = baseX - ((variants.length - 1) * variantStep) / 2;
            variants.forEach(function (node, offset) {
                addPositionedNode(node, variantStart + offset * variantStep, laneTop, positioned, nodeMap);
            });

            var scaffolds = scaffoldBuckets[mainNode.id] || [];
            var scaffoldStart = baseX - ((scaffolds.length - 1) * scaffoldStep) / 2;
            scaffolds.forEach(function (node, offset) {
                addPositionedNode(node, scaffoldStart + offset * scaffoldStep, laneBottom, positioned, nodeMap);
            });
        });

        rawNodes.forEach(function (node, index) {
            if (nodeMap[node.id]) return;
            addPositionedNode(node, marginX + index * 56, laneBottom + 60, positioned, nodeMap);
        });

        var maxX = positioned.reduce(function (max, node) { return Math.max(max, node.x); }, marginX);
        var maxY = positioned.reduce(function (max, node) { return Math.max(max, node.y); }, laneBottom);
        var padX = 48;
        var padY = 44;
        return {
            nodes: positioned,
            nodeMap: nodeMap,
            bounds: {
                width: Math.max(360, Math.ceil(maxX + marginX)) + padX * 2,
                height: Math.max(240, Math.ceil(maxY + 56)) + padY * 2,
                padX: padX,
                padY: padY,
            },
        };
    }

    function addPositionedNode(node, x, y, positioned, nodeMap) {
        var qType = node.question_type || "main";
        var viewNode = {
            id: node.id,
            content: node.content || "",
            qType: qType,
            x: Math.round(x),
            y: Math.round(y),
            visited: visited.indexOf(node.id) >= 0,
            current: node.id === currentNodeId,
        };
        positioned.push(viewNode);
        nodeMap[node.id] = viewNode;
    }

    function getMiniGraphEdges(rawNodes, nodeMap) {
        var edges = [];
        var seen = {};
        function addEdge(source, target, relation) {
            if (!source || !target || source === target || !nodeMap[source] || !nodeMap[target]) return;
            var key = source + "|" + target + "|" + (relation || "");
            if (seen[key]) return;
            seen[key] = true;
            edges.push({
                source: nodeMap[source],
                target: nodeMap[target],
                relation: relation || "fallback",
            });
        }

        (teachingMap.edges || []).forEach(function (edge) {
            addEdge(edge.source || edge.from, edge.target || edge.to, edge.relation || "fallback");
        });

        var mainNodes = rawNodes.filter(function (node) {
            return (node.question_type || "main") === "main";
        }).sort(sortNodeById);
        for (var i = 0; i < mainNodes.length - 1; i++) {
            addEdge(mainNodes[i].id, mainNodes[i + 1].id, "sequence");
        }

        rawNodes.forEach(function (node) {
            var qType = node.question_type || "main";
            if (qType === "variant") {
                addEdge(node.main_id || node.parent_id, node.id, "variant_of");
            } else if (qType === "scaffold") {
                var fromId = node.from_id || node.from_main_id || node.main_id || node.parent_id;
                var toId = node.to_id || node.to_main_id;
                addEdge(fromId, node.id, "scaffold_from");
                if (toId) addEdge(node.id, toId, "scaffold_to");
            }
        });

        return edges;
    }

    function renderMiniGraphEdge(edge) {
        var cls = "nav-mini-graph-edge relation-" + miniRelationClass(edge.relation || "fallback");
        var path = buildMiniEdgePath(edge.source, edge.target, edge.relation);
        return '<path class="' + cls + '" d="' + path + '" marker-end="url(#navMiniArrow)"></path>';
    }

    function buildMiniEdgePath(source, target, relation) {
        var sx = source.x;
        var sy = source.y;
        var tx = target.x;
        var ty = target.y;
        if (relation === "variant_of") {
            return "M" + sx + " " + (sy - 9) + " C " + sx + " " + (sy - 36) + ", " + tx + " " + (ty + 36) + ", " + tx + " " + (ty + 9);
        }
        if (relation === "scaffold_from" || relation === "scaffold_to" || relation === "scaffold_sequence") {
            return "M" + sx + " " + (sy + 9) + " C " + sx + " " + (sy + 36) + ", " + tx + " " + (ty - 36) + ", " + tx + " " + (ty - 9);
        }
        return "M" + (sx + 13) + " " + sy + " L " + (tx - 13) + " " + ty;
    }

    function renderMiniGraphNode(node) {
        var classes = ["nav-mini-node", "type-" + node.qType];
        if (node.visited) classes.push("is-visited");
        if (node.current) classes.push("is-current");
        var disabled = node.visited && !node.current ? "" : " is-disabled";
        var title = escapeHtml((TYPE_LABELS[node.qType] || node.qType) + " " + node.id + " " + (node.content || ""));
        return '<g class="' + classes.join(" ") + disabled + '" data-node-id="' + escapeAttr(node.id) +
            '" transform="translate(' + node.x + " " + node.y + ')">' +
            '<title>' + title + '</title>' +
            '<rect class="nav-mini-node-box" x="-13" y="-9" width="26" height="18" rx="0"></rect>' +
            '<text class="nav-mini-node-label" text-anchor="middle" dominant-baseline="central">' + escapeHtml(node.id) + '</text>' +
            (node.visited ? '<text class="nav-mini-node-check" x="15" y="-8" text-anchor="middle">✓</text>' : "") +
            '</g>';
    }

    function getNodeUnitId(node, fallbackMainId) {
        return node.main_id || node.parent_id || node.from_id || node.from_main_id || fallbackMainId || "";
    }

    function escapeAttr(text) {
        return escapeHtml(text).replace(/"/g, "&quot;");
    }

    function miniRelationClass(relation) {
        return String(relation || "fallback").replace(/[^a-zA-Z0-9_-]/g, "_");
    }

    function toggleMiniMap() {
        if (!miniMapShellEl || !miniMapToggleEl) return;
        var collapsed = miniMapShellEl.classList.toggle("is-collapsed");
        miniMapToggleEl.textContent = collapsed ? "展开" : "收起";
        miniMapToggleEl.setAttribute("aria-expanded", collapsed ? "false" : "true");
        syncDeckHeight();
    }

    function animateTransition(callback) {
        questionCardEl.classList.add("animating-out");
        setTimeout(function () {
            questionCardEl.classList.remove("animating-out");
            callback();
            questionCardEl.classList.add("animating-in");
            requestAnimationFrame(fitVisualAidFrame);
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
        requestAnimationFrame(fitVisualAidFrame);
    }

    function toggleProjectorMode() {
        var active = pageEl.classList.toggle("nav-projector");
        projectorToggleEl.classList.toggle("is-active", active);
        projectorToggleEl.setAttribute("aria-pressed", active ? "true" : "false");
        requestAnimationFrame(fitVisualAidFrame);
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

    function resetReviewState() {
        navEvents = [];
        nodeTimeStats = {};
        strategyHistory = [];
        currentNodeEnteredAt = null;
        recordStrategyChange(null, true);
    }

    function beginNodeVisit(nodeId, source) {
        if (!nodeId) return;
        currentNodeEnteredAt = Date.now();
        recordEvent("enter_node", { node_id: nodeId, source: source || "navigation" });
    }

    function finishCurrentNodeVisit() {
        if (!currentNodeId || !currentNodeEnteredAt) return;
        var elapsed = Math.max(0, Math.round((Date.now() - currentNodeEnteredAt) / 1000));
        nodeTimeStats[currentNodeId] = (nodeTimeStats[currentNodeId] || 0) + elapsed;
        recordEvent("leave_node", { node_id: currentNodeId, elapsed_seconds: elapsed });
        currentNodeEnteredAt = null;
    }

    function recordStrategyChange(previousKey, force) {
        var key = getScenarioKey();
        if (!force && previousKey === key) return;
        strategyHistory.push({
            time: new Date().toISOString(),
            scenario_key: key,
            scenario_label: (SCENARIO_DETAILS[key] && SCENARIO_DETAILS[key].label) || SCENARIO_LABELS[key] || key,
            participation: participation,
            accuracy: accuracy,
            node_id: currentNodeId,
        });
        recordEvent("strategy_change", { scenario_key: key, from: previousKey || "", node_id: currentNodeId });
    }

    function recordEvent(type, detail) {
        navEvents.push({
            type: type,
            time: new Date().toISOString(),
            detail: detail || {},
        });
    }

    function getScenarioKey() {
        return participation + "_" + accuracy;
    }

    function downloadReviewMarkdown() {
        var wasTiming = !!currentNodeEnteredAt;
        if (wasTiming) finishCurrentNodeVisit();
        var markdown = buildReviewMarkdown();
        if (wasTiming && !navigationCompleted) beginNodeVisit(currentNodeId, "review_resume");
        var blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
        var url = URL.createObjectURL(blob);
        var link = document.createElement("a");
        var filename = "教学导航复盘_" + TASK_ID + "_" + formatDateStamp(new Date()) + ".md";
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
    }

    function buildReviewMarkdown() {
        var lines = [];
        var uniqueVisited = [];
        visited.forEach(function (id) {
            if (uniqueVisited.indexOf(id) < 0) uniqueVisited.push(id);
        });
        var coveredKnowledge = collectCoveredKnowledge(uniqueVisited);
        lines.push("# 教学导航复盘");
        lines.push("");
        lines.push("- 任务 ID：" + TASK_ID);
        lines.push("- 生成时间：" + new Date().toLocaleString());
        lines.push("- 访问路径：" + (visited.length ? visited.join(" → ") : "无"));
        lines.push("- 覆盖节点：" + uniqueVisited.length + " / " + ((teachingMap && teachingMap.nodes && teachingMap.nodes.length) || 0));
        lines.push("- 策略切换次数：" + Math.max(0, strategyHistory.length - 1));
        lines.push("- 覆盖知识点：" + (coveredKnowledge.length ? coveredKnowledge.join("、") : "未记录"));
        lines.push("");
        lines.push("## 节点停留与便签");
        uniqueVisited.forEach(function (id) {
            var node = findNode(id) || {};
            var note = localStorage.getItem(noteKey(id)) || "";
            lines.push("");
            lines.push("### " + id + " " + (TYPE_LABELS[node.question_type || "main"] || ""));
            lines.push("- 停留时间：" + formatDuration(nodeTimeStats[id] || 0));
            lines.push("- 知识点：" + ((node.knowledge_points || []).join("、") || "未记录"));
            lines.push("- 问题：" + sanitizeMarkdownLine(node.content || ""));
            if (note) lines.push("- 教师便签：" + sanitizeMarkdownLine(note));
        });
        lines.push("");
        lines.push("## 策略变化");
        strategyHistory.forEach(function (item, index) {
            lines.push((index + 1) + ". " + item.scenario_label + "（参与度：" + labelBinary(item.participation) +
                "，准确率：" + labelBinary(item.accuracy) + "，节点：" + (item.node_id || "起始") + "）");
        });
        lines.push("");
        lines.push("## 调度事件");
        navEvents.filter(function (event) {
            return event.type === "dispatch_result" || event.type === "completed" || event.type === "back";
        }).forEach(function (event) {
            var detail = event.detail || {};
            var meta = detail.dispatch_meta || {};
            lines.push("- " + event.type + "：" + (detail.from_node_id || "") +
                (detail.to_node_id ? " → " + detail.to_node_id : "") +
                (meta.reason_text ? "；" + meta.reason_text : ""));
        });
        lines.push("");
        return lines.join("\n");
    }

    function collectCoveredKnowledge(nodeIds) {
        var seen = {};
        nodeIds.forEach(function (id) {
            var node = findNode(id);
            (node && node.knowledge_points || []).forEach(function (kp) {
                if (kp) seen[kp] = true;
            });
        });
        return Object.keys(seen);
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

    function sortNodeById(a, b) {
        var an = extractNumber(a.id);
        var bn = extractNumber(b.id);
        if (an !== bn) return an - bn;
        return String(a.id || "").localeCompare(String(b.id || ""));
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

    function formatDuration(seconds) {
        var value = Math.max(0, Number(seconds) || 0);
        var min = Math.floor(value / 60);
        var sec = value % 60;
        if (min <= 0) return sec + " 秒";
        return min + " 分 " + pad2(sec) + " 秒";
    }

    function formatDateStamp(date) {
        return date.getFullYear() + pad2(date.getMonth() + 1) + pad2(date.getDate()) +
            "_" + pad2(date.getHours()) + pad2(date.getMinutes()) + pad2(date.getSeconds());
    }

    function sanitizeMarkdownLine(text) {
        return String(text || "").replace(/\s+/g, " ").trim();
    }

    function labelBinary(value) {
        return value === "high" ? "高" : "低";
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
