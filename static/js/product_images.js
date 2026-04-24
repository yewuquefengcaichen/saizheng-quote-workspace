/**
 * 商品图片展示模块
 * 功能：在匹配结果中展示商品图片，支持图片预览放大
 */

const ProductImageManager = {
    // 图片服务器基础URL
    baseUrl: 'https://sz.dinghuovip.com',

    // 本地图片代理前缀
    proxyBase: '/api/product/image-proxy',

    // 当前预览图片
    currentPreview: null,

    // 图片解析缓存
    imageCache: new Map(),

    init() {
        this.createImageViewer();
    },

    getProxyUrl(product, index = 0) {
        if (!product) return '';

        const productCode = String(product.code || '').trim();
        if (productCode) {
            return index > 0
                ? `${this.proxyBase}/${encodeURIComponent(productCode)}?index=${index}`
                : `${this.proxyBase}/${encodeURIComponent(productCode)}`;
        }

        const productId = String(product.product_id || '').trim();
        if (productId) {
            return index > 0
                ? `${this.proxyBase}/by-id/${encodeURIComponent(productId)}?index=${index}`
                : `${this.proxyBase}/by-id/${encodeURIComponent(productId)}`;
        }

        return '';
    },

    /**
     * 获取商品图片URL
     * @param {Object} product - 商品对象
     * @returns {string} 图片URL
     */
    getImageUrl(product) {
        if (!product) return '';

        if (product.image_url) {
            const imageUrl = this.normalizeUrl(product.image_url);
            if (imageUrl) return imageUrl;
        }

        if (product.source_image_url) {
            return this.normalizeUrl(product.source_image_url);
        }

        const images = this.getImages(product);
        if (images.length > 0) {
            return images[0].url || images[0].proxy_url || images[0].source_url || '';
        }

        const proxyUrl = this.getProxyUrl(product);
        if (proxyUrl) {
            return proxyUrl;
        }

        return '';
    },

    getDisplayUrl(image) {
        if (!image) return '';
        return image.proxy_url || this.normalizeUrl(image.source_url || image.url || '') || '';
    },

    getViewerUrl(image) {
        if (!image) return '';
        return image.proxy_url || this.normalizeUrl(image.source_url || image.url || '') || '';
    },

    getSourceUrl(image) {
        if (!image) return '';
        const proxyUrl = String(image.proxy_url || '').trim();
        const sourceUrl = this.normalizeUrl(image.source_url || '');
        const directUrl = this.normalizeUrl(image.url || '');
        if (sourceUrl && sourceUrl !== proxyUrl) return sourceUrl;
        if (directUrl && directUrl !== proxyUrl) return directUrl;
        return '';
    },

    getCacheKey(product) {
        if (!product) return '';
        return [
            String(product.code || '').trim(),
            String(product.product_id || '').trim(),
            String(product.image_url || '').trim(),
            String(product.source_image_url || '').trim(),
            String(product.intro || '').trim().slice(0, 200)
        ].join('||');
    },

    getImages(product) {
        if (!product) return [];

        const cacheKey = this.getCacheKey(product);
        if (cacheKey && this.imageCache.has(cacheKey)) {
            return this.imageCache.get(cacheKey);
        }

        let images = [];

        if (product.images && product.images.length > 0) {
            images = product.images.map((img, index) => {
                const sourceUrl = this.normalizeUrl(img.source_url || img.url);
                const explicitProxyUrl = this.normalizeUrl(img.proxy_url || img.thumb || '');
                const legacyProxyUrl = this.getProxyUrl(product, index) || '';
                const proxyUrl = explicitProxyUrl || (!sourceUrl ? legacyProxyUrl : '');
                return {
                    ...img,
                    url: proxyUrl || sourceUrl,
                    source_url: sourceUrl,
                    proxy_url: proxyUrl
                };
            });
            const productImageUrl = this.normalizeUrl(product.image_url || '');
            if (productImageUrl && productImageUrl.startsWith('/api/') && !images.some(img => (img.url || img.proxy_url) === productImageUrl)) {
                images.unshift({
                    url: productImageUrl,
                    title: product.name || '',
                    source_url: this.normalizeUrl(product.source_image_url || ''),
                    proxy_url: productImageUrl
                });
            }
        } else if (product.image_url || product.source_image_url) {
            const explicitImageUrl = this.normalizeUrl(product.image_url || '');
            const sourceUrl = this.normalizeUrl(product.source_image_url || product.image_url || '');
            images = [{
                url: explicitImageUrl || sourceUrl,
                title: product.name || '',
                source_url: sourceUrl,
                proxy_url: explicitImageUrl && explicitImageUrl.startsWith('/api/') ? explicitImageUrl : ''
            }];
        } else if (product.intro) {
            images = this.extractImagesFromIntro(product.intro, product);
        } else {
            const proxyUrl = this.getProxyUrl(product);
            if (proxyUrl) {
                images = [{
                    url: proxyUrl,
                    title: product.name || '',
                    source_url: product.source_image_url || '',
                    proxy_url: proxyUrl
                }];
            }
        }

        if (cacheKey) {
            this.imageCache.set(cacheKey, images);
        }

        return images;
    },

    buildFallbackImages(product, extractedImages) {
        const proxyUrl = this.getProxyUrl(product);
        if (!proxyUrl) {
            return extractedImages;
        }

        return extractedImages.map((img, index) => ({
            ...img,
            source_url: this.normalizeUrl(img.source_url || img.url),
            proxy_url: '',
            url: this.normalizeUrl(img.url) || this.getProxyUrl(product, index)
        }));
    },

    /**
     * 从intro字段提取图片
     * @param {string} intro - HTML内容
     * @returns {Array} 图片数组
     */
    extractImagesFromIntro(intro, product = null) {
        if (!intro) return [];

        const decodedIntro = this.decodeHtmlEntities(intro);
        const extractedImages = [];
        const imgRegex = /<img[^>]+src=["']([^"']+)["'][^>]*(?:title=["']([^"']*)["'])?/gi;
        let match;

        while ((match = imgRegex.exec(decodedIntro)) !== null) {
            const url = this.normalizeUrl(match[1]);
            const title = this.decodeHtmlEntities(match[2] || '');

            if (!this.shouldExcludeImage(title)) {
                extractedImages.push({
                    url,
                    title,
                    source_url: url
                });
            }
        }

        return this.buildFallbackImages(product, extractedImages);
    },

    decodeHtmlEntities(text) {
        if (!text || typeof text !== 'string') return '';

        const textarea = document.createElement('textarea');
        textarea.innerHTML = text;
        return textarea.value;
    },

    /**
     * 标准化URL
     * @param {string} url - 图片URL
     * @returns {string} 完整URL
     */
    normalizeUrl(url) {
        if (!url) return '';

        if (url.startsWith('http://') || url.startsWith('https://') || url.startsWith('/api/')) {
            return url;
        }

        let cleanUrl = url;
        if (cleanUrl.startsWith('../')) {
            cleanUrl = cleanUrl.substring(3);
        } else if (cleanUrl.startsWith('./')) {
            cleanUrl = cleanUrl.substring(2);
        }

        return `${this.baseUrl}/${cleanUrl.replace(/^\/+/, '')}`;
    },

    /**
     * 判断是否应排除图片
     * @param {string} title - 图片标题
     * @returns {boolean}
     */
    shouldExcludeImage(title) {
        const excludeKeywords = ['温馨提示', '固定格式', '固定模板', '提示', '说明'];
        return excludeKeywords.some(kw => title.includes(kw));
    },

    placeholderDataUrl() {
        return 'data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 60 60%22><rect fill=%22%23f1f5f9%22 width=%2260%22 height=%2260%22/><text x=%2230%22 y=%2235%22 text-anchor=%22middle%22 fill=%22%2394a3b8%22 font-size=%2212%22>暂无图片</text></svg>';
    },

    escapeHtmlAttr(value) {
        return String(value || '')
            .replace(/&/g, '&amp;')
            .replace(/"/g, '&quot;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
    },

    buildViewerPayload(images) {
        return encodeURIComponent(JSON.stringify(images));
    },

    /**
     * 创建图片查看器
     */
    createImageViewer() {
        if (document.getElementById('imageViewerOverlay')) return;

        const viewerHtml = `
            <div id="imageViewerOverlay" class="image-viewer-overlay" style="display: none;">
                <div class="image-viewer-backdrop" onclick="ProductImageManager.closeViewer()"></div>
                <div class="image-viewer-container">
                    <button class="image-viewer-close" onclick="ProductImageManager.closeViewer()">
                        <i class="bi bi-x-lg"></i>
                    </button>
                    <button class="image-viewer-prev" onclick="ProductImageManager.prevImage()">
                        <i class="bi bi-chevron-left"></i>
                    </button>
                    <img id="viewerImage" class="image-viewer-img" src="" alt="">
                    <button class="image-viewer-next" onclick="ProductImageManager.nextImage()">
                        <i class="bi bi-chevron-right"></i>
                    </button>
                    <div class="image-viewer-info">
                        <span id="viewerTitle"></span>
                        <span id="viewerCounter"></span>
                    </div>
                </div>
            </div>
        `;

        document.body.insertAdjacentHTML('beforeend', viewerHtml);
        this.addViewerStyles();
    },

    /**
     * 添加查看器样式
     */
    addViewerStyles() {
        if (document.getElementById('imageViewerStyles')) return;

        const styles = `
            .image-viewer-overlay {
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                z-index: 10000;
                display: flex;
                align-items: center;
                justify-content: center;
            }

            .image-viewer-backdrop {
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: rgba(0, 0, 0, 0.9);
            }

            .image-viewer-container {
                position: relative;
                max-width: 90vw;
                max-height: 90vh;
            }

            .image-viewer-img {
                max-width: 90vw;
                max-height: 85vh;
                object-fit: contain;
                border-radius: 8px;
            }

            .image-viewer-close {
                position: absolute;
                top: -40px;
                right: 0;
                background: rgba(255, 255, 255, 0.1);
                border: none;
                color: white;
                width: 40px;
                height: 40px;
                border-radius: 50%;
                cursor: pointer;
                font-size: 20px;
                transition: background 0.2s;
            }

            .image-viewer-close:hover {
                background: rgba(255, 255, 255, 0.2);
            }

            .image-viewer-prev,
            .image-viewer-next {
                position: absolute;
                top: 50%;
                transform: translateY(-50%);
                background: rgba(255, 255, 255, 0.1);
                border: none;
                color: white;
                width: 50px;
                height: 50px;
                border-radius: 50%;
                cursor: pointer;
                font-size: 24px;
                transition: background 0.2s;
            }

            .image-viewer-prev:hover,
            .image-viewer-next:hover {
                background: rgba(255, 255, 255, 0.2);
            }

            .image-viewer-prev { left: -60px; }
            .image-viewer-next { right: -60px; }

            .image-viewer-info {
                position: absolute;
                bottom: -30px;
                left: 0;
                right: 0;
                text-align: center;
                color: rgba(255, 255, 255, 0.7);
                font-size: 14px;
            }

            .product-image-slot {
                display: flex;
                flex-direction: column;
                align-items: flex-start;
            }

            .product-image-thumb {
                width: 60px;
                height: 60px;
                object-fit: contain;
                border-radius: 8px;
                cursor: pointer;
                transition: transform 0.2s;
                border: 2px solid #e2e8f0;
                background: linear-gradient(135deg, #ffffff 0%, #f8fafc 52%, #eef2ff 100%);
                padding: 2px;
            }

            .product-image-thumb:hover {
                transform: scale(1.1);
                border-color: #6366f1;
            }

            .product-image-placeholder {
                width: 60px;
                height: 60px;
                background: linear-gradient(135deg, #f1f5f9 0%, #e2e8f0 100%);
                border-radius: 8px;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                gap: 4px;
                color: #94a3b8;
                font-size: 24px;
                text-align: center;
                padding: 6px;
                line-height: 1.1;
            }

            .product-image-placeholder span {
                font-size: 11px;
            }

            .product-images-row {
                display: flex;
                gap: 8px;
                margin-top: 8px;
            }

            @media (max-width: 768px) {
                .image-viewer-prev { left: 10px; }
                .image-viewer-next { right: 10px; }
            }
        `;

        const styleEl = document.createElement('style');
        styleEl.id = 'imageViewerStyles';
        styleEl.textContent = styles;
        document.head.appendChild(styleEl);
    },

    /**
     * 打开图片查看器
     * @param {Array} images - 图片数组
     * @param {number} startIndex - 起始索引
     */
    openViewer(images, startIndex = 0) {
        if (!images || images.length === 0) return;

        this.currentPreview = {
            images,
            index: startIndex
        };

        this.showCurrentImage();
        document.getElementById('imageViewerOverlay').style.display = 'flex';
        document.addEventListener('keydown', this.handleKeyDown);
    },

    /**
     * 关闭图片查看器
     */
    closeViewer() {
        const overlay = document.getElementById('imageViewerOverlay');
        if (overlay) {
            overlay.style.display = 'none';
        }
        document.removeEventListener('keydown', this.handleKeyDown);
        this.currentPreview = null;
    },

    /**
     * 显示当前图片
     */
    showCurrentImage() {
        if (!this.currentPreview) return;

        const { images, index } = this.currentPreview;
        const image = images[index];
        if (!image) return;

        const viewerImage = document.getElementById('viewerImage');
        if (!viewerImage) return;

        viewerImage.onerror = () => {
            viewerImage.onerror = null;
            viewerImage.src = this.placeholderDataUrl();
        };
        viewerImage.src = image.proxy_url || image.url || image.source_url || this.placeholderDataUrl();
        viewerImage.alt = image.title || '';
        document.getElementById('viewerTitle').textContent = image.title || '';
        document.getElementById('viewerCounter').textContent = `${index + 1} / ${images.length}`;
    },

    /**
     * 上一张图片
     */
    prevImage() {
        if (!this.currentPreview) return;
        const { images, index } = this.currentPreview;
        this.currentPreview.index = (index - 1 + images.length) % images.length;
        this.showCurrentImage();
    },

    /**
     * 下一张图片
     */
    nextImage() {
        if (!this.currentPreview) return;
        const { images, index } = this.currentPreview;
        this.currentPreview.index = (index + 1) % images.length;
        this.showCurrentImage();
    },

    /**
     * 键盘事件处理
     */
    handleKeyDown(e) {
        if (!ProductImageManager.currentPreview) return;

        switch (e.key) {
            case 'ArrowLeft':
                ProductImageManager.prevImage();
                break;
            case 'ArrowRight':
                ProductImageManager.nextImage();
                break;
            case 'Escape':
                ProductImageManager.closeViewer();
                break;
        }
    },

    /**
     * 创建商品图片HTML
     * @param {Object} product - 商品对象
     * @param {string} size - 图片尺寸 'small' | 'medium' | 'large'
     * @returns {string} HTML字符串
     */
    createImageHtml(product, size = 'small') {
        const images = this.getImages(product);
        const imageHint = product && product.image_assisted ? '<div class="small text-info mt-1"><i class="bi bi-images me-1"></i>图片辅助</div>' : '';

        if (images.length === 0) {
            return `<div><div class="product-image-placeholder"><i class="bi bi-image"></i><span>暂无图片</span></div>${imageHint}</div>`;
        }

        const firstImage = images[0];
        const sizeStyle = size === 'large' ? 'width: 120px; height: 120px;' :
                          size === 'medium' ? 'width: 80px; height: 80px;' :
                          'width: 60px; height: 60px;';
        const displayUrl = this.getDisplayUrl(firstImage) || this.getViewerUrl(firstImage) || this.placeholderDataUrl();
        const fallbackUrl = this.getSourceUrl(firstImage);
        const payload = this.buildViewerPayload(images);
        const loading = size === 'large' ? 'eager' : 'lazy';
        const decoding = 'async';
        const errorPlaceholderHtml = this.escapeHtmlAttr(`<div class="product-image-placeholder"><i class="bi bi-image"></i><span>图片加载失败</span></div>${imageHint}`);

        return `
            <div class="product-image-slot">
                <img class="product-image-thumb"
                     src="${this.escapeHtmlAttr(displayUrl)}"
                     alt="${this.escapeHtmlAttr(firstImage.title || product.name || '')}"
                     style="${sizeStyle}"
                     loading="${loading}"
                     decoding="${decoding}"
                     fetchpriority="${size === 'large' ? 'high' : 'auto'}"
                     data-fallback-src="${this.escapeHtmlAttr(fallbackUrl || '')}"
                     onclick="ProductImageManager.openViewer(JSON.parse(decodeURIComponent('${payload}')))"
                     onerror="ProductImageManager.handleImageError(this, '${errorPlaceholderHtml}')">
                ${imageHint}
            </div>
        `;
    },

    handleImageError(imgEl, errorPlaceholderHtml) {
        if (!imgEl) return;

        const fallbackSrc = imgEl.dataset ? imgEl.dataset.fallbackSrc : '';
        const currentAbs = imgEl.src ? new URL(imgEl.src, window.location.href).href : '';
        const fallbackAbs = fallbackSrc ? new URL(fallbackSrc, window.location.href).href : '';
        if (fallbackSrc && fallbackAbs && currentAbs !== fallbackAbs) {
            imgEl.onerror = () => this.handleImageError(imgEl, errorPlaceholderHtml);
            imgEl.src = fallbackSrc;
            return;
        }

        imgEl.onerror = null;
        const wrapper = imgEl.closest('.product-image-slot') || imgEl.parentElement;
        if (wrapper) {
            wrapper.innerHTML = errorPlaceholderHtml;
        }
    },

    /**
     * 创建多图展示HTML
     * @param {Object} product - 商品对象
     * @param {number} maxImages - 最大显示数量
     * @returns {string} HTML字符串
     */
    createMultiImageHtml(product, maxImages = 3) {
        const images = this.getImages(product).slice(0, maxImages);

        if (images.length === 0) {
            return `<div class="product-image-placeholder"><i class="bi bi-image"></i></div>`;
        }

        const payload = this.buildViewerPayload(images);
        const html = images.map((img, index) => {
            const displayUrl = this.getDisplayUrl(img) || this.getViewerUrl(img) || this.placeholderDataUrl();
            const fallbackUrl = this.getViewerUrl(img) || '';
            return `
            <img class="product-image-thumb"
                 src="${this.escapeHtmlAttr(displayUrl)}"
                 alt="${this.escapeHtmlAttr(img.title || '')}"
                 loading="lazy"
                 decoding="async"
                 data-fallback-src="${this.escapeHtmlAttr(fallbackUrl)}"
                 onclick="ProductImageManager.openViewer(JSON.parse(decodeURIComponent('${payload}')), ${index})"
                 onerror="ProductImageManager.handleImageError(this, '<div class=&quot;product-image-placeholder&quot;><i class=&quot;bi bi-image&quot;></i><span>图片加载失败</span></div>')">
        `;
        }).join('');

        return `<div class="product-images-row">${html}</div>`;
    }
};

window.ProductImageManager = ProductImageManager;

// 初始化
document.addEventListener('DOMContentLoaded', function() {
    ProductImageManager.init();
});
