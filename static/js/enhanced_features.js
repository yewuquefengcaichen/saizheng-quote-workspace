/**
 * 一键报价系统 - 增强功能
 * 包含：主题系统、快捷键、拖拽上传、数据可视化
 */

// =============== 顶部工作台挂载 ===============
function getWorkspaceActionHost() {
    let host = document.getElementById('workspaceActionHost');
    if (host) return host;

    const topbarActions = document.querySelector('.workspace-topbar-actions');
    if (!topbarActions) return null;

    host = document.createElement('div');
    host.id = 'workspaceActionHost';
    host.className = 'workspace-topbar-utility';
    topbarActions.appendChild(host);
    return host;
}

function mountWorkspaceAction(actionId, element, { prepend = false } = {}) {
    const host = getWorkspaceActionHost();
    if (!host) return null;

    const existing = host.querySelector(`[data-workspace-action="${actionId}"]`);
    if (existing) return existing;

    let node = element;
    if (typeof element === 'string') {
        const wrapper = document.createElement('div');
        wrapper.innerHTML = element.trim();
        node = wrapper.firstElementChild;
    }

    if (!node) return null;
    node.setAttribute('data-workspace-action', actionId);

    if (prepend) {
        host.prepend(node);
    } else {
        host.appendChild(node);
    }

    return node;
}

function setWorkspacePageContext(tab = 'upload') {
    document.body.setAttribute('data-scene-tab', tab || 'upload');
}

window.getWorkspaceActionHost = getWorkspaceActionHost;
window.mountWorkspaceAction = mountWorkspaceAction;
window.setWorkspacePage = setWorkspacePageContext;

// =============== 主题管理 ===============
const ThemeManager = {
    currentTheme: 'light',
    hasStoredPreference: false,
    systemThemeMedia: null,
    systemThemeBound: false,
    themes: {
        light: { label: 'Pearl Ledger', icon: 'bi bi-sun-fill' },
        dark: { label: 'Obsidian Control', icon: 'bi bi-moon-stars-fill' }
    },

    init() {
        const savedTheme = localStorage.getItem('quote-theme');
        this.hasStoredPreference = !!savedTheme;
        this.systemThemeMedia = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;
        const initialTheme = savedTheme || this.getSystemTheme();
        this.createToggleButton();
        this.bindSystemPreference();
        this.setTheme(initialTheme, false);
    },

    getSystemTheme() {
        return this.systemThemeMedia?.matches ? 'dark' : 'light';
    },

    bindSystemPreference() {
        if (!this.systemThemeMedia || this.systemThemeBound) {
            return;
        }

        const handleThemeChange = (event) => {
            if (this.hasStoredPreference) {
                return;
            }

            this.setTheme(event.matches ? 'dark' : 'light', false);
        };

        if (typeof this.systemThemeMedia.addEventListener === 'function') {
            this.systemThemeMedia.addEventListener('change', handleThemeChange);
        } else if (typeof this.systemThemeMedia.addListener === 'function') {
            this.systemThemeMedia.addListener(handleThemeChange);
        }

        this.systemThemeBound = true;
    },

    setTheme(theme, save = true) {
        const nextTheme = this.themes[theme] ? theme : 'light';
        this.currentTheme = nextTheme;
        document.documentElement.setAttribute('data-theme', nextTheme);

        if (save) {
            localStorage.setItem('quote-theme', nextTheme);
            this.hasStoredPreference = true;
        }

        const toggleBtn = document.getElementById('themeToggleBtn');
        const icon = document.getElementById('themeIcon');
        const label = document.getElementById('themeLabel');

        if (toggleBtn) {
            toggleBtn.classList.toggle('is-dark', nextTheme === 'dark');
            const nextLabel = nextTheme === 'dark' ? this.themes.light.label : this.themes.dark.label;
            toggleBtn.setAttribute('title', `切换到 ${nextLabel}`);
            toggleBtn.setAttribute('aria-label', `切换到 ${nextLabel}`);
        }

        if (icon) {
            icon.className = `${this.themes[nextTheme].icon} fs-6`;
        }

        if (label) {
            label.textContent = this.themes[nextTheme].label;
        }

        document.dispatchEvent(new CustomEvent('themeChanged', { detail: { theme: nextTheme } }));
    },

    toggle() {
        const newTheme = this.currentTheme === 'light' ? 'dark' : 'light';
        this.setTheme(newTheme);
        showToast('success', `已切换到 ${this.themes[newTheme].label}`);
    },

    createToggleButton() {
        mountWorkspaceAction('theme-toggle', `
            <button type="button" class="workspace-action-btn workspace-theme-btn" id="themeToggleBtn" onclick="ThemeManager.toggle()">
                <span class="workspace-action-icon"><i id="themeIcon" class="bi bi-sun-fill fs-6"></i></span>
                <span class="workspace-action-copy">
                    <span class="workspace-action-label">Theme</span>
                    <span class="workspace-action-value" id="themeLabel">Pearl Ledger</span>
                </span>
            </button>
        `);
    }
};

