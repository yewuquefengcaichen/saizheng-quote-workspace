/**
 * AI助手交互逻辑
 */

// AI助手状态
let aiEnabled = false;
let aiAvailable = false;
let aiProvider = 'none';
let chatHistory = [];
let currentEditItemIndex = 0;

// 初始化AI助手
async function initAIAssistant() {
    try {
        const response = await fetch('/api/ai/status');
        const data = await response.json();

        if (data.success) {
            aiEnabled = data.enabled;
            aiAvailable = data.available;
            aiProvider = data.provider || 'none';

            updateAIStatusUI(data);
            console.log('AI服务状态:', data);
        }
    } catch (error) {
        console.error('获取AI状态失败:', error);
        updateAIStatusUI({ enabled: false, available: false });
    }
}

// 更新AI状态UI
function updateAIStatusUI(status) {
    const dot = document.getElementById('aiStatusDot');
    const name = document.getElementById('aiProviderName');

    if (!dot || !name) return;

    if (!status.enabled) {
        dot.className = 'ai-status-dot inactive';
        name.textContent = 'AI已关闭';
    } else if (status.available) {
        dot.className = 'ai-status-dot active';
        const providerNames = {
            'claude': 'Claude AI',
            'openai': 'GPT AI',
            'local': '本地AI'
        };
        name.textContent = providerNames[status.provider] || 'AI助手';
    } else {
        dot.className = 'ai-status-dot fallback';
        name.textContent = '离线模式';
    }

    // 更新快捷按钮状态
    const quickBtns = document.querySelectorAll('.ai-quick-actions button');
    quickBtns.forEach(btn => {
        btn.disabled = !status.available;
        btn.style.opacity = status.available ? '1' : '0.5';
    });
}

// 打开/关闭AI面板
function toggleAIPanel() {
    const panel = document.getElementById('aiAssistantPanel');
    if (panel) {
        panel.classList.toggle('open');
    }
}

// 发送AI消息
async function sendAIMessage() {
    const input = document.getElementById('aiInput');
    const message = input.value.trim();

    if (!message) return;

    // 添加用户消息到聊天区
    addChatMessage('user', message);
    input.value = '';

    // 显示打字指示器
    showTypingIndicator();

    try {
        const response = await fetch('/api/ai/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                messages: [...chatHistory, { role: 'user', content: message }]
            })
        });

        const data = await response.json();
        hideTypingIndicator();

        if (data.success) {
            addChatMessage('assistant', data.response);
            chatHistory.push({ role: 'user', content: message });
            chatHistory.push({ role: 'assistant', content: data.response });

            // 限制历史记录长度
            if (chatHistory.length > 20) {
                chatHistory = chatHistory.slice(-20);
            }
        } else {
            addChatMessage('assistant', '抱歉，处理您的请求时出现问题：' + data.message);
        }
    } catch (error) {
        hideTypingIndicator();
        addChatMessage('assistant', '网络错误，请稍后重试。');
        console.error('AI对话错误:', error);
    }
}

// 添加消息到聊天容器
function addChatMessage(role, content) {
    const container = document.getElementById('aiChatContainer');
    if (!container) return;

    // 移除欢迎消息
    const welcome = container.querySelector('.ai-welcome-message');
    if (welcome) {
        welcome.remove();
    }

    const messageDiv = document.createElement('div');
    messageDiv.className = `ai-message ${role}`;
    messageDiv.innerHTML = `<div class="message-content">${formatAIResponse(content)}</div>`;
    container.appendChild(messageDiv);

    // 滚动到底部
    container.scrollTop = container.scrollHeight;
}

