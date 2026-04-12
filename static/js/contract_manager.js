/**
 * 合同自动生成模块
 * 功能：根据报价单生成采购合同PDF
 */

const ContractManager = {
    init() {
        this.bindEvents();
    },

    bindEvents() {
        // 可以添加合同按钮的事件绑定
        // 暂时集成到导出选项中
    },

    async showContractDialog() {
        // 检查是否有匹配结果
        if (typeof matchResults === 'undefined' || !matchResults || matchResults.length === 0) {
            showToast('warning', '请先完成商品匹配');
            return;
        }

        // 检查是否有选中的商品
        const hasSelected = matchResults.some(r => r.confirmed && r.action === 'select');
        if (!hasSelected) {
            showToast('warning', '请先选择要采购的商品');
            return;
        }

        // 获取客户名称
        const customerName = document.getElementById('customerName')?.value || '';

        const content = `
            <div class="contract-dialog">
                <div class="mb-4">
                    <h6 class="border-bottom pb-2 mb-3"><i class="bi bi-building me-2"></i>客户信息</h6>
                    <div class="mb-3">
                        <label class="form-label">客户名称 *</label>
                        <input type="text" class="form-control" id="contractCustomerName"
                               value="${customerName}" placeholder="客户公司名称" required>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">联系人</label>
                        <input type="text" class="form-control" id="contractContact"
                               placeholder="联系人姓名">
                    </div>
                    <div class="mb-3">
                        <label class="form-label">联系地址</label>
                        <input type="text" class="form-control" id="contractAddress"
                               placeholder="客户地址">
                    </div>
                </div>

                <div class="mb-3">
                    <h6 class="border-bottom pb-2 mb-3"><i class="bi bi-file-earmark-text me-2"></i>合同预览</h6>
                    <div class="contract-preview qe-surface-muted">
                        <div class="row">
                            <div class="col-6">
                                <small class="text-muted">采购商品数量:</small>
                                <span class="fw-bold">${matchResults.filter(r => r.confirmed && r.action === 'select').length}</span>
                            </div>
                            <div class="col-6">
                                <small class="text-muted">预估总金额:</small>
                                <span class="fw-bold text-primary" id="contractTotalAmount">
                                    ${this.calculateTotal()}
                                </span>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="alert alert-info py-2">
                    <i class="bi bi-info-circle me-1"></i>
                    合同将自动生成PDF格式，包含商品明细、金额汇总和签章区域
                </div>
            </div>
        `;

        const footer = `
            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
            <button type="button" class="btn btn-primary" onclick="ContractManager.generateContract()">
                <i class="bi bi-file-earmark-pdf me-1"></i>生成合同
            </button>
        `;

        this.showCustomModal('生成采购合同', content, footer, 'lg');
    },

    calculateTotal() {
        let total = 0;
        for (const result of matchResults) {
            if (result.confirmed && result.action === 'select' && result.selected_product) {
                const product = result.selected_product.product || {};
                const quantity = result.query_item?.quantity || 1;
                const price = product.market_price || 0;
                total += quantity * price;
            }
        }
        return '¥' + total.toFixed(2);
    },

    showCustomModal(title, content, footer, size = 'md') {
        const modalHtml = `
            <div class="modal fade" id="contractModal" tabindex="-1">
                <div class="modal-dialog modal-${size} modal-dialog-centered">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title"><i class="bi bi-file-earmark-contract me-2"></i>${title}</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">${content}</div>
                        <div class="modal-footer">${footer}</div>
                    </div>
                </div>
            </div>
        `;

        const oldModal = document.getElementById('contractModal');
        if (oldModal) oldModal.remove();

        document.body.insertAdjacentHTML('beforeend', modalHtml);

        const modal = new bootstrap.Modal(document.getElementById('contractModal'));
        modal.show();
    },

    async generateContract() {
        const customerName = document.getElementById('contractCustomerName')?.value;
        if (!customerName) {
            showToast('warning', '请输入客户名称');
            return;
        }

        const customerContact = document.getElementById('contractContact')?.value || '';
        const customerAddress = document.getElementById('contractAddress')?.value || '';

        showLoading('正在生成采购合同...');

        try {
            const response = await fetch('/api/contract/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    customer_name: customerName,
                    customer_contact: customerContact,
                    customer_address: customerAddress
                })
            });

            const data = await response.json();
            hideLoading();

            if (data.success) {
                // 关闭模态框
                const modal = bootstrap.Modal.getInstance(document.getElementById('contractModal'));
                if (modal) modal.hide();

                // 触发下载
                if (data.download_url) {
                    const link = document.createElement('a');
                    link.href = data.download_url;
                    link.download = data.filename;
                    link.click();
                }

                showToast('success', `合同已生成！编号: ${data.contract_no}`);
            } else {
                showToast('error', data.message || '合同生成失败');
            }
        } catch (error) {
            hideLoading();
            showToast('error', '合同生成失败: ' + error.message);
        }
    }
};

// 初始化
document.addEventListener('DOMContentLoaded', function() {
    ContractManager.init();
});