window.ThemeManager = ThemeManager;

document.addEventListener('DOMContentLoaded', function() {
    const activeTab = document.querySelector('#mainTabs .nav-link.active')?.dataset.tab || document.body?.dataset?.sceneTab || 'upload';
    setWorkspacePageContext(activeTab);
});

const WorkspaceEntryActions = {
    ocrUnavailableToastTs: 0,

    shouldPreferTransientPicker(inputId) {
        const route = document.body?.dataset?.route || '';
        return route === 'quotes' && inputId === 'quoteFile';
    },

    triggerExistingInput(inputId) {
        const input = document.getElementById(inputId);
        if (!input) {
            return false;
        }

        input.value = '';
        input.click();
        return true;
    },

    openTransientFilePicker({ accept = '', multiple = false, onChange }) {
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = accept;
        input.multiple = !!multiple;
        input.tabIndex = -1;
        input.setAttribute('aria-hidden', 'true');
        input.style.position = 'fixed';
        input.style.left = '-9999px';
        input.style.top = '0';
        input.style.opacity = '0';

        const cleanup = () => {
            window.setTimeout(() => input.remove(), 0);
        };

        const cleanupOnFocus = () => {
            window.setTimeout(() => {
                if (!input.files?.length) {
                    cleanup();
                }
            }, 0);
            window.removeEventListener('focus', cleanupOnFocus, true);
        };

        input.addEventListener('change', () => {
            if (typeof onChange === 'function' && input.files?.length) {
                onChange(input);
            }
            cleanup();
        }, { once: true });

        document.body.appendChild(input);
        window.addEventListener('focus', cleanupOnFocus, true);
        input.click();
    },

    submitQuoteFiles(files) {
        if (!files?.length) {
            return false;
        }

        if (typeof smartUploadFile === 'function') {
            smartUploadFile({ files });
            return true;
        }

        if (typeof showToast === 'function') {
            showToast('warning', '报价上传入口尚未初始化');
        }
        return false;
    },

    submitProductsFiles(files) {
        if (!files?.length) {
            return false;
        }

        if (typeof uploadFile === 'function') {
            uploadFile({ files }, '/api/upload_products', (result) => {
                if (typeof handleProductsUploadSuccess === 'function') {
                    handleProductsUploadSuccess(result);
                }
            });
            return true;
        }

        if (typeof showToast === 'function') {
            showToast('warning', '商品库上传入口尚未初始化');
        }
        return false;
    },

    openQuoteUpload() {
        if (!this.shouldPreferTransientPicker('quoteFile') && this.triggerExistingInput('quoteFile')) {
            return;
        }

        this.openTransientFilePicker({
            accept: '.xls,.xlsx',
            onChange: (input) => {
                this.submitQuoteFiles(input.files);
            }
        });
    },

    openProductsUpload() {
        if (this.triggerExistingInput('productsFile')) {
            return;
        }

        this.openTransientFilePicker({
            accept: '.xls,.xlsx',
            onChange: (input) => {
                this.submitProductsFiles(input.files);
            }
        });
    },

    openOCRUpload() {
        if (!window.OCRManager) {
            this.showOcrUnavailableHint('OCR 模块尚未初始化，请稍后重试');
            return;
        }

        if (!window.OCRManager.available) {
            this.showOcrUnavailableHint(window.OCRManager.statusMessage || 'OCR服务不可用，请先安装 easyocr: pip install easyocr');
            return;
        }

        if (this.triggerExistingInput('ocrFile')) {
            return;
        }

        this.openTransientFilePicker({
            accept: 'image/*',
            onChange: (input) => {
                const file = input.files?.[0];
                if (!file) {
                    return;
                }
                window.OCRManager.processImage(file);
            }
        });
    },

    goTo(path) {
        if (path) {
            window.location.href = path;
        }
    },

    goToQuotes() {
        this.goTo('/quotes');
    },

    goToCatalog() {
        this.goTo('/catalog');
    },

    goToTemplates() {
        this.goTo('/templates');
    },

    goToGuide() {
        this.goTo('/guide');
    },

    showOcrUnavailableHint(message) {
        const now = Date.now();
        if (now - this.ocrUnavailableToastTs < 2500) {
            return;
        }

        this.ocrUnavailableToastTs = now;
        if (typeof showToast === 'function') {
            showToast('warning', message);
        }
    }
};