// 转义HTML，避免消息内容直接注入页面
function escapeHtml(content) {
    return String(content ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

// 格式化AI响应（简单Markdown支持）
function formatAIResponse(content) {
    return escapeHtml(content)
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/\n/g, '<br>');
}

// 显示打字指示器
function showTypingIndicator() {
    const container = document.getElementById('aiChatContainer');
    if (!container) return;

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

// 隐藏打字指示器
function hideTypingIndicator() {
    const indicator = document.getElementById('aiTypingIndicator');
    if (indicator) {
        indicator.remove();
    }
}

// 快捷操作：解释匹配
async function askExplainMatch(itemIndex) {
    if (typeof itemIndex === 'undefined') {
        itemIndex = currentEditItemIndex || 0;
    }

    // 检查是否有匹配结果
    if (typeof matchResults === 'undefined' || !matchResults || matchResults.length === 0) {
        showToast('warning', '请先进行商品匹配');
        return;
    }

    addChatMessage('user', '请解释当前匹配结果');

    try {
        const response = await fetch(`/api/ai/explain_match/${itemIndex}`);
        const data = await response.json();

        if (data.success) {
            let explanationText = data.explanation.text;

            // 如果有评分分解，显示详细评分
            if (data.explanation.score_breakdown) {
                const scores = data.explanation.score_breakdown;
                explanationText += '\n\n**评分详情:**\n';
                for (const [key, value] of Object.entries(scores)) {
                    const labelMap = {
                        'traditional': '传统匹配',
                        'semantic': '语义相似',
                        'category': '分类匹配',
                        'brand': '品牌匹配',
                        'similarity': '文本相似',
                        'type_match': '类型匹配',
                        'keyword_overlap': '关键词'
                    };
                    explanationText += `- ${labelMap[key] || key}: ${(value * 100).toFixed(0)}%\n`;
                }
            }

            addChatMessage('assistant', explanationText);
        } else {
            addChatMessage('assistant', '无法生成匹配解释：' + data.message);
        }
    } catch (error) {
        addChatMessage('assistant', '生成解释时出错，请稍后重试。');
    }
}

// 快捷操作：推荐替代品
async function askRecommend(itemIndex) {
    if (typeof itemIndex === 'undefined') {
        itemIndex = currentEditItemIndex || 0;
    }

    if (typeof matchResults === 'undefined' || !matchResults || matchResults.length === 0) {
        showToast('warning', '请先进行商品匹配');
        return;
    }

    addChatMessage('user', '请推荐替代商品');

    try {
        const response = await fetch('/api/ai/recommend', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ item_index: itemIndex })
        });

        const data = await response.json();

        if (data.success && data.recommendations.length > 0) {
            let recommendationText = data.recommendations.map(r => r.recommendation || r).join('\n\n');
            addChatMessage('assistant', recommendationText);
        } else {
            addChatMessage('assistant', '暂无替代品推荐，请尝试其他商品。');
        }
    } catch (error) {
        addChatMessage('assistant', '生成推荐时出错，请稍后重试。');
    }
}

// 快捷操作：查询商品信息
async function askProductInfo() {
    addChatMessage('user', '请介绍商品库中的热门商品');

    // 发送消息到AI
    const input = document.getElementById('aiInput');
    input.value = '请介绍商品库中的热门劳保商品';
    await sendAIMessage();
}

// AI重新匹配
async function aiRematchItem(itemIndex) {
    showLoading('AI重新匹配中...');

    try {
        const response = await fetch(`/api/ai/rematch/${itemIndex}`, {
            method: 'POST'
        });

        const data = await response.json();
        hideLoading();

        if (data.success) {
            // 更新本地数据
            if (typeof matchResults !== 'undefined') {
                matchResults[itemIndex].matches = data.matches;
                matchResults[itemIndex].best_match = data.matches.length > 0 ? data.matches[0] : null;
                matchResults[itemIndex].ai_enhanced = data.ai_enhanced;

                // 重新渲染
                if (typeof renderMatchResults === 'function') {
                    renderMatchResults();
                }
            }
            showToast('success', 'AI匹配完成');
        } else {
            showToast('error', data.message || '匹配失败');
        }
    } catch (error) {
        hideLoading();
        showToast('error', 'AI匹配失败');
    }
}

