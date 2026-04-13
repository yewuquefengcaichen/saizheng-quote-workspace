let aiEnabled = false;
let aiAvailable = false;
let aiProvider = 'none';
let chatHistory = [];
let currentEditItemIndex = 0;

const AI_PANEL_STORAGE_KEY = 'workspace-ai-panel-open';
const AI_HISTORY_LIMIT = 24;
const AI_PROVIDER_LABELS = {
    claude: 'Claude AI',
    openai: 'GPT AI',
    local: '本地 AI'
};

AI_PROVIDER_LABELS.local = '本地助手';

function getMatchResultsList() {
    return typeof matchResults !== 'undefined' && Array.isArray(matchResults) ? matchResults : [];
}

function getActiveAssistantIndex() {
    const results = getMatchResultsList();
    if (!results.length) {
        return 0;
    }

    const preferredIndex = typeof activeWorkbenchIndex !== 'undefined' && Number.isFinite(activeWorkbenchIndex)
        ? Number(activeWorkbenchIndex)
        : 0;
    if (results[preferredIndex]) {
        return preferredIndex;
    }

    return 0;
}

function getActiveAssistantEntry() {
    const results = getMatchResultsList();
    if (!results.length) {
        return { index: 0, result: null };
    }

    const index = getActiveAssistantIndex();
    currentEditItemIndex = index;
    return { index, result: results[index] || null };
}

function getProviderLabel(provider) {
    return AI_PROVIDER_LABELS[provider] || '报价助手';
}

function getAIModeLabel() {
    if (!aiEnabled) {
        return '助手未启用';
    }
    if (aiAvailable) {
        return '在线辅助';
    }
    return '当前页辅助';
}

function getAIModeDisplayName() {
    if (!aiEnabled) {
        return '助手未启用';
    }
    if (aiAvailable) {
        return getProviderLabel(aiProvider);
    }
    return '本地助手';
}