window.WorkspaceEntryActions = WorkspaceEntryActions;

// =============== 顶部快捷动作 ===============
const WorkspaceQuickActions = {
    init() {
        const route = document.body?.dataset?.route || 'dashboard';
        const actions = this.getActionsByRoute(route);

        actions
            .slice()
            .reverse()
            .forEach(action => {
                mountWorkspaceAction(action.id, this.renderAction(action), { prepend: true });
            });
    },

    getActionsByRoute(route) {
        switch (route) {
            case 'quotes':
                return [
                    { id: 'quick-quote-upload', kind: 'button', icon: 'bi-file-earmark-arrow-up', label: '上传报价', tone: 'primary', handler: 'WorkspaceEntryActions.openQuoteUpload()' },
                    { id: 'quick-ocr-upload', kind: 'button', icon: 'bi-camera', label: 'OCR', handler: 'WorkspaceEntryActions.openOCRUpload()', dataAttrs: 'data-ocr-entry="true"' },
                    { id: 'quick-products-page', kind: 'link', icon: 'bi-grid-3x3-gap', label: '商品库', href: '/catalog' }
                ];
            case 'catalog':
                return [
                    { id: 'quick-products-upload', kind: 'button', icon: 'bi-box-arrow-in-up-right', label: '更新商品库', tone: 'primary', handler: 'WorkspaceEntryActions.openProductsUpload()' },
                    { id: 'quick-quote-page', kind: 'link', icon: 'bi-layout-text-window', label: '去报价台', href: '/quotes' }
                ];
            case 'templates':
                return [
                    { id: 'quick-export-center', kind: 'button', icon: 'bi-box-arrow-up-right', label: '导出配置', tone: 'primary', handler: "WorkspaceQuickActions.triggerControl('openExportCenterBtn')" },
                    { id: 'quick-quote-page', kind: 'link', icon: 'bi-layout-text-window', label: '去报价台', href: '/quotes' }
                ];
            case 'history':
            case 'synonyms':
                return [
                    { id: 'quick-quote-upload', kind: 'button', icon: 'bi-file-earmark-arrow-up', label: '上传报价', tone: 'primary', handler: 'WorkspaceEntryActions.openQuoteUpload()' },
                    { id: 'quick-products-page', kind: 'link', icon: 'bi-grid-3x3-gap', label: '商品库', href: '/catalog' }
                ];
            case 'dashboard':
            default:
                return [
                    { id: 'quick-products-upload', kind: 'button', icon: 'bi-box-arrow-in-up-right', label: '上传商品库', tone: 'primary', handler: 'WorkspaceEntryActions.openProductsUpload()' },
                    { id: 'quick-quote-upload', kind: 'button', icon: 'bi-file-earmark-arrow-up', label: '上传报价', handler: 'WorkspaceEntryActions.openQuoteUpload()' },
                    { id: 'quick-ocr-upload', kind: 'button', icon: 'bi-camera', label: 'OCR', handler: 'WorkspaceEntryActions.openOCRUpload()', dataAttrs: 'data-ocr-entry="true"' }
                ];
        }
    },

    renderAction(action) {
        const toneClass = action.tone ? ` workspace-quick-btn--${action.tone}` : '';

        if (action.kind === 'link' && action.href) {
            return `
                <a href="${action.href}" class="workspace-quick-btn${toneClass}">
                    <i class="bi ${action.icon}"></i>
                    <span>${action.label}</span>
                </a>
            `;
        }

        return `
            <button type="button" class="workspace-quick-btn${toneClass}" ${action.dataAttrs || ''} onclick="${action.handler}">
                <i class="bi ${action.icon}"></i>
                <span>${action.label}</span>
            </button>
        `;
    },

    triggerControl(controlId) {
        const control = document.getElementById(controlId);
        if (control) {
            control.click();
            return;
        }

        if (typeof showToast === 'function') {
            showToast('warning', '当前页面还没有准备好这个入口');
        }
    }
};