// AI批量重新匹配
async function aiMatchAll() {
    if (typeof quoteItems === 'undefined' || !quoteItems || quoteItems.length === 0) {
        showToast('warning', '请先上传报价单');
        return;
    }

    showLoading('AI批量匹配中，请稍候...');

    try {
        const response = await fetch('/api/ai/match_all', {
            method: 'POST'
        });

        const data = await response.json();
        hideLoading();

        if (data.success) {
            matchResults = data.match_results;
            if (typeof renderMatchResults === 'function') {
                renderMatchResults();
            }
            showToast('success', `AI匹配完成，共处理 ${data.count} 项`);
        } else {
            showToast('error', data.message || '匹配失败');
        }
    } catch (error) {
        hideLoading();
        showToast('error', 'AI批量匹配失败');
    }
}

// 开关AI功能
async function toggleAI() {
    const newEnabled = !aiEnabled;

    try {
        const response = await fetch('/api/ai/toggle', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled: newEnabled })
        });

        const data = await response.json();

        if (data.success) {
            aiEnabled = data.enabled;
            updateAIStatusUI({
                enabled: aiEnabled,
                available: aiAvailable,
                provider: aiProvider
            });
            showToast('success', data.message);
        }
    } catch (error) {
        showToast('error', '切换AI状态失败');
    }
}

// 显示AI匹配解释弹窗
async function showAIExplanation(itemIndex) {
    try {
        const response = await fetch(`/api/ai/explain_match/${itemIndex}`);
        const data = await response.json();

        if (data.success) {
            const explanation = data.explanation;

            // 创建弹窗内容
            const modalBody = document.createElement('div');
            modalBody.innerHTML = `
                <div class="ai-explanation-text">
                    ${formatAIResponse(explanation.text)}
                </div>
                ${Object.keys(explanation.score_breakdown || {}).length > 0 ? `
                <div class="ai-score-breakdown">
                    ${Object.entries(explanation.score_breakdown).map(([key, value]) => {
                        const labelMap = {
                            'traditional': '传统匹配',
                            'semantic': '语义相似',
                            'category': '分类匹配',
                            'brand': '品牌匹配',
                            'similarity': '文本相似',
                            'type_match': '类型匹配',
                            'keyword_overlap': '关键词'
                        };
                        const scoreClass = value >= 0.7 ? 'score-high' : (value >= 0.4 ? 'score-medium' : 'score-low');
                        return `
                            <div class="score-item">
                                <span class="label">${labelMap[key] || key}</span>
                                <span class="score ${scoreClass}">${(value * 100).toFixed(0)}%</span>
                            </div>
                        `;
                    }).join('')}
                </div>
                ` : ''}
            `;

            // 使用Bootstrap模态框或自定义弹窗
            if (typeof bootstrap !== 'undefined') {
                const modalHtml = `
                    <div class="modal fade ai-explanation-modal" id="aiExplanationModal" tabindex="-1">
                        <div class="modal-dialog modal-dialog-centered">
                            <div class="modal-content">
                                <div class="modal-header">
                                    <h5 class="modal-title">AI匹配解释</h5>
                                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                                </div>
                                <div class="modal-body">
                                    ${modalBody.innerHTML}
                                </div>
                            </div>
                        </div>
                    </div>
                `;

                // 移除旧的模态框
                const oldModal = document.getElementById('aiExplanationModal');
                if (oldModal) {
                    oldModal.remove();
                }

                // 添加新的模态框
                document.body.insertAdjacentHTML('beforeend', modalHtml);

                // 显示模态框
                const modal = new bootstrap.Modal(document.getElementById('aiExplanationModal'));
                modal.show();
            } else {
                // 简单弹窗
                alert(explanation.text);
            }
        }
    } catch (error) {
        console.error('获取解释失败:', error);
    }
}

// 回车发送消息
document.addEventListener('DOMContentLoaded', function() {
    const aiInput = document.getElementById('aiInput');
    if (aiInput) {
        aiInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendAIMessage();
            }
        });
    }

    // 初始化AI状态
    initAIAssistant();
});