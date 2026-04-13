/**
 * 设置管理模块
 * 功能：公司信息设置、品牌定制、导出配置
 */

const SettingsManager = {
    settings: {
        name: '赛正慧采商城',
        address: '',
        phone: '',
        email: '',
        logo_path: ''
    },

    async init() {
        await this.loadSettings();
        this.createSettingsButton();
    },

    async loadSettings() {
        try {
            const response = await fetch('/api/company/settings');
            const data = await response.json();
            if (data.success) {
                this.settings = data.settings;
            }
        } catch (error) {
            console.error('加载设置失败:', error);
        }
    },

    async saveSettings(newSettings) {
        try {
            const response = await fetch('/api/company/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(newSettings)
            });
            const data = await response.json();
            if (data.success) {
                this.settings = newSettings;
                showToast('success', '设置已保存');
                return true;
            }
        } catch (error) {
            showToast('error', '保存设置失败');
        }
        return false;
    },

    createSettingsButton() {
        if (typeof mountWorkspaceAction !== 'function') return;

        mountWorkspaceAction('settings-toggle', `
            <button type="button" class="workspace-action-btn" title="系统设置" onclick="SettingsManager.showSettingsModal()">
                <span class="workspace-action-icon"><i class="bi bi-gear fs-6"></i></span>
                <span class="workspace-action-copy">
                    <span class="workspace-action-label">系统</span>
                    <span class="workspace-action-value">设置中心</span>
                </span>
            </button>
        `);
    },

    showSettingsModal() {
        const content = `
            <div class="settings-form">
                <div class="mb-4">
                    <h6 class="border-bottom pb-2 mb-3"><i class="bi bi-building me-2"></i>公司信息</h6>
                    <div class="mb-3">
                        <label class="form-label">公司名称</label>
                        <input type="text" class="form-control" id="settingCompanyName"
                               value="${this.settings.name || ''}"
                               placeholder="将显示在报价单头部">
                    </div>
                    <div class="mb-3">
                        <label class="form-label">公司地址</label>
                        <input type="text" class="form-control" id="settingCompanyAddress"
                               value="${this.settings.address || ''}"
                               placeholder="公司详细地址">
                    </div>
                    <div class="row">
                        <div class="col-md-6 mb-3">
                            <label class="form-label">联系电话</label>
                            <input type="text" class="form-control" id="settingCompanyPhone"
                                   value="${this.settings.phone || ''}"
                                   placeholder="客服电话">
                        </div>
                        <div class="col-md-6 mb-3">
                            <label class="form-label">电子邮箱</label>
                            <input type="email" class="form-control" id="settingCompanyEmail"
                                   value="${this.settings.email || ''}"
                                   placeholder="联系邮箱">
                        </div>
                    </div>
                </div>

                <div class="mb-4">
                    <h6 class="border-bottom pb-2 mb-3"><i class="bi bi-file-earmark-pdf me-2"></i>PDF导出设置</h6>
                    <div class="mb-3">
                        <label class="form-label">水印文字（可选）</label>
                        <input type="text" class="form-control" id="settingWatermark"
                               placeholder="留空则不添加水印">
                    </div>
                    <div class="form-check mb-3">
                        <input class="form-check-input" type="checkbox" id="settingSignature" checked>
                        <label class="form-check-label" for="settingSignature">
                            在PDF中包含签名区域
                        </label>
                    </div>
                </div>

                <div class="mb-3">
                    <h6 class="border-bottom pb-2 mb-3"><i class="bi bi-palette me-2"></i>界面设置</h6>
                    <div class="d-flex align-items-center gap-3">
                        <span>主题模式：</span>
                        <div class="form-check form-switch">
                            <input class="form-check-input" type="checkbox" id="themeSwitchSetting"
                                   ${document.documentElement.getAttribute('data-theme') === 'dark' ? 'checked' : ''}>
                            <label class="form-check-label" for="themeSwitchSetting">深色模式</label>
                        </div>
                    </div>
                </div>
            </div>
        `;

        const footer = `
            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
            <button type="button" class="btn btn-primary" onclick="SettingsManager.saveAndClose()">
                <i class="bi bi-check-lg me-1"></i>保存设置
            </button>
        `;

        this.showCustomModalWithFooter('系统设置', content, footer, 'lg');
    },

    showCustomModalWithFooter(title, content, footer, size = 'md') {
        const modalHtml = `
            <div class="modal fade" id="settingsModal" tabindex="-1">
                <div class="modal-dialog modal-${size} modal-dialog-centered">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title"><i class="bi bi-gear me-2"></i>${title}</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">${content}</div>
                        <div class="modal-footer">${footer}</div>
                    </div>
                </div>
            </div>
        `;

        const oldModal = document.getElementById('settingsModal');
        if (oldModal) oldModal.remove();

        document.body.insertAdjacentHTML('beforeend', modalHtml);

        const modal = new bootstrap.Modal(document.getElementById('settingsModal'));
        modal.show();

        // 绑定主题切换事件
        const themeSwitch = document.getElementById('themeSwitchSetting');
        if (themeSwitch) {
            themeSwitch.addEventListener('change', (e) => {
                ThemeManager.setTheme(e.target.checked ? 'dark' : 'light');
            });
        }
    },

    async saveAndClose() {
        const newSettings = {
            name: document.getElementById('settingCompanyName')?.value || '',
            address: document.getElementById('settingCompanyAddress')?.value || '',
            phone: document.getElementById('settingCompanyPhone')?.value || '',
            email: document.getElementById('settingCompanyEmail')?.value || ''
        };

        const success = await this.saveSettings(newSettings);

        if (success) {
            const modal = bootstrap.Modal.getInstance(document.getElementById('settingsModal'));
            if (modal) modal.hide();
        }
    }
};