function escapeHtml(content) {
    return String(content ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function formatAIResponse(content) {
    return escapeHtml(content)
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/\n/g, '<br>');
}

function toNumber(value) {
    if (value === null || typeof value === 'undefined' || value === '') {
        return 0;
    }

    const numeric = Number(String(value).replace(/[^\d.-]/g, ''));
    return Number.isFinite(numeric) ? numeric : 0;
}

function formatAssistantPrice(value) {
    const numeric = toNumber(value);
    return numeric > 0 ? `¥${numeric.toFixed(2)}` : '待补充';
}

function getResultPrimaryCandidate(result) {
    if (!result) {
        return null;
    }

    if (result.selected_product) {
        return result.selected_product;
    }

    if (Array.isArray(result.matches) && result.matches.length) {
        return result.matches[0];
    }

    if (Array.isArray(result.alternatives) && result.alternatives.length) {
        return result.alternatives[0];
    }

    return null;
}

function getCandidateProduct(candidate) {
    return candidate?.product || {};
}

function getCandidateDisplayName(candidate) {
    const product = getCandidateProduct(candidate);
    return product.name || candidate?.name || '暂无稳定候选';
}

function getCandidateDisplayCode(candidate) {
    const product = getCandidateProduct(candidate);
    return [
        product.code,
        product.product_code,
        product.item_code,
        product.sku
    ].map(value => String(value || '').trim()).find(Boolean) || '未选择';
}

function getCandidateScoreText(candidate) {
    const score = Number(candidate?.score || 0);
    return score > 0 ? `${Math.round(score * 100)}%` : '无推荐度';
}

function getResultStatusText(result) {
    if (!result) {
        return '暂无报价项';
    }

    if (result.confirmed && result.action === 'select') {
        return '已确认';
    }
    if (result.action === 'ask_boss') {
        return '问老板';
    }
    if (result.action === 'no_match') {
        return '无匹配';
    }
    if (Array.isArray(result.matches) && result.matches.length) {
        return '待确认';
    }
    return '待人工搜索';
}

function getResultPriority(result) {
    if (!result) {
        return 0;
    }

    if (result.action === 'ask_boss') {
        return 450;
    }
    if (result.action === 'no_match' && (!Array.isArray(result.matches) || !result.matches.length)) {
        return 420;
    }
    if (!result.confirmed && (!Array.isArray(result.matches) || !result.matches.length)) {
        return 360;
    }

    const score = Number(getResultPrimaryCandidate(result)?.score || 0);
    if (!result.confirmed && score < 0.45) {
        return 280;
    }
    if (!result.confirmed) {
        return 180;
    }
    return 0;
}

function buildUploadHelpText() {
    return [
        '当前还没有可分析的报价结果。',
        '',
        '建议直接从当前页面开始：',
        '- 点击“上传报价”重新导入 Excel 报价单',
        '- 或点击“OCR 图片”走图片识别',
        '- 导入后先确认列映射，再进入整页连续确认'
    ].join('\n');
}

function buildLocalMatchExplanation(itemIndex = getActiveAssistantIndex()) {
    const results = getMatchResultsList();
    const result = results[itemIndex];
    if (!result) {
        return buildUploadHelpText();
    }

    const queryItem = result.query_item || {};
    const candidate = getResultPrimaryCandidate(result);
    const product = getCandidateProduct(candidate);
    const matches = Array.isArray(result.matches) ? result.matches : [];
    const alternatives = Array.isArray(result.alternatives) ? result.alternatives : [];
    const score = getCandidateScoreText(candidate);
    const reasons = [];
    const nextSteps = [];

    if (candidate) {
        reasons.push(`当前首选是 **${getCandidateDisplayName(candidate)}**，推荐度 ${score}`);
    } else {
        reasons.push('当前没有稳定首选，系统还没找到足够像的候选');
    }

    if (product.brand || queryItem.brand) {
        reasons.push(`品牌线索：报价单侧是 **${queryItem.brand || queryItem.spec || '未提供'}**，候选侧是 **${product.brand || '待补充'}**`);
    }

    if (queryItem.spec || product.model || product.spec) {
        reasons.push(`规格线索：报价单 **${queryItem.spec || '未提供'}**，候选 **${product.model || product.spec || '待补充'}**`);
    }

    reasons.push(`当前候选数量：自动候选 ${matches.length} 个，替代候选 ${alternatives.length} 个`);

    if (result.confirmed && result.action === 'select') {
        nextSteps.push('这条已经确认，可继续往下处理下一条');
    } else if (result.action === 'ask_boss') {
        nextSteps.push('这条已经标记为“问老板”，建议补充关键判断依据后再回头确认');
    } else if (result.action === 'no_match') {
        nextSteps.push('这条已经标记为“无匹配”，若仍不放心就用全商城搜索再扫一次');
    } else if (!matches.length) {
        nextSteps.push('优先打开“全商城搜索”，在弹窗里人工搜索并直接选 SKU');
    } else {
        nextSteps.push('如果首选就是对的，直接点“确认当前推荐”收口');
        nextSteps.push('如果不稳，先看右侧候选框和替代候选，再考虑全商城搜索');
    }

    return [
        `当前焦点：**ITEM ${itemIndex + 1} · ${queryItem.name || '未命名报价项'}**`,
        `状态：**${getResultStatusText(result)}**`,
        candidate ? `当前候选：**${getCandidateDisplayName(candidate)}** · ${formatAssistantPrice(product.market_price || product.price)}` : '当前候选：**暂无稳定候选**',
        '',
        '判断依据：',
        ...reasons.map(line => `- ${line}`),
        '',
        '下一步建议：',
        ...nextSteps.map(line => `- ${line}`)
    ].join('\n');
}

function buildLocalRecommendationText(itemIndex = getActiveAssistantIndex()) {
    const results = getMatchResultsList();
    const result = results[itemIndex];
    if (!result) {
        return buildUploadHelpText();
    }

    const candidates = [
        ...(Array.isArray(result.matches) ? result.matches : []),
        ...(Array.isArray(result.alternatives) ? result.alternatives : [])
    ].slice(0, 5);

    if (!candidates.length) {
        return [
            `ITEM ${itemIndex + 1} 当前没有可用的自动候选。`,
            '',
            '建议直接做这两步：',
            '- 打开“全商城搜索”弹窗，用名称 / 规格 / 编码人工搜',
            '- 如果仍然没有对的，就先标记“无匹配”或“问老板”'
        ].join('\n');
    }

    return [
        `ITEM ${itemIndex + 1} 的候选建议：`,
        '',
        ...candidates.slice(0, 3).map((candidate, index) => {
            const product = getCandidateProduct(candidate);
            return `${index + 1}. **${getCandidateDisplayName(candidate)}**\n   - 推荐度：${getCandidateScoreText(candidate)}\n   - 编码：${getCandidateDisplayCode(candidate)}\n   - 价格：${formatAssistantPrice(product.market_price || product.price)}\n   - 供应商：${product.supplier || '待补充'}`;
        }),
        '',
        '判断规则：优先看推荐度、规格是否贴近、品牌是否一致，再看价格是否合理。'
    ].join('\n');
}

function buildQueueSummaryText() {
    const results = getMatchResultsList();
    if (!results.length) {
        return buildUploadHelpText();
    }

    const confirmed = results.filter(result => result?.confirmed && result?.action === 'select').length;
    const askBoss = results.filter(result => result?.action === 'ask_boss').length;
    const noMatch = results.filter(result => result?.action === 'no_match').length;
    const pending = results.filter(result => !result?.confirmed).length;

    const topItems = results
        .map((result, index) => ({ index, result, priority: getResultPriority(result) }))
        .filter(item => item.priority > 0)
        .sort((a, b) => b.priority - a.priority)
        .slice(0, 5);

    const lines = [
        `当前报价单共 **${results.length}** 项。`,
        `已确认 **${confirmed}** 项，待确认 **${pending}** 项，问老板 **${askBoss}** 项，无匹配 **${noMatch}** 项。`,
        ''
    ];

    if (!topItems.length) {
        lines.push('现在没有高优先级阻塞项，可以直接做导出检查。');
        return lines.join('\n');
    }

    lines.push('当前最该优先处理的条目：');
    topItems.forEach(({ index, result }) => {
        const queryItem = result.query_item || {};
        lines.push(`- ITEM ${index + 1} · ${queryItem.name || '未命名报价项'} · ${getResultStatusText(result)}`);
    });

    return lines.join('\n');
}

function buildExportReadinessText() {
    const results = getMatchResultsList();
    if (!results.length) {
        return buildUploadHelpText();
    }

    const confirmed = results.filter(result => result?.confirmed && result?.action === 'select').length;
    const pending = results.filter(result => !result?.confirmed).length;
    const blockers = results.filter(result => result?.action === 'ask_boss' || result?.action === 'no_match').length;

    const lines = [
        `导出检查：当前共 **${results.length}** 项，已确认可导出 **${confirmed}** 项。`
    ];

    if (pending === 0 && blockers === 0) {
        lines.push('现在已经可以直接走正式导出。');
        lines.push('如果你还想把人工候选留给别人二次核对，可以同时导出“候选报价单”。');
        return lines.join('\n');
    }

    lines.push(`现在还不能完全收口：待确认 **${pending}** 项，异常/待老板确认 **${blockers}** 项。`);
    lines.push('');
    lines.push('建议顺序：');
    lines.push('- 先收掉高分但未确认的条目');
    lines.push('- 再处理“问老板”和“无匹配”');
    lines.push('- 如果需要交给别人补选，先导出“候选报价单”');

    return lines.join('\n');
}

function buildOfflineReply(message) {
    const text = String(message || '').trim();
    if (!text) {
        return '可以直接问我：当前这条为什么这么匹配、还有哪些待确认、现在能不能导出。';
    }

    if (!getMatchResultsList().length) {
        return buildUploadHelpText();
    }

    if (/(导出|候选报价单|能不能导|可不可以导|收口)/.test(text)) {
        return buildExportReadinessText();
    }

    if (/(待处理|清单|还差|剩下|问老板|无匹配|优先)/.test(text)) {
        return buildQueueSummaryText();
    }

    if (/(候选|替代|推荐|换一个|备选)/.test(text)) {
        return buildLocalRecommendationText();
    }

    if (/(为什么|解释|匹配|这条|当前项|当前条)/.test(text)) {
        return buildLocalMatchExplanation();
    }

    return [
        buildQueueSummaryText(),
        '',
        '你也可以继续问得更直接一点：',
        '- 这条为什么匹到它',
        '- 还有哪些没确认',
        '- 现在能不能导出',
        '- 给我看看当前候选建议'
    ].join('\n');
}

function trimChatHistory() {
    if (chatHistory.length > AI_HISTORY_LIMIT) {
        chatHistory = chatHistory.slice(-AI_HISTORY_LIMIT);
    }
}

function addChatMessage(role, content) {
    const container = document.getElementById('aiChatContainer');
    if (!container) {
        return;
    }

    const welcome = container.querySelector('.ai-welcome-message');
    if (welcome) {
        welcome.remove();
    }

    const messageDiv = document.createElement('div');
    messageDiv.className = `ai-message ${role}`;
    messageDiv.innerHTML = `<div class="message-content">${formatAIResponse(content)}</div>`;
    container.appendChild(messageDiv);
    container.scrollTop = container.scrollHeight;
}

function showTypingIndicator() {
    const container = document.getElementById('aiChatContainer');
    if (!container || document.getElementById('aiTypingIndicator')) {
        return;
    }

    const typingDiv = document.createElement('div');
    typingDiv.className = 'ai-typing';
    typingDiv.id = 'aiTypingIndicator';
    typingDiv.innerHTML = `
        <div class="ai-typing-dots">
            <span></span>
            <span></span>
            <span></span>
        </div>
    `;
    container.appendChild(typingDiv);
    container.scrollTop = container.scrollHeight;
}

function hideTypingIndicator() {
    document.getElementById('aiTypingIndicator')?.remove();
}

function getAIPanelElement() {
    return document.getElementById('aiAssistantPanel');
}

function getAIFloatButton() {
    return document.querySelector('.ai-float-btn');
}

function setAIPanelOpen(isOpen) {
    const panel = getAIPanelElement();
    const floatButton = getAIFloatButton();
    if (!panel || !floatButton) {
        return;
    }

    panel.classList.toggle('open', !!isOpen);
    panel.setAttribute('aria-hidden', isOpen ? 'false' : 'true');
    floatButton.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
    localStorage.setItem(AI_PANEL_STORAGE_KEY, isOpen ? '1' : '0');
}

function openAIPanel() {
    setAIPanelOpen(true);
}

function closeAIPanel() {
    setAIPanelOpen(false);
}

function toggleAIPanel() {
    const panel = getAIPanelElement();
    setAIPanelOpen(!panel?.classList.contains('open'));
}

function updateAIBadge() {
    const badge = document.getElementById('aiFloatBadge');
    if (!badge) {
        return;
    }

    const results = getMatchResultsList();
    const pendingCount = results.filter(result => !result?.confirmed).length;
    const issueCount = results.filter(result => result?.action === 'ask_boss' || result?.action === 'no_match').length;
    const attentionCount = pendingCount + issueCount;

    badge.hidden = attentionCount <= 0;
    badge.textContent = attentionCount > 99 ? '99+' : String(attentionCount);
}

function renderAssistantSummary() {
    const summary = document.getElementById('aiAssistantSummary');
    const title = document.getElementById('aiAssistantContextTitle');
    const meta = document.getElementById('aiAssistantContextMeta');
    const mode = document.getElementById('aiModePill');

    if (!summary || !title || !meta || !mode) {
        return;
    }

    mode.textContent = getAIModeLabel();

    const results = getMatchResultsList();
    if (!results.length) {
        title.textContent = '等待新的报价单';
        meta.textContent = '直接在当前页重新上传报价单，确认列映射后就会回到连续确认流里。';
        summary.innerHTML = `
            <button class="ai-summary-card is-neutral" type="button" onclick="WorkspaceEntryActions.openQuoteUpload()">
                <div class="ai-summary-card-title">立即开始</div>
                <div class="ai-summary-card-value">上传报价</div>
                <div class="ai-summary-card-meta">从当前页直接换单</div>
            </button>
            <button class="ai-summary-card is-neutral" type="button" onclick="WorkspaceEntryActions.openOCRUpload()">
                <div class="ai-summary-card-title">图片报价</div>
                <div class="ai-summary-card-value">OCR</div>
                <div class="ai-summary-card-meta">图片也能走同一流程</div>
            </button>
            <button class="ai-summary-card is-neutral" type="button" onclick="askProductInfo()">
                <div class="ai-summary-card-title">当前建议</div>
                <div class="ai-summary-card-value">先上传</div>
                <div class="ai-summary-card-meta">再确认，再导出</div>
            </button>
        `;
        updateAIBadge();
        return;
    }

    const { index, result } = getActiveAssistantEntry();
    const queryItem = result?.query_item || {};
    const primary = getResultPrimaryCandidate(result);
    const confirmed = results.filter(item => item?.confirmed && item?.action === 'select').length;
    const pending = results.filter(item => !item?.confirmed).length;
    const issues = results.filter(item => item?.action === 'ask_boss' || item?.action === 'no_match').length;

    title.textContent = `ITEM ${index + 1} · ${queryItem.name || '未命名报价项'}`;
    meta.textContent = `${getResultStatusText(result)} · 当前候选 ${primary ? getCandidateDisplayName(primary) : '暂无稳定候选'} · 已确认 ${confirmed}/${results.length}`;
    summary.innerHTML = `
        <button class="ai-summary-card is-neutral" type="button" onclick="askExplainMatch(${index})">
            <div class="ai-summary-card-title">当前焦点</div>
            <div class="ai-summary-card-value">${escapeHtml(getResultStatusText(result))}</div>
            <div class="ai-summary-card-meta">${escapeHtml(primary ? getCandidateScoreText(primary) : '待人工搜索')}</div>
        </button>
        <button class="ai-summary-card ${pending + issues > 0 ? 'is-warning' : 'is-neutral'}" type="button" onclick="askQueueSummary()">
            <div class="ai-summary-card-title">待处理</div>
            <div class="ai-summary-card-value">${pending + issues}</div>
            <div class="ai-summary-card-meta">未确认 ${pending} · 异常 ${issues}</div>
        </button>
        <button class="ai-summary-card ${pending === 0 && issues === 0 ? 'is-success' : 'is-warning'}" type="button" onclick="askExportReadiness()">
            <div class="ai-summary-card-title">导出状态</div>
            <div class="ai-summary-card-value">${pending === 0 && issues === 0 ? '可导出' : '待收口'}</div>
            <div class="ai-summary-card-meta">已确认 ${confirmed} 项</div>
        </button>
    `;

    updateAIBadge();
}

function updateAIStatusUI(status) {
    const dot = document.getElementById('aiStatusDot');
    const name = document.getElementById('aiProviderName');

    if (!dot || !name) {
        return;
    }

    if (!status.enabled) {
        dot.className = 'ai-status-dot inactive';
        name.textContent = '助手未启用';
    } else if (status.available) {
        dot.className = 'ai-status-dot active';
        name.textContent = getProviderLabel(status.provider);
    } else {
        dot.className = 'ai-status-dot fallback';
        name.textContent = '本地助手';
    }

    renderAssistantSummary();
}

async function initAIAssistant() {
    try {
        const response = await fetch('/api/ai/status');
        const data = await response.json();

        if (data.success) {
            aiEnabled = !!data.enabled;
            aiAvailable = !!data.available;
            aiProvider = data.provider || 'none';
            updateAIStatusUI(data);
            return;
        }
    } catch (error) {
        console.error('获取 AI 状态失败:', error);
    }

    aiEnabled = true;
    aiAvailable = false;
    aiProvider = 'none';
    updateAIStatusUI({ enabled: true, available: false, provider: 'none' });
}

async function sendAIMessage() {
    const input = document.getElementById('aiInput');
    if (!input) {
        return;
    }

    const message = input.value.trim();
    if (!message) {
        return;
    }

    addChatMessage('user', message);
    input.value = '';
    showTypingIndicator();

    try {
        let reply = '';

        if (aiEnabled && aiAvailable) {
            const response = await fetch('/api/ai/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    messages: [...chatHistory, { role: 'user', content: message }]
                })
            });

            const data = await response.json();
            if (!data.success) {
                throw new Error(data.message || 'AI 对话失败');
            }
            reply = data.response || '没有返回内容。';
        } else {
            await new Promise(resolve => window.setTimeout(resolve, 120));
            reply = buildOfflineReply(message);
        }

        hideTypingIndicator();
        addChatMessage('assistant', reply);
        chatHistory.push({ role: 'user', content: message });
        chatHistory.push({ role: 'assistant', content: reply });
        trimChatHistory();
    } catch (error) {
        hideTypingIndicator();
        const fallbackReply = buildOfflineReply(message);
        addChatMessage('assistant', fallbackReply);
        chatHistory.push({ role: 'user', content: message });
        chatHistory.push({ role: 'assistant', content: fallbackReply });
        trimChatHistory();
        console.error('AI 对话失败，已回退到本地辅助模式:', error);
    }
}