window.WorkspaceQuickActions = WorkspaceQuickActions;

// =============== 快捷键管理 ===============
const ShortcutManager = {
    shortcuts: {
        'ctrl+u': { action: 'upload', description: '上传报价单' },
        'ctrl+e': { action: 'export', description: '导出报价单' },
        'ctrl+m': { action: 'match', description: '开始匹配' },
        'ctrl+d': { action: 'dashboard', description: '数据仪表盘' },
        'ctrl+/': { action: 'help', description: '显示快捷键帮助' },
        'escape': { action: 'close', description: '关闭弹窗' }
    },

    init() {
        document.addEventListener('keydown', (e) => this.handleKeydown(e));
        this.showHints();
    },

    handleKeydown(e) {
        // 忽略输入框中的快捷键
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
            if (e.key !== 'Escape') return;
        }

        const key = this.getComboKey(e);
        const shortcut = this.shortcuts[key];

        if (shortcut) {
            e.preventDefault();
            this.executeAction(shortcut.action);
        }
    },

    getComboKey(e) {
        const parts = [];
        if (e.ctrlKey || e.metaKey) parts.push('ctrl');
        if (e.shiftKey) parts.push('shift');
        if (e.altKey) parts.push('alt');
        parts.push(e.key.toLowerCase());
        return parts.join('+');
    },

    executeAction(action) {
        switch (action) {
            case 'upload':
                this.triggerUpload();
                break;
            case 'export':
                this.triggerExport();
                break;
            case 'match':
                this.triggerMatch();
                break;
            case 'dashboard':
                this.showDashboard();
                break;
            case 'help':
                this.showHelp();
                break;
            case 'close':
                this.closeModal();
                break;
        }
    },

    triggerUpload() {
        if (window.WorkspaceEntryActions?.openQuoteUpload) {
            window.WorkspaceEntryActions.openQuoteUpload();
            showToast('info', '请选择要上传的文件');
        }
    },

    triggerExport() {
        const exportBtn = document.getElementById('exportBtn') || document.querySelector('[onclick*="export"]');
        if (exportBtn) {
            exportBtn.click();
        } else {
            showToast('warning', '请先完成商品匹配');
        }
    },

    triggerMatch() {
        const matchBtn = document.querySelector('[onclick*="match"]') || document.getElementById('startMatchBtn');
        if (matchBtn) {
            matchBtn.click();
        }
    },

    showDashboard() {
        const dashboardBtn = document.getElementById('dashboardBtn');
        if (dashboardBtn) {
            dashboardBtn.click();
        } else {
            showToast('info', '数据仪表盘功能');
        }
    },

    showHelp() {
        const helpContent = Object.entries(this.shortcuts)
            .map(([key, config]) => `<div class="d-flex justify-content-between py-2 border-bottom">
                <span>${config.description}</span>
                <kbd class="shortcut-key">${this.formatKey(key)}</kbd>
            </div>`)
            .join('');

        showCustomModal('快捷键帮助', `<div class="shortcut-help">${helpContent}</div>`);
    },

    closeModal() {
        // 关闭Bootstrap模态框
        const modals = document.querySelectorAll('.modal.show');
        modals.forEach(modal => {
            const bsModal = bootstrap.Modal.getInstance(modal);
            if (bsModal) bsModal.hide();
        });

        // 关闭AI面板
        const aiPanel = document.getElementById('aiAssistantPanel');
        if (aiPanel && aiPanel.classList.contains('open')) {
            aiPanel.classList.remove('open');
        }
    },

    formatKey(key) {
        return key.replace('ctrl', 'Ctrl+')
                  .replace('shift', 'Shift+')
                  .replace('alt', 'Alt+')
                  .toUpperCase();
    },

    showHints() {
        // 在按钮上添加快捷键提示
        const hints = {
            'input[type="file"]': 'Ctrl+U',
            '#exportBtn': 'Ctrl+E'
        };

        Object.entries(hints).forEach(([selector, key]) => {
            const el = document.querySelector(selector);
            if (el && el.parentElement) {
                const hint = document.createElement('small');
                hint.className = 'shortcut-hint ms-2 text-muted';
                hint.innerHTML = `<kbd class="shortcut-key">${key}</kbd>`;
                el.parentElement.appendChild(hint);
            }
        });
    }
};