// =============== PDF导出功能 ===============
const PDFExporter = {
    async exportToPDF() {
        // 检查是否有匹配结果
        if (typeof matchResults === 'undefined' || !matchResults || matchResults.length === 0) {
            showToast('warning', '请先完成商品匹配');
            return;
        }

        // 获取客户名称
        const customerName = document.getElementById('customerName')?.value ||
                            prompt('请输入客户名称：') || '';

        // 显示导出选项
        this.showExportOptions(customerName);
    },

    showExportOptions(customerName) {
        const content = `
            <div class="export-options">
                <div class="mb-3">
                    <label class="form-label">客户名称</label>
                    <input type="text" class="form-control" id="pdfCustomerName"
                           value="${customerName}" placeholder="可选">
                </div>
                <div class="mb-3">
                    <label class="form-label">水印文字</label>
                    <input type="text" class="form-control" id="pdfWatermark"
                           placeholder="留空则不添加水印">
                </div>
                <div class="form-check mb-3">
                    <input class="form-check-input" type="checkbox" id="pdfSignature" checked>
                    <label class="form-check-label" for="pdfSignature">
                        包含签名区域
                    </label>
                </div>
                <hr class="my-3">
                <div class="d-grid gap-2">
                    <button class="btn btn-outline-info" onclick="ContractManager.showContractDialog()">
                        <i class="bi bi-file-earmark-contract me-1"></i>生成采购合同
                    </button>
                </div>
            </div>
        `;

        const footer = `
            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
            <button type="button" class="btn btn-primary" onclick="PDFExporter.doExport()">
                <i class="bi bi-file-earmark-pdf me-1"></i>生成PDF报价单
            </button>
        `;

        this.showCustomModalWithFooter('导出报价单', content, footer);
    },

    showCustomModalWithFooter(title, content, footer, size = 'md') {
        const modalHtml = `
            <div class="modal fade" id="pdfExportModal" tabindex="-1">
                <div class="modal-dialog modal-${size} modal-dialog-centered">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title"><i class="bi bi-file-earmark-pdf me-2"></i>${title}</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">${content}</div>
                        <div class="modal-footer">${footer}</div>
                    </div>
                </div>
            </div>
        `;

        const oldModal = document.getElementById('pdfExportModal');
        if (oldModal) oldModal.remove();

        document.body.insertAdjacentHTML('beforeend', modalHtml);

        const modal = new bootstrap.Modal(document.getElementById('pdfExportModal'));
        modal.show();
    },

    async doExport() {
        showLoading('正在生成PDF...');

        try {
            const response = await fetch('/api/pdf/export', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    customer_name: document.getElementById('pdfCustomerName')?.value || '',
                    watermark: document.getElementById('pdfWatermark')?.value || '',
                    include_signature: document.getElementById('pdfSignature')?.checked ?? true
                })
            });

            const data = await response.json();
            hideLoading();

            if (data.success) {
                // 关闭模态框
                const modal = bootstrap.Modal.getInstance(document.getElementById('pdfExportModal'));
                if (modal) modal.hide();

                // 触发下载
                const downloadUrl = data.download_url;
                if (downloadUrl) {
                    const link = document.createElement('a');
                    link.href = downloadUrl;
                    link.download = data.filename;
                    link.click();
                }

                showToast('success', 'PDF已生成并开始下载');
            } else {
                showToast('error', data.message || 'PDF导出失败');
            }
        } catch (error) {
            hideLoading();
            showToast('error', 'PDF导出失败: ' + error.message);
        }
    }
};

// 初始化设置管理
SettingsManager.createSettingsButton = function() {
    if (typeof mountWorkspaceAction !== 'function') return;

    mountWorkspaceAction('settings-toggle', `
        <button type="button" class="workspace-action-btn" title="系统设置" aria-label="系统设置" onclick="SettingsManager.showSettingsModal()">
            <span class="workspace-action-icon"><i class="bi bi-gear fs-6"></i></span>
            <span class="workspace-action-copy">
                <span class="workspace-action-label">系统</span>
                <span class="workspace-action-value">设置</span>
            </span>
        </button>
    `);
};

document.addEventListener('DOMContentLoaded', function() {
    SettingsManager.init();
});