async function askExplainMatch(itemIndex) {
    const targetIndex = typeof itemIndex === 'number' ? itemIndex : getActiveAssistantIndex();
    const prompt = `请解释 ITEM ${targetIndex + 1} 当前的匹配判断`;
    addChatMessage('user', prompt);
    addChatMessage('assistant', aiEnabled && aiAvailable ? '正在分析当前匹配...' : buildLocalMatchExplanation(targetIndex));

    if (!(aiEnabled && aiAvailable)) {
        return;
    }

    try {
        const response = await fetch(`/api/ai/explain_match/${targetIndex}`);
        const data = await response.json();
        if (!data.success) {
            throw new Error(data.message || '生成解释失败');
        }

        const explanation = data.explanation?.text || buildLocalMatchExplanation(targetIndex);
        const container = document.getElementById('aiChatContainer');
        const messages = container?.querySelectorAll('.ai-message.assistant');
        const lastMessage = messages?.[messages.length - 1];
        if (lastMessage) {
            lastMessage.querySelector('.message-content').innerHTML = formatAIResponse(explanation);
        }
    } catch (error) {
        const container = document.getElementById('aiChatContainer');
        const messages = container?.querySelectorAll('.ai-message.assistant');
        const lastMessage = messages?.[messages.length - 1];
        if (lastMessage) {
            lastMessage.querySelector('.message-content').innerHTML = formatAIResponse(buildLocalMatchExplanation(targetIndex));
        }
        console.error('获取 AI 解释失败:', error);
    }
}

