/**
 * 报价单在线分享模块
 * 功能：生成分享链接、复制链接、查看分享状态
 */

const ShareManager = {
    // 当前分享信息
    currentShare: null,

    init() {
        this.bindEvents();
    },

    bindEvents() {
        const shareBtn = document.getElementById('shareBtn');
        if (shareBtn) {
            shareBtn.addEventListener('click', () => this.showShareDialog());
        }
    },

    async showShareDialog() {
        // 检查是否有匹配结果
        if (typeof matchResults === 'undefined' || !matchResults || matchResults.length === 0) {
            showToast('warning', '请先完成商品匹配');
            return;
        }

        // 获取客户名称
        const customerName = document.getElementById('customerName')?.value || '';

        const content = `
            <div class="share-dialog">
                <div class="mb-3">
                    <label class="form-label">客户名称（可选）</label>
                    <input type="text" class="form-control" id="shareCustomerName"
                           value="${customerName}" placeholder="输入客户名称">
                </div>
                <div class="mb-3">
                    <label class="form-label">有效期</label>
                    <select class="form-select" id="shareExpireHours">
                        <option value="1">1小时</option>
                        <option value="6">6小时</option>
                        <option value="24" selected>24小时</option>
                        <option value="72">3天</option>
                        <option value="168">7天</option>
                    </select>
                </div>
                <div class="alert alert-info py-2">
                    <i class="bi bi-info-circle me-1"></i>
                    分享链接可让客户在线查看报价单，无需登录
                </div>
            </div>
        `;

        const footer = `
            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
            <button type="button" class="btn btn-primary" onclick="ShareManager.createShare()">
                <i class="bi bi-link-45deg me-1"></i>生成分享链接
            </button>
        `;

        this.showCustomModal('在线分享报价单', content, footer);
    },

    showCustomModal(title, content, footer, size = 'md') {
        const modalHtml = `
            <div class="modal fade" id="shareModal" tabindex="-1">
                <div class="modal-dialog modal-${size} modal-dialog-centered">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title"><i class="bi bi-share me-2"></i>${title}</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">${content}</div>
                        <div class="modal-footer">${footer}</div>
                    </div>
                </div>
            </div>
        `;

        const oldModal = document.getElementById('shareModal');
        if (oldModal) oldModal.remove();

        document.body.insertAdjacentHTML('beforeend', modalHtml);

        const modal = new bootstrap.Modal(document.getElementById('shareModal'));
        modal.show();
    },

    async createShare() {
        const customerName = document.getElementById('shareCustomerName')?.value || '';
        const expireHours = parseInt(document.getElementById('shareExpireHours')?.value || '24');

        showLoading('正在生成分享链接...');

        try {
            const response = await fetch('/api/share/create', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    customer_name: customerName,
                    expire_hours: expireHours
                })
            });

            const data = await response.json();
            hideLoading();

            if (data.success) {
                this.currentShare = data;
                this.showShareResult(data);
            } else {
                showToast('error', data.message || '生成分享链接失败');
            }
        } catch (error) {
            hideLoading();
            showToast('error', '生成分享链接失败: ' + error.message);
        }
    },

    showShareResult(data) {
        // 关闭之前的模态框
        const oldModal = bootstrap.Modal.getInstance(document.getElementById('shareModal'));
        if (oldModal) oldModal.hide();

        const content = `
            <div class="share-result">
                <div class="mb-3">
                    <label class="form-label">分享链接</label>
                    <div class="input-group">
                        <input type="text" class="form-control" id="shareUrlInput"
                               value="${data.share_url}" readonly>
                        <button class="btn btn-outline-primary" type="button"
                                onclick="ShareManager.copyShareUrl()">
                            <i class="bi bi-clipboard"></i>
                        </button>
                    </div>
                </div>
                <div class="share-preview mb-3">
                    <div class="d-flex align-items-center justify-content-between">
                        <div>
                            <span class="badge bg-info">分享ID: ${data.share_id}</span>
                            <span class="text-muted ms-2">有效期: ${data.expire_hours}小时</span>
                        </div>
                        <a href="${data.share_url}" target="_blank" class="btn btn-sm btn-outline-secondary">
                            <i class="bi bi-eye me-1"></i>预览
                        </a>
                    </div>
                </div>
                <div class="alert alert-success py-2">
                    <i class="bi bi-check-circle me-1"></i>
                    分享链接已生成！点击复制按钮将链接发送给客户
                </div>
            </div>
        `;

        const footer = `
            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">关闭</button>
            <button type="button" class="btn btn-success" onclick="ShareManager.copyAndClose()">
                <i class="bi bi-clipboard-check me-1"></i>复制并关闭
            </button>
        `;

        this.showCustomModal('分享链接已生成', content, footer);
    },

    copyShareUrl() {
        const input = document.getElementById('shareUrlInput');
        if (input) {
            input.select();
            navigator.clipboard.writeText(input.value).then(() => {
                showToast('success', '链接已复制到剪贴板');
            }).catch(() => {
                // 备用方法
                document.execCommand('copy');
                showToast('success', '链接已复制');
            });
        }
    },

    copyAndClose() {
        this.copyShareUrl();
        const modal = bootstrap.Modal.getInstance(document.getElementById('shareModal'));
        if (modal) modal.hide();
    }
};

// 初始化
document.addEventListener('DOMContentLoaded', function() {
    ShareManager.init();
});