// =============== 拖拽上传 ===============
const DragDropManager = {
    init() {
        this.createOverlay();
        this.bindEvents();
    },

    createOverlay() {
        const overlay = document.createElement('div');
        overlay.id = 'dragOverlay';
        overlay.className = 'drag-overlay';
        overlay.innerHTML = `
            <div class="drag-overlay-content">
                <i class="bi bi-cloud-arrow-up"></i>
                <h3>释放文件以上传</h3>
                <p>支持 Excel (.xlsx, .xls) 和 CSV 文件</p>
            </div>
        `;
        document.body.appendChild(overlay);
    },

    bindEvents() {
        let dragCounter = 0;

        // 防止浏览器默认打开文件
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(event => {
            document.addEventListener(event, (e) => {
                e.preventDefault();
                e.stopPropagation();
            });
        });

        // 拖拽进入
        document.addEventListener('dragenter', (e) => {
            dragCounter++;
            if (e.dataTransfer.types.includes('Files')) {
                document.getElementById('dragOverlay').classList.add('active');
            }
        });

        // 拖拽离开
        document.addEventListener('dragleave', (e) => {
            dragCounter--;
            if (dragCounter === 0) {
                document.getElementById('dragOverlay').classList.remove('active');
            }
        });

        // 拖拽悬停
        document.addEventListener('dragover', (e) => {
            e.dataTransfer.dropEffect = 'copy';
        });

        // 释放文件
        document.addEventListener('drop', (e) => {
            dragCounter = 0;
            document.getElementById('dragOverlay').classList.remove('active');

            const files = e.dataTransfer.files;
            if (files.length > 0) {
                this.handleDrop(files);
            }
        });

        // 点击覆盖层关闭
        document.getElementById('dragOverlay').addEventListener('click', () => {
            document.getElementById('dragOverlay').classList.remove('active');
        });
    },

    handleDrop(files) {
        const file = files[0];
        const validTypes = ['.xlsx', '.xls', '.csv'];
        const ext = '.' + file.name.split('.').pop().toLowerCase();

        if (!validTypes.includes(ext)) {
            showToast('error', '不支持的文件格式，请上传 Excel 或 CSV 文件');
            return;
        }

        // 默认拖拽到报价单上传入口，避免误发到商品库接口
        const dt = new DataTransfer();
        dt.items.add(file);
        if (window.WorkspaceEntryActions?.submitQuoteFiles?.(dt.files)) {

            showToast('success', `已选择文件: ${file.name}`);
        }
    }
};

// =============== 数字动画 ===============
const NumberAnimator = {
    animate(element, targetValue, duration = 1000) {
        const startValue = parseFloat(element.textContent) || 0;
        const startTime = performance.now();
        const isDecimal = targetValue % 1 !== 0;

        function update(currentTime) {
            const elapsed = currentTime - startTime;
            const progress = Math.min(elapsed / duration, 1);

            // 缓动函数
            const easeOutQuart = 1 - Math.pow(1 - progress, 4);
            const currentValue = startValue + (targetValue - startValue) * easeOutQuart;

            element.textContent = isDecimal ? currentValue.toFixed(2) : Math.round(currentValue);

            if (progress < 1) {
                requestAnimationFrame(update);
            }
        }

        requestAnimationFrame(update);
    },

    animateAll(selector) {
        document.querySelectorAll(selector).forEach(el => {
            const target = parseFloat(el.dataset.target || el.textContent);
            if (!isNaN(target)) {
                this.animate(el, target);
            }
        });
    }
};