async function askRecommend(itemIndex) {
    const targetIndex = typeof itemIndex === 'number' ? itemIndex : getActiveAssistantIndex();
    addChatMessage('user', `给我看 ITEM ${targetIndex + 1} 的候选建议`);

    if (!(aiEnabled && aiAvailable)) {
        addChatMessage('assistant', buildLocalRecommendationText(targetIndex));
        return;
    }

    try {
        const response = await fetch('/api/ai/recommend', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ item_index: targetIndex })
        });

        const data = await response.json();
        if (data.success && Array.isArray(data.recommendations) && data.recommendations.length) {
            addChatMessage('assistant', data.recommendations.map(item => item.recommendation || item).join('\n\n'));
            return;
        }
    } catch (error) {
        console.error('获取 AI 推荐失败:', error);
    }

    addChatMessage('assistant', buildLocalRecommendationText(targetIndex));
}

function askQueueSummary() {
    addChatMessage('user', '把当前待处理清单告诉我');
    addChatMessage('assistant', buildQueueSummaryText());
}

function askExportReadiness() {
    addChatMessage('user', '检查现在能不能导出');
    addChatMessage('assistant', buildExportReadinessText());
}

function askProductInfo() {
    addChatMessage('user', '告诉我现在该先做什么');
    addChatMessage('assistant', getMatchResultsList().length ? buildQueueSummaryText() : buildUploadHelpText());
}

