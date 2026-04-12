/**
 * OCR图片识别模块
 * 功能：上传报价单图片，自动识别商品名称和价格
 */

const OCRManager = {
    // OCR服务状态
    available: false,

    async init() {
        await this.checkStatus();
        this.bindEvents();
    },

    async checkStatus() {
        try {
            const response = await fetch('/api/ocr/status');
            const data = await response.json();
            this.available = data.available;

            if (!this.available) {
                console.warn('OCR服务不可用，请安装easyocr');
            }
        } catch (error) {
            console.error('检查OCR状态失败:', error);
            this.available = false;
        }
    },

    bindEvents() {
        // OCR上传按钮
        const ocrBtn = document.getElementById('ocrUploadBtn');
        const ocrFile = document.getElementById('ocrFile');

        if (ocrBtn && ocrFile) {
            ocrBtn.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                console.log('OCR button clicked, available =', this.available);
                if (!this.available) {
                    showToast('warning', 'OCR服务不可用，请先安装easyocr: pip install easyocr');
                    return;
                }
                ocrFile.value = '';
                ocrFile.click();
            });

            ocrFile.addEventListener('change', (e) => {
                const file = e.target.files && e.target.files[0];
                console.log('OCR file changed:', file ? file.name : 'no file');
                if (file) {
                    showToast('success', '已选择图片：' + file.name);
                    this.processImage(file);
                }
            });
        } else {
            console.error('OCR elements not found', { ocrBtn, ocrFile });
        }
    },

    async processImage(file) {
        console.log('Starting OCR for file:', file);
        showLoading('正在识别图片中的文字...');

        try {
            const formData = new FormData();
            formData.append('file', file);

            const response = await fetch('/api/ocr/recognize', {
                method: 'POST',
                body: formData
            });

            const data = await response.json();
            hideLoading();

            if (data.success) {
                this.showResults(data);
            } else {
                showToast('error', data.message || 'OCR识别失败');
            }
        } catch (error) {
            hideLoading();
            showToast('error', 'OCR识别失败: ' + error.message);
        }
    },

    showResults(data) {
        this.lastResults = data;

        if (!data.parsed_items || data.parsed_items.length === 0 || !data.parse_result) {
            this.showRawTextModal(data);
            return;
        }

        if (typeof showColumnMappingModal !== 'function') {
            showToast('error', '校对界面尚未准备好，请刷新页面后重试');
            return;
        }

        const lowConfidenceRows = Array.isArray(data.parse_result?.low_confidence_rows)
            ? data.parse_result.low_confidence_rows.length
            : 0;
        const hintText = lowConfidenceRows > 0
            ? `OCR识别完成，共解析 ${data.parsed_items.length} 个报价项，其中 ${lowConfidenceRows} 行建议重点校对`
            : `OCR识别完成，共解析 ${data.parsed_items.length} 个报价项，请先校对`;

        showToast('success', hintText);
        showColumnMappingModal(data.parse_result);
    },

    showRawTextModal(data) {
        const rawTextHtml = (data.raw_text || []).map(item =>
            `<div class="ocr-line">
                <span class="ocr-text">${item.text}</span>
                <span class="ocr-confidence badge bg-${item.confidence > 0.7 ? 'success' : item.confidence > 0.5 ? 'warning' : 'secondary'}">
                    ${(item.confidence * 100).toFixed(0)}%
                </span>
            </div>`
        ).join('');

        const content = `
            <div class="ocr-results">
                <div class="mb-4">
                    <h6><i class="bi bi-eye me-2"></i>识别到的文字内容</h6>
                    <div class="ocr-text-container" style="max-height: 260px; overflow-y: auto;">
                        ${rawTextHtml || '<div class="text-muted">未识别到有效文字</div>'}
                    </div>
                </div>

                <div class="alert alert-warning mb-0">
                    <i class="bi bi-exclamation-triangle me-2"></i>
                    未能自动解析出有效报价项，请更换更清晰的图片后重试。
                </div>
            </div>
        `;

        const footer = `
            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">关闭</button>
        `;

        this.showCustomModal('OCR识别结果', content, footer, 'lg');
    },

    createQuoteFromOCR() {
        showToast('warning', 'OCR识别结果现在会直接进入校对界面，请在校对弹窗中确认后继续');
    },

    showCustomModal(title, content, footer, size = 'md') {
        const modalHtml = `
            <div class="modal fade" id="ocrResultModal" tabindex="-1">
                <div class="modal-dialog modal-${size} modal-dialog-centered">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title"><i class="bi bi-camera me-2"></i>${title}</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">${content}</div>
                        <div class="modal-footer">${footer}</div>
                    </div>
                </div>
            </div>
        `;

        const oldModal = document.getElementById('ocrResultModal');
        if (oldModal) oldModal.remove();

        document.body.insertAdjacentHTML('beforeend', modalHtml);

        const modal = new bootstrap.Modal(document.getElementById('ocrResultModal'));
        modal.show();
    }
};

// 初始化OCR模块
document.addEventListener('DOMContentLoaded', function() {
    OCRManager.init();
});