// =============== 进度条动画 ===============
const ProgressAnimator = {
    animate(element, targetPercent, duration = 1500) {
        element.style.width = '0%';

        setTimeout(() => {
            element.style.transition = `width ${duration}ms ease-out`;
            element.style.width = `${targetPercent}%`;
        }, 100);
    }
};

// =============== 图表管理 ===============
const ChartManager = {
    charts: {},

    colors: {
        primary: '#2563eb',
        success: '#10b981',
        warning: '#f59e0b',
        danger: '#ef4444',
        info: '#0ea5e9',
        accent: '#38bdf8'
    },

    getThemePalette(theme = ThemeManager.currentTheme || document.documentElement.getAttribute('data-theme') || 'light') {
        const isDark = theme === 'dark';

        return {
            textColor: isDark ? '#e2e8f0' : '#334155',
            mutedTextColor: isDark ? '#94a3b8' : '#64748b',
            gridColor: isDark ? 'rgba(148, 163, 184, 0.18)' : 'rgba(15, 23, 42, 0.08)',
            fillAlpha: isDark ? '26' : '18',
            series: isDark
                ? ['#60a5fa', '#34d399', '#fbbf24', '#f87171', '#22d3ee', '#93c5fd']
                : Object.values(this.colors)
        };
    },

    applyThemeOptions(chart, palette) {
        if (!chart?.options) return;

        if (chart.options.plugins?.legend) {
            chart.options.plugins.legend.labels = {
                ...(chart.options.plugins.legend.labels || {}),
                color: palette.mutedTextColor
            };
        }

        if (chart.options.plugins?.title) {
            chart.options.plugins.title.color = palette.textColor;
        }

        ['x', 'y'].forEach((axis) => {
            if (!chart.options.scales?.[axis]) return;

            chart.options.scales[axis].ticks = {
                ...(chart.options.scales[axis].ticks || {}),
                color: palette.mutedTextColor
            };

            chart.options.scales[axis].grid = {
                ...(chart.options.scales[axis].grid || {}),
                color: chart.options.scales[axis].grid?.display === false ? 'transparent' : palette.gridColor
            };
        });

        chart.data.datasets.forEach((dataset, index) => {
            const color = palette.series[index % palette.series.length];

            if (chart.config.type === 'doughnut') {
                dataset.backgroundColor = palette.series;
                return;
            }

            if (chart.config.type === 'bar') {
                dataset.backgroundColor = color;
                return;
            }

            if (chart.config.type === 'line') {
                dataset.borderColor = color;
                dataset.backgroundColor = `${color}${palette.fillAlpha}`;
            }
        });
    },

    createPieChart(canvasId, data, labels, title) {
        const ctx = document.getElementById(canvasId);
        if (!ctx) return null;

        if (this.charts[canvasId]) {
            this.charts[canvasId].destroy();
        }

        const palette = this.getThemePalette();

        this.charts[canvasId] = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: labels,
                datasets: [{
                    data: data,
                    backgroundColor: palette.series,
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            color: palette.mutedTextColor
                        }
                    },
                    title: {
                        display: !!title,
                        text: title,
                        color: palette.textColor
                    }
                }
            }
        });

        return this.charts[canvasId];
    },

    createBarChart(canvasId, data, labels, title) {
        const ctx = document.getElementById(canvasId);
        if (!ctx) return null;

        if (this.charts[canvasId]) {
            this.charts[canvasId].destroy();
        }

        const palette = this.getThemePalette();

        this.charts[canvasId] = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: title || '',
                    data: data,
                    backgroundColor: palette.series[0],
                    borderRadius: 8
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            color: palette.mutedTextColor
                        },
                        grid: {
                            display: true,
                            color: palette.gridColor
                        }
                    },
                    x: {
                        ticks: {
                            color: palette.mutedTextColor
                        },
                        grid: {
                            display: false
                        }
                    }
                }
            }
        });

        return this.charts[canvasId];
    },

    createLineChart(canvasId, datasets, labels, title) {
        const ctx = document.getElementById(canvasId);
        if (!ctx) return null;

        if (this.charts[canvasId]) {
            this.charts[canvasId].destroy();
        }

        const palette = this.getThemePalette();

        this.charts[canvasId] = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: datasets.map((ds, i) => ({
                    label: ds.label,
                    data: ds.data,
                    borderColor: palette.series[i % palette.series.length],
                    backgroundColor: `${palette.series[i % palette.series.length]}${palette.fillAlpha}`,
                    fill: true,
                    tension: 0.4
                }))
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    title: {
                        display: !!title,
                        text: title,
                        color: palette.textColor
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            color: palette.mutedTextColor
                        },
                        grid: {
                            color: palette.gridColor
                        }
                    },
                    x: {
                        ticks: {
                            color: palette.mutedTextColor
                        },
                        grid: {
                            color: 'transparent'
                        }
                    }
                }
            }
        });

        return this.charts[canvasId];
    },

    updateTheme(theme) {
        // 更新图表颜色主题
        const palette = this.getThemePalette(theme);
        Object.values(this.charts).forEach(chart => {
            if (chart && chart.options) {
                this.applyThemeOptions(chart, palette);
                chart.update();
            }
        });
    }
};