async function aiRematchItem(itemIndex) {
    if (!(aiEnabled && aiAvailable)) {
        showToast('warning', '当前未连接在线 AI，先按本地匹配结果确认');
        return;
    }

    showLoading('AI 重新匹配中...');

    try {
        const response = await fetch(`/api/ai/rematch/${itemIndex}`, { method: 'POST' });
        const data = await response.json();
        hideLoading();

        if (!data.success) {
            throw new Error(data.message || 'AI 重新匹配失败');
        }

        if (typeof matchResults !== 'undefined' && matchResults[itemIndex]) {
            matchResults[itemIndex].matches = data.matches;
            matchResults[itemIndex].best_match = data.matches.length > 0 ? data.matches[0] : null;
            matchResults[itemIndex].ai_enhanced = data.ai_enhanced;
        }

        if (typeof renderMatchResults === 'function') {
            renderMatchResults();
        }
        showToast('success', 'AI 重新匹配完成');
    } catch (error) {
        hideLoading();
        showToast('error', error.message || 'AI 重新匹配失败');
    }
}

async function aiMatchAll() {
    if (!(aiEnabled && aiAvailable)) {
        showToast('warning', '当前未连接在线 AI，可先按现有候选确认');
        return;
    }

    if (typeof quoteItems === 'undefined' || !quoteItems || quoteItems.length === 0) {
        showToast('warning', '请先上传报价单');
        return;
    }

    showLoading('AI 批量匹配中，请稍候...');

    try {
        const response = await fetch('/api/ai/match_all', { method: 'POST' });
        const data = await response.json();
        hideLoading();

        if (!data.success) {
            throw new Error(data.message || 'AI 批量匹配失败');
        }

        matchResults = data.match_results;
        if (typeof renderMatchResults === 'function') {
            renderMatchResults();
        }
        showToast('success', `AI 批量匹配完成，共处理 ${data.count} 项`);
    } catch (error) {
        hideLoading();
        showToast('error', error.message || 'AI 批量匹配失败');
    }
}