// =============== 仪表盘 ===============
const Dashboard = {
    visible: false,

    init() {
        this.createDashboardButton();
        document.addEventListener('themeChanged', (e) => {
            ChartManager.updateTheme(e.detail.theme);
        });
    },

    createDashboardButton() {
        mountWorkspaceAction('dashboard-toggle', `
            <button type="button" class="workspace-action-btn" id="dashboardBtn" title="数据仪表盘" onclick="Dashboard.toggle()">
                <span class="workspace-action-icon"><i class="bi bi-graph-up fs-6"></i></span>
                <span class="workspace-action-copy">
                    <span class="workspace-action-label">洞察</span>
                    <span class="workspace-action-value">数据仪表盘</span>
                </span>
            </button>
        `);
    },

    toggle() {
        if (this.visible) {
            this.hide();
        } else {
            this.show();
        }
    },

    async show() {
        this.visible = true;

        // 创建仪表盘模态框
        const modalHtml = `
            <div class="modal fade" id="dashboardModal" tabindex="-1">
                <div class="modal-dialog modal-xl modal-dialog-centered modal-dialog-scrollable">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title"><i class="bi bi-graph-up me-2"></i>数据仪表盘</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <div id="dashboardContent">
                                <!-- 统计卡片 -->
                                <div class="row mb-4">
                                    <div class="col-md-3">
                                        <div class="stats-card">
                                            <div class="stats-icon" style="background: linear-gradient(135deg, #2563eb 0%, #0ea5e9 100%); color: white;">
                                                <i class="bi bi-box-seam"></i>
                                            </div>
                                            <div class="stats-value" id="totalProducts">-</div>
                                            <div class="stats-label">商品总数</div>
                                        </div>
                                    </div>
                                    <div class="col-md-3">
                                        <div class="stats-card">
                                            <div class="stats-icon" style="background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: white;">
                                                <i class="bi bi-check-circle"></i>
                                            </div>
                                            <div class="stats-value" id="matchedCount">-</div>
                                            <div class="stats-label">已匹配</div>
                                        </div>
                                    </div>
                                    <div class="col-md-3">
                                        <div class="stats-card">
                                            <div class="stats-icon" style="background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); color: white;">
                                                <i class="bi bi-clock"></i>
                                            </div>
                                            <div class="stats-value" id="pendingCount">-</div>
                                            <div class="stats-label">待确认</div>
                                        </div>
                                    </div>
                                    <div class="col-md-3">
                                        <div class="stats-card">
                                            <div class="stats-icon" style="background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%); color: white;">
                                                <i class="bi bi-x-circle"></i>
                                            </div>
                                            <div class="stats-value" id="unmatchedCount">-</div>
                                            <div class="stats-label">未匹配</div>
                                        </div>
                                    </div>
                                </div>

                                <!-- 图表区域 -->
                                <div class="row">
                                    <div class="col-md-6">
                                        <div class="chart-container">
                                            <h6 class="mb-3">商品分类分布</h6>
                                            <canvas id="categoryChart" height="250"></canvas>
                                        </div>
                                    </div>
                                    <div class="col-md-6">
                                        <div class="chart-container">
                                            <h6 class="mb-3">价格区间分布</h6>
                                            <canvas id="priceChart" height="250"></canvas>
                                        </div>
                                    </div>
                                </div>

                                <!-- 匹配进度 -->
                                <div class="mt-4">
                                    <h6>匹配进度</h6>
                                    <div class="progress-enhanced">
                                        <div class="progress-bar-enhanced" id="matchProgress" style="width: 0%"></div>
                                    </div>
                                    <div class="d-flex justify-content-between mt-2 text-muted small">
                                        <span>0%</span>
                                        <span id="matchProgressText">计算中...</span>
                                        <span>100%</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;

        // 移除旧的模态框
        const oldModal = document.getElementById('dashboardModal');
        if (oldModal) oldModal.remove();

        // 添加新的模态框
        document.body.insertAdjacentHTML('beforeend', modalHtml);

        // 显示模态框
        const modal = new bootstrap.Modal(document.getElementById('dashboardModal'));
        modal.show();

        // 加载数据
        await this.loadData();

        // 监听关闭事件
        document.getElementById('dashboardModal').addEventListener('hidden.bs.modal', () => {
            this.visible = false;
        });
    },

    hide() {
        const modal = document.getElementById('dashboardModal');
        if (modal) {
            bootstrap.Modal.getInstance(modal)?.hide();
        }
    },

    async loadData() {
        try {
            // 获取统计数据
            const response = await fetch('/api/ai/status');
            const data = await response.json();

            // 模拟数据展示
            document.getElementById('totalProducts').textContent = '1,234';

            // 动画数字
            NumberAnimator.animateAll('.stats-value');

            // 创建图表
            this.createCharts();

        } catch (error) {
            console.error('加载仪表盘数据失败:', error);
        }
    },

    createCharts() {
        // 分类饼图
        ChartManager.createPieChart(
            'categoryChart',
            [30, 25, 20, 15, 10],
            ['手部防护', '足部防护', '头部防护', '呼吸防护', '其他'],
            ''
        );

        // 价格柱状图
        ChartManager.createBarChart(
            'priceChart',
            [50, 120, 80, 30, 15],
            ['0-50元', '50-100元', '100-200元', '200-500元', '500元以上'],
            '商品数量'
        );

        // 更新进度条
        setTimeout(() => {
            const progressBar = document.getElementById('matchProgress');
            if (progressBar) {
                ProgressAnimator.animate(progressBar, 75);
            }
            document.getElementById('matchProgressText').textContent = '75% 完成';
        }, 500);
    }
};

// =============== 自定义模态框 ===============
function showCustomModal(title, content, size = 'md') {
    const modalHtml = `
        <div class="modal fade" id="customModal" tabindex="-1">
            <div class="modal-dialog modal-${size} modal-dialog-centered">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">${title}</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">${content}</div>
                </div>
            </div>
        </div>
    `;

    const oldModal = document.getElementById('customModal');
    if (oldModal) oldModal.remove();

    document.body.insertAdjacentHTML('beforeend', modalHtml);

    const modal = new bootstrap.Modal(document.getElementById('customModal'));
    modal.show();

    document.getElementById('customModal').addEventListener('hidden.bs.modal', function() {
        this.remove();
    });
}

// =============== 骨架屏加载 ===============
function showSkeletonLoading(containerId, count = 3) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const skeletonHtml = Array(count).fill(`
        <div class="mb-3">
            <div class="skeleton skeleton-title"></div>
            <div class="skeleton skeleton-text"></div>
            <div class="skeleton skeleton-text" style="width: 80%"></div>
        </div>
    `).join('');

    container.innerHTML = skeletonHtml;
}

// =============== 初始化 ===============
document.addEventListener('DOMContentLoaded', function() {
    // 初始化主题
    ThemeManager.init();

    // 初始化页面快捷动作
    WorkspaceQuickActions.init();

    // 初始化快捷键
    ShortcutManager.init();

    // 初始化拖拽上传
    DragDropManager.init();

    // 初始化仪表盘
    Dashboard.init();

    document.body.classList.add('enhanced-ui-ready');
    console.log('增强功能已加载');
});

// 监听主题变化更新图表
document.addEventListener('themeChanged', (e) => {
    ChartManager.updateTheme(e.detail.theme);
});