async function toggleAI() {
    const newEnabled = !aiEnabled;

    try {
        const response = await fetch('/api/ai/toggle', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled: newEnabled })
        });

        const data = await response.json();
        if (!data.success) {
            throw new Error(data.message || '切换 AI 状态失败');
        }

        aiEnabled = !!data.enabled;
        updateAIStatusUI({
            enabled: aiEnabled,
            available: aiAvailable,
            provider: aiProvider
        });
        showToast('success', data.message || 'AI 状态已更新');
    } catch (error) {
        showToast('error', error.message || '切换 AI 状态失败');
    }
}

async function showAIExplanation(itemIndex) {
    const targetIndex = typeof itemIndex === 'number' ? itemIndex : getActiveAssistantIndex();
    let explanationText = buildLocalMatchExplanation(targetIndex);
    let scoreBreakdown = null;

    if (aiEnabled && aiAvailable) {
        try {
            const response = await fetch(`/api/ai/explain_match/${targetIndex}`);
            const data = await response.json();
            if (data.success) {
                explanationText = data.explanation?.text || explanationText;
                scoreBreakdown = data.explanation?.score_breakdown || null;
            }
        } catch (error) {
            console.error('获取 AI 解释详情失败:', error);
        }
    }

    const modalHtml = `
        <div class="modal fade ai-explanation-modal" id="aiExplanationModal" tabindex="-1">
            <div class="modal-dialog modal-dialog-centered modal-lg">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">当前报价项解释</h5>
                        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="关闭"></button>
                    </div>
                    <div class="modal-body">
                        <div class="ai-explanation-text">${formatAIResponse(explanationText)}</div>
                        ${scoreBreakdown && Object.keys(scoreBreakdown).length ? `
                            <div class="ai-score-breakdown">
                                ${Object.entries(scoreBreakdown).map(([key, value]) => `
                                    <div class="score-item">
                                        <span class="label">${escapeHtml(key)}</span>
                                        <span class="score ${value >= 0.7 ? 'score-high' : (value >= 0.4 ? 'score-medium' : 'score-low')}">${Math.round(value * 100)}%</span>
                                    </div>
                                `).join('')}
                            </div>
                        ` : ''}
                    </div>
                </div>
            </div>
        </div>
    `;

    document.getElementById('aiExplanationModal')?.remove();
    document.body.insertAdjacentHTML('beforeend', modalHtml);

    if (typeof bootstrap !== 'undefined') {
        bootstrap.Modal.getOrCreateInstance(document.getElementById('aiExplanationModal')).show();
        return;
    }

    alert(explanationText);
}

function refreshAIAssistantContext(forceRefresh = false) {
    renderAssistantSummary();
    if (forceRefresh) {
        initAIAssistant();
    }
}

document.addEventListener('DOMContentLoaded', function() {
    const aiInput = document.getElementById('aiInput');
    if (aiInput) {
        aiInput.addEventListener('keydown', function(event) {
            if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                sendAIMessage();
            }
        });
    }

    const initialOpen = localStorage.getItem(AI_PANEL_STORAGE_KEY) === '1';
    setAIPanelOpen(initialOpen);
    initAIAssistant();
    renderAssistantSummary();

    const matchResultsContainer = document.getElementById('matchResults');
    if (matchResultsContainer) {
        const observer = new MutationObserver(() => {
            renderAssistantSummary();
        });
        observer.observe(matchResultsContainer, { childList: true, subtree: true });
    }
});

document.addEventListener('ai-assistant-context-change', function() {
    renderAssistantSummary();
});

document.addEventListener('keydown', function(event) {
    if (event.key === 'Escape') {
        closeAIPanel();
    }
});
