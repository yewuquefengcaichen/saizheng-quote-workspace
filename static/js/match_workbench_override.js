(() => {
  const styleId = 'match-workbench-override-style';
  if (!document.getElementById(styleId)) {
    const style = document.createElement('style');
    style.id = styleId;
    style.textContent = `
      .match-rail-focus-btn {
        width: 100%;
        padding: 0;
        border: 0;
        background: transparent;
        text-align: left;
        color: inherit;
      }
      .match-rail-focus-btn strong {
        display: block;
        margin-bottom: 4px;
        color: var(--qe-text-strong);
      }
      .match-rail-focus-btn span {
        display: block;
        font-size: 0.8rem;
        line-height: 1.55;
        color: var(--qe-text-muted);
      }
      .quote-item-card[data-item-index] {
        cursor: default;
      }
      .quote-item-shell-top[data-focus-workbench] {
        cursor: pointer;
      }
      .quote-item-shell-top[data-focus-workbench]:hover .quote-item-title {
        color: var(--qe-accent-strong);
      }
      .match-inspector-media-title {
        color: var(--qe-text-strong);
      }
    `;
    document.head.appendChild(style);
  }

  const originalInitCandidateActions = initCandidateActions;
  const originalSelectProduct = selectProduct;
  const originalMarkNoMatch = markNoMatch;
  const originalMarkAskBoss = markAskBoss;
  const originalFilterResults = filterResults;
  let workbenchUserPinnedFocus = false;

  function getMatchStatusMeta(result) {
    const matches = Array.isArray(result?.matches) ? result.matches : [];
    const selectedProduct = result?.selected_product || null;

    if (result?.confirmed && result?.action === 'select') {
      return { cardClass: 'confirmed', badgeClass: 'status-matched', statusText: '已确认' };
    }
    if (!result?.confirmed && result?.action === 'select' && selectedProduct) {
      return { cardClass: 'pending', badgeClass: 'status-pending', statusText: '待确认' };
    }
    if (result?.action === 'no_match') {
      return { cardClass: 'no-match', badgeClass: 'status-nomatch', statusText: '无匹配' };
    }
    if (result?.action === 'ask_boss') {
      return { cardClass: 'no-match', badgeClass: 'status-nomatch', statusText: '需问老板' };
    }
    if (matches.length > 0) {
      return { cardClass: 'pending', badgeClass: 'status-pending', statusText: '待选择' };
    }
    return { cardClass: 'no-match', badgeClass: 'status-nomatch', statusText: '无匹配' };
  }

  function focusWorkbenchItem(itemIndex, shouldScroll = false) {
    workbenchUserPinnedFocus = true;
    activeWorkbenchIndex = itemIndex;
    renderMatchResults(true);

    if (!shouldScroll) {
      return;
    }

    requestAnimationFrame(() => {
      document.querySelector(`.quote-item-card[data-item-index="${itemIndex}"]`)?.scrollIntoView({
        behavior: 'smooth',
        block: 'start'
      });
    });
  }

  function confirmWorkbenchSelection(itemIndex) {
    const result = matchResults[itemIndex];
    if (!result) return;

    const candidate = result.selected_product || result.matches?.[0] || result.alternatives?.[0];
    if (!candidate) {
      showToast('warning', '当前没有可确认的候选商品');
      return;
    }

    selectProduct(itemIndex, candidate);
  }

  const styleEl = document.getElementById(styleId);
  if (styleEl && !styleEl.dataset.workbenchExtended) {
    styleEl.textContent += `
      .match-rail-list li.is-active {
        border-color: rgba(37, 99, 235, 0.28);
        background: linear-gradient(135deg, rgba(239, 246, 255, 0.96) 0%, rgba(255, 255, 255, 0.92) 100%);
        box-shadow: 0 12px 24px rgba(37, 99, 235, 0.08);
      }
      .match-rail-list li.is-warning {
        border-color: rgba(245, 158, 11, 0.22);
      }
      [data-theme="dark"] .match-rail-list li.is-active {
        border-color: rgba(96, 165, 250, 0.3);
        background: linear-gradient(135deg, rgba(15, 23, 42, 0.96) 0%, rgba(15, 23, 42, 0.9) 58%, rgba(30, 64, 175, 0.2) 100%);
        box-shadow: 0 16px 32px rgba(2, 6, 23, 0.34);
      }
      [data-theme="dark"] .match-rail-list li.is-warning {
        border-color: rgba(251, 191, 36, 0.18);
      }
      .match-stream-section {
        display: flex;
        flex-direction: column;
        gap: 12px;
      }
      .match-stream-section + .match-stream-section {
        margin-top: 8px;
      }
      .match-stream-section-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
      }
      .match-stream-section-title {
        font-size: 0.9rem;
        font-weight: 800;
        color: var(--qe-text-strong);
      }
      .match-stream-section-meta {
        font-size: 0.78rem;
        color: var(--qe-text-muted);
      }
      .match-inspector-option-actions {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin-top: 10px;
      }
      .match-inspector-inline-note {
        margin-top: 10px;
        font-size: 0.8rem;
        line-height: 1.65;
        color: var(--qe-text-muted);
      }
      .match-inspector-card .quote-search-panel {
        margin-top: 0;
      }
      .match-stream-empty {
        min-height: 360px;
      }
    `;
    styleEl.dataset.workbenchExtended = 'true';
  }

  function isIssueResult(result) {
    return result?.action === 'no_match' || result?.action === 'ask_boss';
  }

  function isMatchedResult(result) {
    return !!(result?.confirmed && result?.action === 'select');
  }

  function isPendingResult(result) {
    return !result?.confirmed;
  }

  function setQuotesWorkbenchState(state = 'ready') {
    if (document.body?.dataset?.route !== 'quotes') {
      return;
    }

    const matchTab = document.getElementById('matchTab');
    if (matchTab) {
      matchTab.setAttribute('data-match-state', state);
    }
  }

  function renderQuotesFilteredEmpty() {
    return `
      <div class="workspace-empty-orbit workspace-empty-orbit--quotes">
        <div class="workspace-empty-orbit-visual">
          <i class="bi bi-search"></i>
        </div>
        <div class="workspace-empty-orbit-title">当前筛选条件下没有可处理的报价项。</div>
        <div class="workspace-empty-orbit-copy">试着放宽关键词、恢复全部状态或回到默认排序，让待处理项重新回到你的工作台里。</div>
        <div class="workspace-empty-orbit-pills">
          <span class="workspace-empty-orbit-pill">放宽关键词</span>
          <span class="workspace-empty-orbit-pill">恢复全部状态</span>
          <span class="workspace-empty-orbit-pill">回到默认排序</span>
        </div>
        <div class="quote-empty-actions">
          <button class="btn btn-outline-primary" type="button" onclick="document.getElementById('resetFilterBtn')?.click()">
            <i class="bi bi-arrow-counterclockwise me-2"></i>重置筛选
          </button>
        </div>
      </div>
    `;
  }

  function getPrimaryCandidate(result) {
    return result?.selected_product || result?.matches?.[0] || result?.alternatives?.[0] || null;
  }

  function getPrimaryProduct(result) {
    return getPrimaryCandidate(result)?.product || {};
  }

  function getPrimaryScore(result) {
    return Number(getPrimaryCandidate(result)?.score || 0);
  }

  function getWorkbenchFilters() {
    return {
      searchText: (document.getElementById('searchInput')?.value || '').trim().toLowerCase(),
      rawSearchText: (document.getElementById('searchInput')?.value || '').trim(),
      statusFilter: document.getElementById('statusFilter')?.value || 'all',
      sortFilter: document.getElementById('sortFilter')?.value || 'default'
    };
  }

  function getWorkbenchFilterLabels(filters) {
    const statusMap = {
      all: '全部状态',
      pending: '待确认',
      matched: '已匹配',
      nomatch: '无匹配'
    };

    const sortMap = {
      default: '默认排序',
      'match-desc': '匹配度高到低',
      'match-asc': '匹配度低到高',
      'price-desc': '价格高到低',
      'price-asc': '价格低到高'
    };

    return {
      statusLabel: statusMap[filters.statusFilter] || statusMap.all,
      sortLabel: sortMap[filters.sortFilter] || sortMap.default
    };
  }

  function getVisibleMatchItems() {
    const filters = getWorkbenchFilters();
    let visibleItems = (matchResults || []).map((result, itemIndex) => ({ result, itemIndex }));

    visibleItems = visibleItems.filter(({ result }) => {
      const queryItem = result?.query_item || {};
      const primaryProduct = getPrimaryProduct(result);
      const haystack = [
        queryItem.name,
        queryItem.spec,
        queryItem.remark,
        queryItem.unit,
        primaryProduct.name,
        primaryProduct.model,
        primaryProduct.brand,
        primaryProduct.supplier,
        primaryProduct.code
      ].filter(Boolean).join(' ').toLowerCase();

      const matchesSearch = !filters.searchText || haystack.includes(filters.searchText);
      let matchesStatus = true;

      if (filters.statusFilter === 'pending') {
        matchesStatus = isPendingResult(result);
      } else if (filters.statusFilter === 'matched') {
        matchesStatus = isMatchedResult(result);
      } else if (filters.statusFilter === 'nomatch') {
        matchesStatus = !!(result?.confirmed && isIssueResult(result));
      }

      return matchesSearch && matchesStatus;
    });

    if (filters.sortFilter === 'match-desc') {
      visibleItems.sort((left, right) => (getPrimaryScore(right.result) - getPrimaryScore(left.result)) || (left.itemIndex - right.itemIndex));
    } else if (filters.sortFilter === 'match-asc') {
      visibleItems.sort((left, right) => (getPrimaryScore(left.result) - getPrimaryScore(right.result)) || (left.itemIndex - right.itemIndex));
    } else if (filters.sortFilter === 'price-desc') {
      visibleItems.sort((left, right) => ((parseNumericPrice(getPrimaryProduct(right.result)?.market_price) || 0) - (parseNumericPrice(getPrimaryProduct(left.result)?.market_price) || 0)) || (left.itemIndex - right.itemIndex));
    } else if (filters.sortFilter === 'price-asc') {
      visibleItems.sort((left, right) => ((parseNumericPrice(getPrimaryProduct(left.result)?.market_price) || 0) - (parseNumericPrice(getPrimaryProduct(right.result)?.market_price) || 0)) || (left.itemIndex - right.itemIndex));
    }

    return { filters, visibleItems };
  }

  function ensureActiveWorkbenchItem(visibleItems) {
    if (!visibleItems.length) {
      return null;
    }

    const currentEntry = visibleItems.find(item => item.itemIndex === activeWorkbenchIndex) || null;
    const queueLead = getPriorityQueueItems(visibleItems, 1)[0] || visibleItems[0];

    if (workbenchUserPinnedFocus && currentEntry) {
      return currentEntry;
    }

    if (workbenchUserPinnedFocus && !currentEntry) {
      workbenchUserPinnedFocus = false;
    }

    activeWorkbenchIndex = (queueLead || currentEntry || visibleItems[0]).itemIndex;
    return visibleItems.find(item => item.itemIndex === activeWorkbenchIndex) || visibleItems[0];
  }

  function getStreamSections(visibleItems, filters) {
    if (!filters.rawSearchText && filters.statusFilter === 'all' && filters.sortFilter === 'default') {
      const sections = [
        {
          key: 'pending',
          title: '待人工确认',
          subtitle: '先处理系统已给出候选但还没有最终确认的项目。',
          items: visibleItems.filter(({ result }) => isPendingResult(result))
        },
        {
          key: 'issue',
          title: '异常与待问老板',
          subtitle: '这些项目已经被判定为异常或需要升级决策。',
          items: visibleItems.filter(({ result }) => !!(result?.confirmed && isIssueResult(result)))
        },
        {
          key: 'matched',
          title: '已确认可导出',
          subtitle: '这些项目已经完成确认，可直接进入导出模板。',
          items: visibleItems.filter(({ result }) => isMatchedResult(result))
        }
      ];

      return sections.filter(section => section.items.length > 0);
    }

    return [{
      key: 'filtered',
      title: '筛选结果',
      subtitle: filters.rawSearchText ? `当前关键字：${filters.rawSearchText}` : '按照当前状态和排序方式显示。',
      items: visibleItems
    }];
  }

  function renderMatchInsights(result) {
    const queryItem = result?.query_item || {};
    const feedbackHint = result?.feedback_hint || '';
    const feedbackSummary = result?.feedback_summary || {};
    const imageAssisted = !!result?.image_assisted;
    const isOcrItem = queryItem.source_type === 'ocr';
    const ocrConfidence = Number(queryItem.ocr_confidence || 0);

    return `
      <div class="match-insights">
        ${feedbackHint ? `<span class="learning-hint"><i class="bi bi-clock-history"></i>${escapeHtml(feedbackHint)}</span>` : ''}
        ${feedbackSummary.feedback_count ? `<span class="match-insight-badge badge-learning"><i class="bi bi-bar-chart-line"></i>反馈 ${feedbackSummary.feedback_count} 条</span>` : ''}
        ${feedbackSummary.template_hit_count ? `<span class="match-insight-badge badge-template"><i class="bi bi-stars"></i>模板经验 ${feedbackSummary.template_hit_count}</span>` : ''}
        ${feedbackSummary.mapping_changed_count ? `<span class="match-insight-badge badge-mapping"><i class="bi bi-pencil-square"></i>人工修正 ${feedbackSummary.mapping_changed_count}</span>` : ''}
        ${feedbackSummary.no_match_count ? `<span class="match-insight-badge"><i class="bi bi-x-circle"></i>无匹配 ${feedbackSummary.no_match_count}</span>` : ''}
        ${feedbackSummary.ask_boss_count ? `<span class="match-insight-badge"><i class="bi bi-question-circle"></i>问老板 ${feedbackSummary.ask_boss_count}</span>` : ''}
        ${imageAssisted ? `<span class="match-insight-badge badge-positive"><i class="bi bi-image"></i>图片辅助</span>` : ''}
        ${isOcrItem ? `<span class="match-insight-badge"><i class="bi bi-camera"></i>OCR来源 ${ocrConfidence ? Math.round(ocrConfidence * 100) + '%' : ''}</span>` : ''}
        ${queryItem.low_confidence ? `<span class="match-insight-badge text-warning-emphasis"><i class="bi bi-exclamation-triangle"></i>低置信度项</span>` : ''}
      </div>
    `;
  }

  function getWorkbenchStatusLine(result) {
    const matchesCount = Array.isArray(result?.matches) ? result.matches.length : 0;

    if (result?.confirmed && result?.action === 'select') {
      return '已确认完成，可直接纳入导出。';
    }
    if (!result?.confirmed && result?.action === 'select' && result?.selected_product) {
      return '系统已预选商品，等待人工最终确认。';
    }
    if (result?.action === 'no_match') {
      return '当前已标记无匹配，建议补充人工检索或回源确认。';
    }
    if (result?.action === 'ask_boss') {
      return '当前需升级给老板判断，请补充背景和备选。';
    }
    if (matchesCount > 0) {
      return '已有推荐候选，优先核验首选商品。';
    }
    return '暂未找到有效候选，建议直接人工检索。';
  }

  function renderRecommendationBrief(result, itemIndex) {
    const primary = getPrimaryCandidate(result);
    if (!primary) {
      return `
        <div class="quote-reference-card mt-3">
          <div class="small fw-semibold mb-1"><i class="bi bi-search me-1"></i>当前建议</div>
          <div class="small text-muted">还没有自动推荐结果，请使用右侧人工搜索补齐。</div>
        </div>
      `;
    }

    const product = primary.product || {};
    const scoreText = primary.score ? `${Math.round(primary.score * 100)}%` : '人工检索';
    const marketPrice = parseNumericPrice(product.market_price) || 0;
    const adjustedPrice = getAdjustedPrice(marketPrice, itemIndex) || marketPrice;

    return `
      <div class="quote-reference-card mt-3">
        <div class="small fw-semibold mb-1"><i class="bi bi-stars me-1"></i>当前建议</div>
        <div class="small text-muted">${escapeHtml(product.name || '未命名商品')}</div>
        <div class="small text-muted">供应商：${escapeHtml(product.supplier || '待补充')} · 参考价 ${adjustedPrice > 0 ? '¥' + adjustedPrice.toFixed(2) : '待补充'}</div>
        <div class="small text-muted">推荐依据：${scoreText}${primary.learning_reason ? ' · ' + escapeHtml(primary.learning_reason) : ''}</div>
      </div>
    `;
  }

  function getPriorityQueueItems(visibleItems, limit = 6) {
    return [...visibleItems].sort((left, right) => {
      const leftPriorityWeight = typeof getMatchPriorityWeight === 'function'
        ? getMatchPriorityWeight(left.result)
        : 0;
      const rightPriorityWeight = typeof getMatchPriorityWeight === 'function'
        ? getMatchPriorityWeight(right.result)
        : 0;
      const leftScore = getPrimaryScore(left.result);
      const rightScore = getPrimaryScore(right.result);
      const leftPriority = left.result?.confirmed && isIssueResult(left.result)
        ? 0
        : (!left.result?.confirmed && leftScore < 0.4 ? 1 : (!left.result?.confirmed ? 2 : 3));
      const rightPriority = right.result?.confirmed && isIssueResult(right.result)
        ? 0
        : (!right.result?.confirmed && rightScore < 0.4 ? 1 : (!right.result?.confirmed ? 2 : 3));

      return (rightPriorityWeight - leftPriorityWeight)
        || (leftPriority - rightPriority)
        || (leftScore - rightScore)
        || (left.itemIndex - right.itemIndex);
    }).slice(0, limit);
  }

  function getActiveSectionInfo(visibleItems, filters, activeEntry) {
    if (!activeEntry) {
      return {
        key: 'empty',
        title: '当前没有可展开的报价项',
        subtitle: '调整筛选条件后再继续处理。',
        count: 0
      };
    }

    const activeResult = activeEntry.result;
    const activePosition = visibleItems.findIndex(item => item.itemIndex === activeEntry.itemIndex);

    if (filters.rawSearchText || filters.statusFilter !== 'all' || filters.sortFilter !== 'default') {
      return {
        key: 'filtered',
        title: '筛选结果视图',
        subtitle: filters.rawSearchText
          ? `当前关键字：${filters.rawSearchText}。中区只展开当前焦点项，避免回到旧式长列表。`
          : '当前正在按筛选条件工作，中区只展开一项，左右两侧继续负责排队和核查。',
        count: visibleItems.length,
        position: activePosition + 1
      };
    }

    const pendingCount = visibleItems.filter(({ result }) => isPendingResult(result)).length;
    const issueCount = visibleItems.filter(({ result }) => !!(result?.confirmed && isIssueResult(result))).length;
    const matchedCount = visibleItems.filter(({ result }) => isMatchedResult(result)).length;

    if (activeResult?.confirmed && isIssueResult(activeResult)) {
      return {
        key: 'issue',
        title: '异常升级段',
        subtitle: '当前项已经进入异常或升级判断，建议先补充证据、人工检索或直接升级给老板。',
        count: issueCount,
        position: activePosition + 1
      };
    }

    if (isMatchedResult(activeResult)) {
      return {
        key: 'matched',
        title: '已确认段',
        subtitle: '当前项已经确认完成，中区仅保留复核信息，方便快速扫尾并进入导出。',
        count: matchedCount,
        position: activePosition + 1
      };
    }

    return {
      key: 'pending',
      title: '待人工确认段',
      subtitle: '先核验当前焦点项，再决定是否切换候选、启用备选或进入人工搜索。',
      count: pendingCount,
      position: activePosition + 1
    };
  }

  function renderWorkbenchRail(visibleItems, filters, activeEntry) {
    const matchedCount = matchResults.filter(result => isMatchedResult(result)).length;
    const pendingCount = matchResults.filter(result => isPendingResult(result)).length;
    const issueCount = matchResults.filter(result => !!(result?.confirmed && isIssueResult(result))).length;
    const ocrCount = matchResults.filter(result => result?.query_item?.source_type === 'ocr').length;
    const queueItems = getPriorityQueueItems(visibleItems);
    const filterLabels = getWorkbenchFilterLabels(filters);
    const suggestionText = issueCount > 0
      ? `先处理 ${issueCount} 个异常项，再回到普通待确认项。`
      : (pendingCount > 0
        ? `异常项已清空，继续收尾 ${pendingCount} 个待确认项。`
        : '当前已没有待确认项，可以直接检查导出准备。');

    return `
      <aside class="match-rail">
        <div class="match-rail-card match-rail-card--pulse">
          <div class="match-rail-heading">决策脉冲</div>
          <div class="match-rail-copy">先看总负载、异常与 OCR 压力，再进入焦点项确认。</div>
          <div class="match-rail-stat-grid">
            <div class="match-rail-stat"><strong>${matchResults.length}</strong><span>报价项</span></div>
            <div class="match-rail-stat"><strong>${matchedCount}</strong><span>已确认</span></div>
            <div class="match-rail-stat"><strong>${pendingCount}</strong><span>待确认</span></div>
            <div class="match-rail-stat"><strong>${ocrCount}</strong><span>OCR项</span></div>
          </div>
          <div class="match-rail-focus-note">${suggestionText}</div>
        </div>
        <div class="match-rail-card match-rail-card--command">
          <div class="match-rail-heading">当前指令层</div>
          <div class="match-rail-inline-pills">
            <span class="match-rail-inline-pill">状态 · ${filterLabels.statusLabel}</span>
            <span class="match-rail-inline-pill">排序 · ${filterLabels.sortLabel}</span>
            ${filters.rawSearchText ? `<span class="match-rail-inline-pill">搜索 · ${escapeHtml(filters.rawSearchText)}</span>` : '<span class="match-rail-inline-pill">搜索 · 未启用</span>'}
          </div>
          <ul class="match-rail-list mt-3">
            <li>
              <strong>处理建议</strong>
              <span>${suggestionText}</span>
            </li>
            <li>
              <strong>当前焦点</strong>
              <span>${activeEntry ? `ITEM ${activeEntry.itemIndex + 1} · ${escapeHtml(activeEntry.result?.query_item?.name || '未命名询价项')}` : '当前没有可显示的报价项。'}</span>
            </li>
          </ul>
        </div>
        <div class="match-rail-card match-rail-card--queue">
          <div class="match-rail-heading">优先处理队列</div>
          <div class="match-rail-copy">默认按异常、低分未确认、普通待确认排序，减少回找与回扫。</div>
          <ul class="match-rail-list mt-3">
            ${queueItems.length ? queueItems.map(({ result, itemIndex }) => {
              const primary = getPrimaryCandidate(result);
              const statusMeta = getMatchStatusMeta(result);
              const queueNote = primary
                ? `${statusMeta.statusText} · ${Math.round((primary.score || 0) * 100)}% · ${escapeHtml(primary.product?.name || '未命名商品')}`
                : `${statusMeta.statusText} · 暂无推荐候选`;
              const itemClasses = [
                itemIndex === activeWorkbenchIndex ? 'is-active' : '',
                (!result?.confirmed || isIssueResult(result)) ? 'is-warning' : ''
              ].filter(Boolean).join(' ');

              return `
                <li class="${itemClasses}">
                  <button class="match-rail-focus-btn" type="button" data-item-index="${itemIndex}">
                    <strong>ITEM ${itemIndex + 1} · ${escapeHtml(result?.query_item?.name || '未命名询价项')}</strong>
                    <span>${queueNote}</span>
                  </button>
                </li>
              `;
            }).join('') : '<li><strong>没有匹配结果</strong><span>调整筛选条件后再试。</span></li>'}
          </ul>
        </div>
      </aside>
    `;
  }

  function renderWorkbenchSummary() {
    const totalCount = matchResults.length;
    const confirmedCount = matchResults.filter(item => item.confirmed && item.action === 'select').length;
    const pendingCount = matchResults.filter(item => !item.confirmed).length;
    const issueCount = matchResults.filter(item => item.action === 'no_match' || item.action === 'ask_boss').length;
    const completionRate = totalCount > 0 ? Math.round((confirmedCount / totalCount) * 100) : 0;
    const primaryFocus = matchResults.find(item => !item.confirmed) || matchResults[0] || null;
    const focusName = primaryFocus?.query_item?.name || '等待焦点项';
    const nextAction = issueCount > 0
      ? `优先消灭 ${issueCount} 个异常项，避免导出后返工。`
      : (pendingCount > 0
        ? `继续完成 ${pendingCount} 个待确认项，就可以进入最终导出。`
        : '当前确认已基本完成，可以直接检查模板与导出配置。');
    const readinessTone = issueCount > 0 ? 'is-alert' : (pendingCount > 0 ? 'is-warm' : 'is-strong');

    return `
      <div class="match-workspace-summary">
        <div class="workspace-summary-card workspace-summary-card--hero">
          <div class="workspace-summary-kicker">Decision Brief</div>
          <div class="workspace-summary-title">报价决策台已进入确认阶段。</div>
          <div class="workspace-summary-subtitle">先消灭异常，再收尾待确认项，最后直接把结果送进模板导出。每个报价项都是一个独立决策单元。</div>
          <div class="workspace-summary-progress-shell">
            <div class="workspace-summary-progress-head">
              <span>当前确认进度</span>
              <strong>${completionRate}%</strong>
            </div>
            <div class="workspace-summary-progress-track">
              <span style="width:${Math.min(Math.max(completionRate, 0), 100)}%;"></span>
            </div>
          </div>
          <div class="workspace-summary-stats">
            <div class="workspace-summary-stat"><strong>${totalCount}</strong><span>本次报价项</span></div>
            <div class="workspace-summary-stat"><strong>${confirmedCount}</strong><span>已确认商品</span></div>
            <div class="workspace-summary-stat"><strong>${pendingCount + issueCount}</strong><span>待处理项</span></div>
          </div>
          <div class="workspace-summary-inline-grid">
            <div class="workspace-summary-inline-card">
              <span>当前焦点</span>
              <strong>${escapeHtml(focusName)}</strong>
            </div>
            <div class="workspace-summary-inline-card">
              <span>下一动作</span>
              <strong>${escapeHtml(nextAction)}</strong>
            </div>
          </div>
          <div class="workspace-summary-actions">
            <button class="btn btn-primary btn-sm" type="button" onclick="showExportOptionsForCurrentMatch()"><i class="bi bi-box-arrow-up-right me-1"></i>检查导出配置</button>
            <button class="btn btn-outline-secondary btn-sm" type="button" onclick="window.location.href='/catalog'"><i class="bi bi-grid-3x3-gap me-1"></i>查看商品资产库</button>
          </div>
        </div>
        <div class="workspace-summary-card workspace-summary-card--status">
          <div class="workspace-summary-kicker">Export Readiness</div>
          <div class="workspace-summary-title">导出准备状态</div>
          <div class="workspace-summary-subtitle">模板、价格口径与导出动作已经被独立成中心；这里只负责判断你是否可以无阻塞地进入交付。</div>
          <div class="workspace-summary-readiness ${readinessTone}">
            <span>准备判断</span>
            <strong>${issueCount > 0 ? '先解异常' : (pendingCount > 0 ? '继续确认' : '可以导出')}</strong>
          </div>
          <div class="workspace-summary-status-list">
            <div class="workspace-summary-status-item">
              <div>
                <strong>已确认可导出</strong>
                <span>当前已完成确认、可直接进入模板导出的项目数量。</span>
              </div>
              <div class="workspace-summary-status-value">${confirmedCount}</div>
            </div>
            <div class="workspace-summary-status-item">
              <div>
                <strong>待人工确认</strong>
                <span>仍需从候选、替代品或人工搜索里做最终判断。</span>
              </div>
              <div class="workspace-summary-status-value is-warning">${pendingCount}</div>
            </div>
            <div class="workspace-summary-status-item">
              <div>
                <strong>风险与异常</strong>
                <span>无匹配、需问老板、低置信度项优先处理，避免导出后返工。</span>
              </div>
              <div class="workspace-summary-status-value is-danger">${issueCount}</div>
            </div>
          </div>
        </div>
      </div>
    `;
  }

  renderCandidates = function renderCompactCandidates(matches, itemIndex, selectedProduct, expandAll = false, budgetPrice = null) {
    if (!matches || matches.length === 0) {
      return '<div class="text-muted text-center py-3">没有找到匹配的商品</div>';
    }

    const displayCount = expandAll ? matches.length : 3;
    let html = '';

    matches.slice(0, displayCount).forEach((match, idx) => {
      const product = match.product || {};
      const score = Number(match.score || 0);
      const isSelected = !!(selectedProduct && selectedProduct.index === match.index);
      const isBest = idx === 0;
      const scoreClass = score >= 0.7 ? 'score-high' : (score >= 0.4 ? 'score-medium' : 'score-low');
      const learningDetails = match.learning_details || {};
      const learningReason = match.learning_reason || '';
      const scoreDetails = match.score_details || {};
      const feedbackSummary = match.feedback_summary || {};
      const hasImage = !!(match.has_image || product.image_url || (product.images && product.images.length));
      const productForImage = { ...product, image_assisted: !!match.has_image };
      const marketPrice = parseNumericPrice(product.market_price) || 0;
      const costPriceMeta = getCostPriceMeta(product);
      const costPrice = costPriceMeta.hasValue ? (parseNumericPrice(product.cost_price) || 0) : null;
      const quotePrice = budgetPrice ? (parseNumericPrice(budgetPrice) || marketPrice) : marketPrice;
      const adjustedPrice = getAdjustedPrice(marketPrice, itemIndex);
      const hasAdjustment = priceAdjustment && adjustedPrice !== marketPrice;

      const proofParts = [];
      if (scoreDetails.traditional !== undefined) proofParts.push(`规则 ${Math.round((scoreDetails.traditional || 0) * 100)}%`);
      else proofParts.push(`基础 ${Math.round((match.base_score || score) * 100)}%`);
      if (scoreDetails.semantic !== undefined) proofParts.push(`语义 ${Math.round((scoreDetails.semantic || 0) * 100)}%`);
      if (learningDetails.selection_boost) proofParts.push(`历史确认 +${(learningDetails.selection_boost * 100).toFixed(0)}%`);
      else if (feedbackSummary.feedback_count) proofParts.push(`历史反馈 ${feedbackSummary.feedback_count}`);
      if (learningDetails.template_bonus) proofParts.push(`模板 +${(learningDetails.template_bonus * 100).toFixed(0)}%`);
      if (learningDetails.image_bonus && hasImage) proofParts.push(`图片 +${(learningDetails.image_bonus * 100).toFixed(0)}%`);
      if (learningDetails.rejection_penalty) proofParts.push(`排除 -${(learningDetails.rejection_penalty * 100).toFixed(0)}%`);
      if (learningDetails.mapping_penalty) proofParts.push(`修正 -${(learningDetails.mapping_penalty * 100).toFixed(0)}%`);

      let profitHtml = '';
      if (costPrice > 0 && quotePrice > 0) {
        const profit = quotePrice - costPrice;
        const profitMargin = (profit / costPrice * 100).toFixed(1);
        const profitClass = profit >= 0 ? 'text-success' : 'text-danger';
        const profitIcon = profit >= 0 ? 'arrow-up-right' : 'arrow-down-right';
        profitHtml = `
          <div class="profit-info ${profitClass}">
            <i class="bi bi-${profitIcon}"></i>${profit >= 0 ? '利润' : '倒挂'} ¥${Math.abs(profit).toFixed(2)} (${Math.abs(Number(profitMargin)).toFixed(1)}%)
          </div>
        `;
      } else if (marketPrice > 0 && quotePrice > 0 && quotePrice !== marketPrice) {
        const diff = quotePrice - marketPrice;
        const diffPercent = (diff / marketPrice * 100).toFixed(1);
        const diffClass = diff <= 0 ? 'text-success' : 'text-warning';
        const diffText = diff <= 0 ? '低于市场价' : '高于市场价';
        const diffIcon = diff <= 0 ? 'dash-circle' : 'exclamation-circle';
        profitHtml = `
          <div class="profit-info ${diffClass}">
            <i class="bi bi-${diffIcon}"></i>${diffText} ¥${Math.abs(diff).toFixed(2)} (${Math.abs(Number(diffPercent)).toFixed(1)}%)
          </div>
        `;
      }

      html += `
        <div class="product-card ${isSelected ? 'selected' : ''} ${isBest ? 'best-match' : ''}"
             data-item-index="${itemIndex}" data-match-index="${match.index}">
          <div class="product-card-layout">
            <div class="candidate-visual">
              ${ProductImageManager.createImageHtml(productForImage, 'small')}
            </div>
            <div class="candidate-score-stack">
              <div class="match-score ${scoreClass}">
                ${Math.round(score * 100)}%
              </div>
              <span class="candidate-rank-badge">${isBest ? '首选' : `候选 ${idx + 1}`}</span>
            </div>
            <div class="candidate-main">
              <div class="candidate-title">${product.name || '-'}</div>
              <div class="candidate-subtitle">
                ${product.brand ? `品牌 ${escapeHtml(product.brand)}` : '品牌待补充'}
                ${product.category ? ` · ${escapeHtml(product.category)}` : ''}
                ${product.supplier ? ` · ${escapeHtml(product.supplier)}` : ''}
              </div>
              <div class="candidate-meta">
                ${hasImage ? '<span class="qe-badge qe-badge-info"><i class="bi bi-image"></i>有图</span>' : '<span class="qe-badge qe-badge-muted">待补图</span>'}
                ${learningReason ? `<span class="qe-badge qe-badge-secondary"><i class="bi bi-stars"></i>${escapeHtml(learningReason)}</span>` : ''}
                ${feedbackSummary.feedback_count ? `<span class="qe-badge qe-badge-success"><i class="bi bi-clock-history"></i>${feedbackSummary.feedback_count}条历史</span>` : ''}
              </div>
              <div class="candidate-proofline">${proofParts.slice(0, 4).join(' · ') || '暂无额外学习信号'}</div>
            </div>
            <div class="candidate-price-panel">
              <div class="candidate-price-label">参考报价</div>
              ${hasAdjustment ? `
                <div class="text-muted small" style="text-decoration: line-through;">¥${marketPrice.toFixed(2)}</div>
                <div class="price-highlight text-warning">¥${adjustedPrice.toFixed(2)}</div>
              ` : `
                <div class="price-highlight">${formatNumericPrice(product.market_price)}</div>
              `}
              <div class="candidate-price-meta">成本 ${renderCostPriceText(product)}${renderCostPriceHint(product, { ambiguousLabel: '待校正', missingLabel: '未导入' })}</div>
              ${profitHtml}
            </div>
            <div class="candidate-actions">
              <span class="candidate-selection-indicator${isSelected ? '' : ' is-muted'}">${isSelected ? '当前已选' : (isBest ? '当前首选' : '点卡片切换')}</span>
              <button class="btn btn-outline-info btn-sm compare-price-btn"
                      data-product-name="${product.name || ''}"
                      data-item-index="${itemIndex}"
                      title="价格对比" onclick="event.stopPropagation();">
                <i class="bi bi-graph-up"></i>
              </button>
            </div>
          </div>
        </div>
      `;
    });

    if (!expandAll && matches.length > 3) {
      html += `
        <div class="text-center py-2">
          <span class="text-muted">还有 ${matches.length - 3} 个候选商品</span>
        </div>
      `;
    }

    return html;
  };

  renderAlternatives = function renderCompactAlternatives(alternatives, itemIndex, selectedProduct, budgetPrice = null) {
    if (!alternatives || alternatives.length === 0) {
      return '';
    }

    const displayCount = 3;
    let html = '';

    alternatives.slice(0, displayCount).forEach((alt, idx) => {
      const product = alt.product || {};
      const score = Number(alt.score || 0);
      const reason = alt.reason || '相似商品';
      const isSelected = !!(selectedProduct && selectedProduct.index === alt.index);
      const marketPrice = parseNumericPrice(product.market_price) || 0;
      const costPriceMeta = getCostPriceMeta(product);
      const costPrice = costPriceMeta.hasValue ? (parseNumericPrice(product.cost_price) || 0) : null;
      const quotePrice = budgetPrice ? (parseNumericPrice(budgetPrice) || marketPrice) : marketPrice;

      let profitHtml = '';
      if (costPrice !== null && costPrice > 0 && quotePrice > 0) {
        const profit = quotePrice - costPrice;
        const profitMargin = (profit / costPrice * 100).toFixed(1);
        const profitClass = profit >= 0 ? 'text-success' : 'text-danger';
        const profitIcon = profit >= 0 ? 'arrow-up-right' : 'arrow-down-right';
        profitHtml = `<div class="profit-info ${profitClass}"><i class="bi bi-${profitIcon}"></i>${profit >= 0 ? '利润' : '倒挂'} ¥${Math.abs(profit).toFixed(2)} (${Math.abs(Number(profitMargin)).toFixed(1)}%)</div>`;
      }

      html += `
        <div class="alternative-card ${isSelected ? 'selected' : ''}"
             data-item-index="${itemIndex}" data-alt-index="${alt.index}" data-is-alternative="true">
          <div class="alternative-layout">
            <div class="alternative-visual">
              ${ProductImageManager.createImageHtml(product, 'small')}
            </div>
            <div class="alternative-score-stack">
              <div class="alt-score">
                ${score ? Math.round(score * 100) + '%' : '<i class="bi bi-stars"></i>'}
              </div>
              <span class="alternative-rank-badge">备选 ${idx + 1}</span>
            </div>
            <div class="alternative-main">
              <div class="alternative-title">${product.name || '-'}</div>
              <div class="alternative-subtitle">
                ${product.brand ? `品牌 ${escapeHtml(product.brand)}` : '品牌待补充'}
                ${product.category ? ` · ${escapeHtml(product.category)}` : ''}
                ${product.supplier ? ` · ${escapeHtml(product.supplier)}` : ''}
              </div>
              <div class="alternative-proofline">替代建议 · ${escapeHtml(reason)}${score ? ` · 参考度 ${Math.round(score * 100)}%` : ''}</div>
            </div>
            <div class="alternative-price-panel">
              <div class="candidate-price-label">备选价格</div>
              <div class="price-highlight" style="font-size: 1rem;">${formatNumericPrice(product.market_price)}</div>
              <div class="alternative-price-meta">成本 ${renderCostPriceText(product)}${renderCostPriceHint(product, { ambiguousLabel: '待校正', missingLabel: '未导入' })}</div>
              ${profitHtml}
            </div>
            <div class="candidate-actions">
              <span class="candidate-selection-indicator${isSelected ? '' : ' is-muted'}">${isSelected ? '当前已选' : '点卡片切换'}</span>
              <button class="btn btn-outline-info btn-sm compare-price-btn"
                      data-product-name="${product.name || ''}"
                      data-item-index="${itemIndex}"
                      title="价格对比" onclick="event.stopPropagation();">
                <i class="bi bi-graph-up"></i>
              </button>
            </div>
          </div>
        </div>
      `;
    });

    if (alternatives.length > displayCount) {
      html += `
        <div class="text-center py-1">
          <small class="text-muted">还有 ${alternatives.length - displayCount} 个替代品</small>
        </div>
      `;
    }

    return html;
  };

  function renderWorkbenchCard(result, itemIndex, isActive) {
    const queryItem = result?.query_item || {};
    const matches = Array.isArray(result?.matches) ? result.matches : [];
    const alternatives = Array.isArray(result?.alternatives) ? result.alternatives : [];
    const primary = getPrimaryCandidate(result);
    const primaryProduct = primary?.product || {};
    const statusMeta = getMatchStatusMeta(result);
    const isOcrItem = queryItem.source_type === 'ocr';
    const ocrConfidence = Number(queryItem.ocr_confidence || 0);
    const showAlternatives = (matches.length === 0 || (matches[0]?.score || 0) < 0.4) && alternatives.length > 0;

    return `
      <article class="quote-item-card ${statusMeta.cardClass}${isActive ? ' is-active' : ''}" data-item-index="${itemIndex}">
        <div class="quote-item-shell-top" data-focus-workbench="true" data-item-index="${itemIndex}">
          <div class="flex-grow-1 min-w-0">
            <div class="quote-item-shell-row">
              <span class="quote-item-index">ITEM ${itemIndex + 1}</span>
              <span class="quote-item-source-pill"><i class="bi ${isOcrItem ? 'bi-camera' : 'bi-card-checklist'}"></i>${isOcrItem ? 'OCR来源' : '表格来源'}</span>
              ${primary ? `<span class="quote-item-score-pill"><i class="bi bi-bullseye"></i>${Math.round((primary.score || 0) * 100)}% 推荐度</span>` : ''}
            </div>
            <div class="quote-item-title">${escapeHtml(queryItem.name || '未命名询价项')}</div>
            <div class="quote-item-statusline">${getWorkbenchStatusLine(result)}</div>
          </div>
          <span class="status-badge ${statusMeta.badgeClass}">${statusMeta.statusText}</span>
        </div>
        <div class="quote-item-body">
          <div class="quote-item-side">
            <div class="quote-item-context">
              <div class="quote-item-meta-grid">
                <div class="quote-item-meta-card">
                  <span class="label">需求数量</span>
                  <span class="value">${escapeHtml(String(queryItem.quantity || '-'))} ${escapeHtml(queryItem.unit || '')}</span>
                </div>
                <div class="quote-item-meta-card">
                  <span class="label">预算单价</span>
                  <span class="value">${queryItem.price ? '¥' + escapeHtml(String(queryItem.price)) : '-'}</span>
                </div>
                <div class="quote-item-meta-card">
                  <span class="label">规格要求</span>
                  <span class="value">${escapeHtml(queryItem.spec || '-')}</span>
                </div>
                <div class="quote-item-meta-card">
                  <span class="label">OCR置信度</span>
                  <span class="value">${isOcrItem && ocrConfidence ? Math.round(ocrConfidence * 100) + '%' : (isOcrItem ? '待补充' : '非OCR项')}</span>
                </div>
              </div>
              <p class="mb-0 text-muted small">${escapeHtml(queryItem.remark ? (queryItem.remark.length > 120 ? queryItem.remark.substring(0, 120) + '...' : queryItem.remark) : '当前询价项暂无额外备注。')}</p>
              ${renderMatchInsights(result)}
            </div>
            ${renderRecommendationBrief(result, itemIndex)}
            ${isOcrItem ? `
              <div class="quote-reference-card mt-3">
                <div class="small fw-semibold mb-1"><i class="bi bi-eye me-1"></i>OCR识别参考</div>
                <div class="small text-muted">名称：${escapeHtml(queryItem.name || '-')}</div>
                <div class="small text-muted">规格：${escapeHtml(queryItem.spec || '-')}</div>
                <div class="small text-muted">单位/数量：${escapeHtml(queryItem.unit || '-')} / ${escapeHtml(String(queryItem.quantity || '-'))}</div>
              </div>
            ` : ''}
          </div>
          <div class="quote-item-candidates">
            <div class="quote-item-section-head">
              <div>
                <div class="quote-item-section-title">推荐候选</div>
                <div class="quote-item-section-copy">当前项共找到 <strong>${matches.length}</strong> 个候选，先处理最可能的一组。</div>
              </div>
              <span class="quote-item-section-pill">${primary ? `首选 ${Math.round((primary.score || 0) * 100)}%` : '待人工检索'}</span>
            </div>
            <div class="candidate-list" id="candidate-list-${itemIndex}">
              ${renderCandidates(matches, itemIndex, result?.selected_product, false, queryItem.price)}
            </div>
            ${showAlternatives ? `
              <div class="alternatives-section mt-2">
                <div class="alternatives-header">
                  <i class="bi bi-lightbulb text-warning me-1"></i>
                  <span>推荐替代品 (${alternatives.length}个)</span>
                  <small class="text-muted ms-2">相似商品，可作为备选</small>
                </div>
                <div class="alternatives-list" id="alternatives-list-${itemIndex}">
                  ${renderAlternatives(alternatives, itemIndex, result?.selected_product, queryItem.price)}
                </div>
              </div>
            ` : ''}
            <div class="match-actions-bar">
              <div class="match-actions-group">
                ${primary ? `<button class="btn btn-sm ${isMatchedResult(result) ? 'btn-success' : 'btn-primary'} match-confirm-btn" data-item-index="${itemIndex}" type="button"><i class="bi bi-check2-circle me-1"></i>${isMatchedResult(result) ? '重新确认当前商品' : '确认当前推荐'}</button>` : '<span class="match-actions-hint"><i class="bi bi-search me-1"></i>暂无自动推荐，请使用右侧人工搜索</span>'}
                ${primaryProduct.code ? `<button class="btn btn-sm btn-outline-secondary match-detail-btn" data-product-code="${escapeHtmlAttr(primaryProduct.code || '')}" type="button"><i class="bi bi-eye me-1"></i>商品详情</button>` : ''}
              </div>
              <div class="match-actions-group">
                ${matches.length > 3 ? `<button class="btn btn-sm btn-outline-primary toggle-candidates" data-index="${itemIndex}" data-expanded="false" type="button"><i class="bi bi-chevron-down me-1"></i>展开全部 (${matches.length}个)</button>` : '<span class="match-actions-hint"><i class="bi bi-check2-circle me-1"></i>当前候选已全部展示</span>'}
                <button class="btn btn-sm btn-outline-danger mark-no-match" data-index="${itemIndex}" type="button"><i class="bi bi-x-circle me-1"></i>无匹配</button>
                <button class="btn btn-sm btn-outline-warning mark-ask-boss" data-index="${itemIndex}" type="button"><i class="bi bi-question-circle me-1"></i>问老板</button>
              </div>
            </div>
          </div>
        </div>
      </article>
    `;
  }

  function renderWorkbenchInspector(activeEntry) {
    if (!activeEntry) {
      return `
        <aside class="match-inspector">
          <div class="match-inspector-empty match-stream-empty">当前筛选下没有可查看的报价项。</div>
        </aside>
      `;
    }

    const { result, itemIndex } = activeEntry;
    const queryItem = result?.query_item || {};
    const primary = getPrimaryCandidate(result);
    const product = primary?.product || {};
    const marketPrice = parseNumericPrice(product.market_price) || 0;
    const adjustedPrice = getAdjustedPrice(marketPrice, itemIndex) || marketPrice;
    const costMeta = getCostPriceMeta(product);
    const costPrice = costMeta.hasValue ? (parseNumericPrice(product.cost_price) || 0) : null;
    const budgetPrice = parseNumericPrice(queryItem.price) || adjustedPrice || marketPrice;
    let marginText = '待补充';
    let marginClass = '';

    if (costPrice && budgetPrice) {
      const margin = budgetPrice - costPrice;
      const marginRate = costPrice ? ((margin / costPrice) * 100).toFixed(1) : '0.0';
      marginText = `${margin >= 0 ? '+' : ''}¥${margin.toFixed(2)} (${marginRate}%)`;
      marginClass = margin >= 0 ? 'text-success' : 'text-danger';
    }

    const optionItems = [
      ...((result?.matches || []).slice(0, 2).map(match => ({
        type: 'match',
        label: '候选',
        candidate: match
      }))),
      ...((result?.alternatives || []).slice(0, 1).map(match => ({
        type: 'alt',
        label: '备选',
        candidate: match
      })))
    ];

    return `
      <aside class="match-inspector">
        <div class="match-inspector-card">
          <div class="match-inspector-heading">当前焦点</div>
          <div class="match-inspector-copy">右侧固定保留商业信息、人工搜索与快捷确认，不再来回弹窗。</div>
          <div class="match-inspector-media">
            <div class="candidate-visual">
              ${ProductImageManager.createImageHtml(product, 'small')}
            </div>
            <div>
              <div class="fw-semibold match-inspector-media-title">${escapeHtml(product.name || queryItem.name || '未命名商品')}</div>
              <div class="small text-muted mt-1">ITEM ${itemIndex + 1} · ${escapeHtml(queryItem.name || '未命名询价项')}</div>
              <div class="small text-muted">${escapeHtml(product.supplier || '供应商待补充')} ${product.code ? '· 编码 ' + escapeHtml(product.code) : ''}</div>
            </div>
          </div>
          <div class="match-inspector-metrics">
            <div class="match-inspector-metric">
              <span class="match-inspector-metric-label">推荐度</span>
              <span class="match-inspector-metric-value">${primary ? Math.round((primary.score || 0) * 100) + '%' : '暂无'}</span>
            </div>
            <div class="match-inspector-metric">
              <span class="match-inspector-metric-label">当前状态</span>
              <span class="match-inspector-metric-value">${getMatchStatusMeta(result).statusText}</span>
            </div>
            <div class="match-inspector-metric">
              <span class="match-inspector-metric-label">市场价</span>
              <span class="match-inspector-metric-value">${adjustedPrice > 0 ? '¥' + adjustedPrice.toFixed(2) : '待补充'}</span>
            </div>
            <div class="match-inspector-metric">
              <span class="match-inspector-metric-label">成本价</span>
              <span class="match-inspector-metric-value">${renderCostPriceText(product)}</span>
            </div>
            <div class="match-inspector-metric">
              <span class="match-inspector-metric-label">预算单价</span>
              <span class="match-inspector-metric-value">${queryItem.price ? '¥' + escapeHtml(String(queryItem.price)) : '未填写'}</span>
            </div>
            <div class="match-inspector-metric">
              <span class="match-inspector-metric-label">利润空间</span>
              <span class="match-inspector-metric-value ${marginClass}">${marginText}</span>
            </div>
          </div>

          <div class="match-inspector-section">
            <div class="match-inspector-section-title">商品与来源</div>
            <ul class="match-inspector-option-list">
              <li class="match-inspector-option">
                <strong>${escapeHtml(product.brand || '品牌待补充')} ${product.model ? '· ' + escapeHtml(product.model) : ''}</strong>
                <span>分类 ${escapeHtml(product.category || '待补充')} · 单位 ${escapeHtml(product.unit || queryItem.unit || '-')}</span>
              </li>
              <li class="match-inspector-option">
                <strong>询价规格与备注</strong>
                <span>${escapeHtml(queryItem.spec || '未提供规格')} ${queryItem.remark ? '· ' + escapeHtml(queryItem.remark) : ''}</span>
              </li>
              ${costMeta.hasValue || costMeta.missing || costMeta.ambiguous ? `
                <li class="match-inspector-option">
                  <strong>成本信息提醒</strong>
                  <span>${renderCostPriceHint(product, { ambiguousLabel: '历史数据待校正', missingLabel: '未导入' }) || '成本信息正常'}</span>
                </li>
              ` : ''}
            </ul>
          </div>

          <div class="match-inspector-section">
            <div class="match-inspector-section-title">候选摘要</div>
            <ul class="match-inspector-option-list">
              ${optionItems.length ? optionItems.map(option => {
                const candidate = option.candidate;
                const candidateProduct = candidate?.product || {};
                return `
                  <li class="match-inspector-option">
                    <strong>${option.label} · ${escapeHtml(candidateProduct.name || '未命名商品')}</strong>
                    <span>${escapeHtml(candidateProduct.supplier || '供应商待补充')} · 推荐度 ${candidate?.score ? Math.round(candidate.score * 100) + '%' : '人工检索'} ${candidate.learning_reason ? '· ' + escapeHtml(candidate.learning_reason) : ''}</span>
                    <div class="match-inspector-option-actions">
                      <button class="btn btn-sm btn-outline-primary match-inspector-pick" type="button" data-item-index="${itemIndex}" data-source-type="${option.type}" data-source-index="${candidate.index}"><i class="bi bi-check2 me-1"></i>切换到这个</button>
                      ${candidateProduct.code ? `<button class="btn btn-sm btn-outline-secondary match-detail-btn" type="button" data-product-code="${escapeHtmlAttr(candidateProduct.code || '')}"><i class="bi bi-eye me-1"></i>详情</button>` : ''}
                    </div>
                  </li>
                `;
              }).join('') : '<li class="match-inspector-option"><strong>暂无候选摘要</strong><span>请通过下方人工搜索补齐。</span></li>'}
            </ul>
          </div>

          <div class="match-inspector-section">
            <div class="match-inspector-section-title">人工审核搜索</div>
            ${renderQuoteCatalogSearchPanel(queryItem, itemIndex)}
            <div class="match-inspector-inline-note">人工搜索结果会直接回写到当前报价项。</div>
          </div>

          <div class="match-inspector-actions">
            <button class="btn btn-primary match-confirm-btn" type="button" data-item-index="${itemIndex}"><i class="bi bi-check2-circle me-1"></i>${isMatchedResult(result) ? '重新确认' : '确认当前推荐'}</button>
            <button class="btn btn-outline-secondary" type="button" onclick="showExportOptionsForCurrentMatch()"><i class="bi bi-box-arrow-up-right me-1"></i>去导出</button>
            <button class="btn btn-outline-danger mark-no-match" type="button" data-index="${itemIndex}"><i class="bi bi-x-circle me-1"></i>无匹配</button>
            <button class="btn btn-outline-warning mark-ask-boss" type="button" data-index="${itemIndex}"><i class="bi bi-question-circle me-1"></i>问老板</button>
          </div>
        </div>
      </aside>
    `;
  }

  function renderWorkbenchStream(visibleItems, filters, activeEntry) {
    if (!visibleItems.length) {
      return `
        <section class="match-stream">
          <div class="match-stream-header">
            <div class="match-stream-heading">结果流为空</div>
            <div class="match-stream-subtitle">当前搜索、状态或排序条件下没有命中项，重置筛选后再继续。</div>
          </div>
          <div class="match-inspector-empty match-stream-empty">
            <div>
              <div class="fw-semibold mb-2">没有找到匹配结果</div>
              <div class="small">请尝试放宽搜索词或点击重置筛选。</div>
            </div>
          </div>
        </section>
      `;
    }

    const sectionInfo = getActiveSectionInfo(visibleItems, filters, activeEntry);
    const activePosition = visibleItems.findIndex(item => item.itemIndex === activeEntry.itemIndex);
    const previousEntry = activePosition > 0 ? visibleItems[activePosition - 1] : null;
    const nextEntry = activePosition < visibleItems.length - 1 ? visibleItems[activePosition + 1] : null;
    const jumpItems = getPriorityQueueItems(visibleItems, 4).filter(item => item.itemIndex !== activeEntry.itemIndex).slice(0, 3);

    return `
      <section class="match-stream">
        <div class="match-stream-header">
          <div class="match-stream-heading">单焦点决策流</div>
          <div class="match-stream-subtitle">中区只展开当前焦点项：左侧排队，右侧核查，这里只做一个决策单元。</div>
        </div>
        <div class="match-stream-section-overview">
          <span class="match-stream-section-pill is-${sectionInfo.key}">${sectionInfo.title}</span>
          <span class="match-stream-section-pill">当前位置 ${Math.max(sectionInfo.position || 1, 1)} / ${visibleItems.length}</span>
          <span class="match-stream-section-pill">同段 ${sectionInfo.count || 0} 项</span>
        </div>
        <div class="match-stream-nav">
          ${previousEntry ? `<button class="match-stream-jump" type="button" data-item-index="${previousEntry.itemIndex}"><i class="bi bi-arrow-left"></i>上一项</button>` : ''}
          ${nextEntry ? `<button class="match-stream-jump" type="button" data-item-index="${nextEntry.itemIndex}">下一项<i class="bi bi-arrow-right"></i></button>` : ''}
          ${jumpItems.map(entry => `<button class="match-stream-jump is-priority" type="button" data-item-index="${entry.itemIndex}">跳至 ITEM ${entry.itemIndex + 1}</button>`).join('')}
        </div>
        <div class="match-stream-section" data-section-key="${sectionInfo.key}">
          <div class="match-stream-section-header">
            <div>
              <div class="match-stream-section-title">ITEM ${activeEntry.itemIndex + 1} · ${escapeHtml(activeEntry.result?.query_item?.name || '未命名询价项')}</div>
              <div class="match-stream-section-meta">${sectionInfo.subtitle}</div>
            </div>
            <div class="match-stream-section-meta">${getMatchStatusMeta(activeEntry.result).statusText}</div>
          </div>
          <div class="match-stream-list">
            ${renderWorkbenchCard(activeEntry.result, activeEntry.itemIndex, true)}
          </div>
        </div>
      </section>
    `;
  }

  function rebindWorkbenchFilterEvents() {
    const bind = (element, eventName, handler) => {
      if (!element) return;
      element[`on${eventName}`] = handler;
    };

    bind(document.getElementById('searchInput'), 'input', () => filterResults());
    bind(document.getElementById('clearSearchBtn'), 'click', () => {
      document.getElementById('searchInput').value = '';
      filterResults();
    });
    bind(document.getElementById('statusFilter'), 'change', function() {
      currentStatsFilter = this.value;
      updateStatsCardHighlight();
      filterResults();
    });
    bind(document.getElementById('sortFilter'), 'change', () => filterResults());
    bind(document.getElementById('resetFilterBtn'), 'click', () => {
      document.getElementById('searchInput').value = '';
      document.getElementById('statusFilter').value = 'all';
      document.getElementById('sortFilter').value = 'default';
      currentStatsFilter = 'all';
      updateStatsCardHighlight();
      renderMatchResults(true);
    });
  }

  renderMatchResults = function renderWorkbenchResults(skipAutoMatch = false) {
    refreshQuotesPreludeCopy();
    updateExportTemplateBrowseContext();
    const container = document.getElementById('matchResults');

    if (!container) {
      return;
    }

    if (!Array.isArray(matchResults) || matchResults.length === 0) {
      setQuotesWorkbenchState('empty');
      container.innerHTML = renderQuotesLandingEmpty();
      updateStats();
      return;
    }

    if (!skipAutoMatch) {
      autoMatchHighScore();
    }

    const { filters, visibleItems } = getVisibleMatchItems();
    const activeEntry = ensureActiveWorkbenchItem(visibleItems);

    if (!visibleItems.length) {
      setQuotesWorkbenchState('filtered-empty');
      container.innerHTML = renderQuotesFilteredEmpty();
      updateStats();
      rebindWorkbenchFilterEvents();
      return;
    }

    setQuotesWorkbenchState('ready');

    container.innerHTML = `
      ${renderWorkbenchSummary()}
      <div class="match-workbench-shell">
        ${renderWorkbenchRail(visibleItems, filters, activeEntry)}
        ${renderWorkbenchStream(visibleItems, filters, activeEntry)}
        ${renderWorkbenchInspector(activeEntry)}
      </div>
    `;

    updateStats();
    initCandidateActions();
    rebindWorkbenchFilterEvents();
  };

  renderMatchResultsInternal = function renderMatchResultsInternalOverride() {
    renderMatchResults(true);
  };

  filterResults = function filterWorkbenchResults() {
    renderMatchResults(true);
  };

  initCandidateActions = function initWorkbenchCandidateActions() {
    document.querySelectorAll('.product-card').forEach(card => {
      card.onclick = function() {
        const itemIndex = parseInt(this.dataset.itemIndex, 10);
        const matchIndex = parseInt(this.dataset.matchIndex, 10);
        activeWorkbenchIndex = itemIndex;
        workbenchUserPinnedFocus = true;
        const match = matchResults[itemIndex]?.matches?.find(item => item.index === matchIndex);
        if (match) {
          selectProduct(itemIndex, match);
        }
      };
    });

    document.querySelectorAll('.alternative-card').forEach(card => {
      card.onclick = function() {
        const itemIndex = parseInt(this.dataset.itemIndex, 10);
        const altIndex = parseInt(this.dataset.altIndex, 10);
        activeWorkbenchIndex = itemIndex;
        workbenchUserPinnedFocus = true;
        const alt = matchResults[itemIndex]?.alternatives?.find(item => item.index === altIndex);
        if (alt) {
          selectProduct(itemIndex, alt);
        }
      };
    });

    document.querySelectorAll('.toggle-candidates').forEach(btn => {
      btn.onclick = function(e) {
        e.stopPropagation();
        const itemIndex = parseInt(this.dataset.index, 10);
        activeWorkbenchIndex = itemIndex;
        workbenchUserPinnedFocus = true;
        toggleCandidates(itemIndex);
      };
    });

    document.querySelectorAll('.mark-no-match').forEach(btn => {
      btn.onclick = function(e) {
        e.stopPropagation();
        const itemIndex = parseInt(this.dataset.index, 10);
        activeWorkbenchIndex = itemIndex;
        workbenchUserPinnedFocus = true;
        markNoMatch(itemIndex);
      };
    });

    document.querySelectorAll('.mark-ask-boss').forEach(btn => {
      btn.onclick = function(e) {
        e.stopPropagation();
        const itemIndex = parseInt(this.dataset.index, 10);
        activeWorkbenchIndex = itemIndex;
        workbenchUserPinnedFocus = true;
        markAskBoss(itemIndex);
      };
    });

    document.querySelectorAll('.compare-price-btn').forEach(btn => {
      btn.onclick = function(e) {
        e.stopPropagation();
        const productName = this.dataset.productName;
        const itemIndex = parseInt(this.dataset.itemIndex, 10);
        activeWorkbenchIndex = itemIndex;
        workbenchUserPinnedFocus = true;
        showPriceCompare(productName, itemIndex);
      };
    });

    document.querySelectorAll('.quote-catalog-search-btn').forEach(btn => {
      btn.onclick = function(e) {
        e.stopPropagation();
        const itemIndex = parseInt(this.dataset.itemIndex, 10);
        activeWorkbenchIndex = itemIndex;
        workbenchUserPinnedFocus = true;
        searchCatalogForQuoteItem(itemIndex);
      };
    });

    document.querySelectorAll('.quote-catalog-keyword').forEach(input => {
      input.onkeydown = function(e) {
        if (e.key !== 'Enter') return;
        e.preventDefault();
        e.stopPropagation();
        const itemIndex = parseInt(this.dataset.itemIndex, 10);
        activeWorkbenchIndex = itemIndex;
        workbenchUserPinnedFocus = true;
        searchCatalogForQuoteItem(itemIndex, this.value);
      };
    });

    document.querySelectorAll('.quote-catalog-detail-btn, .match-detail-btn').forEach(btn => {
      btn.onclick = function(e) {
        e.stopPropagation();
        showCatalogProductDetail(this.dataset.productCode || '');
      };
    });

    document.querySelectorAll('.quote-catalog-use-btn').forEach(btn => {
      btn.onclick = function(e) {
        e.stopPropagation();
        const itemIndex = parseInt(this.dataset.itemIndex, 10);
        activeWorkbenchIndex = itemIndex;
        workbenchUserPinnedFocus = true;
        const encodedMatch = this.dataset.manualMatch || '';
        try {
          const match = JSON.parse(decodeURIComponent(encodedMatch));
          selectProduct(itemIndex, match);
        } catch (error) {
          showToast('error', '人工选择数据解析失败');
        }
      };
    });

    document.querySelectorAll('.match-confirm-btn').forEach(btn => {
      btn.onclick = function(e) {
        e.stopPropagation();
        const itemIndex = parseInt(this.dataset.itemIndex, 10);
        activeWorkbenchIndex = itemIndex;
        workbenchUserPinnedFocus = true;
        confirmWorkbenchSelection(itemIndex);
      };
    });

    document.querySelectorAll('.match-rail-focus-btn, .quote-item-shell-top[data-focus-workbench]').forEach(btn => {
      btn.onclick = function(e) {
        e.stopPropagation();
        const itemIndex = parseInt(this.dataset.itemIndex, 10);
        focusWorkbenchItem(itemIndex, true);
      };
    });

    document.querySelectorAll('.match-inspector-pick').forEach(btn => {
      btn.onclick = function(e) {
        e.stopPropagation();
        const itemIndex = parseInt(this.dataset.itemIndex, 10);
        const sourceType = this.dataset.sourceType;
        const sourceIndex = parseInt(this.dataset.sourceIndex, 10);
        activeWorkbenchIndex = itemIndex;
        workbenchUserPinnedFocus = true;

        const sourceList = sourceType === 'alt'
          ? (matchResults[itemIndex]?.alternatives || [])
          : (matchResults[itemIndex]?.matches || []);
        const candidate = sourceList.find(item => item.index === sourceIndex);
        if (candidate) {
          selectProduct(itemIndex, candidate);
        }
      };
    });

    document.querySelectorAll('.match-stream-jump').forEach(btn => {
      btn.onclick = function(e) {
        e.stopPropagation();
        const itemIndex = parseInt(this.dataset.itemIndex, 10);
        if (Number.isFinite(itemIndex)) {
          focusWorkbenchItem(itemIndex, true);
        }
      };
    });
  };

  selectProduct = function selectProductOverride(itemIndex, match) {
    activeWorkbenchIndex = itemIndex;
    workbenchUserPinnedFocus = true;
    return originalSelectProduct(itemIndex, match);
  };

  markNoMatch = function markNoMatchOverride(itemIndex) {
    activeWorkbenchIndex = itemIndex;
    workbenchUserPinnedFocus = true;
    return originalMarkNoMatch(itemIndex);
  };

  markAskBoss = function markAskBossOverride(itemIndex) {
    activeWorkbenchIndex = itemIndex;
    workbenchUserPinnedFocus = true;
    return originalMarkAskBoss(itemIndex);
  };

  window.addEventListener('load', () => {
    refreshQuotesPreludeCopy();
    rebindWorkbenchFilterEvents();
  }, { once: true });

  function refreshQuotesPreludeCopy() {
    if (document.body?.dataset?.route !== 'quotes') return;
    const filterBar = document.querySelector('#matchTab .quote-filter-bar');
    if (!filterBar) return;
    const heading = filterBar.querySelector('.match-toolbar-heading');
    const subtitle = filterBar.querySelector('.match-toolbar-subtitle');
    if (heading) heading.textContent = '筛选器';
    if (subtitle) subtitle.textContent = '先筛掉噪音，再进入人工确认。把最影响判断的字段放到第一排，减少视觉干扰。';
  }

  function renderQuotesLandingEmpty() {
    return `
      <div class="workspace-empty-orbit workspace-empty-orbit--quotes workspace-empty-orbit--quotes-landing">
        <div class="quote-empty-layout">
          <div class="quote-empty-primary">
            <div class="workspace-empty-orbit-visual">
              <i class="bi bi-layout-text-window"></i>
            </div>
            <div class="workspace-empty-orbit-title">这里还没有待确认的报价结果</div>
            <div class="workspace-empty-orbit-copy">上传 Excel 报价单或 OCR 图片后，这里会切换成待处理队列、当前报价项和候选核对区。整个流程尽量不再要求你来回切页。</div>
            <div class="workspace-empty-orbit-pills">
              <span class="workspace-empty-orbit-pill">本页直接上传</span>
              <span class="workspace-empty-orbit-pill">统一确认</span>
              <span class="workspace-empty-orbit-pill">确认后再导出</span>
            </div>
            <div class="quote-empty-primary-note">
              <strong>当前建议</strong>
              <span>先把报价来源推进来，再处理候选与异常，最后再去模板中心做交付选择。</span>
            </div>
          </div>
          <div class="quote-empty-card quote-empty-stage">
            <span class="quote-empty-card-kicker">Direct Upload</span>
            <strong class="quote-empty-card-title">就在报价页开始，不再返回首页找入口</strong>
            <span class="quote-empty-card-copy">这页本身就是报价确认台。选中文件之后，系统会立即进入解析和待确认流程，避免旧界面那种多层跳转。</span>
            <div class="quote-empty-actions">
              <button class="btn btn-primary" type="button" onclick="WorkspaceEntryActions.openQuoteUpload()">
                <i class="bi bi-file-earmark-arrow-up me-2"></i>上传报价单
              </button>
              <button class="btn btn-outline-info" type="button" data-ocr-entry="true" onclick="WorkspaceEntryActions.openOCRUpload()">
                <i class="bi bi-camera me-2"></i>OCR 图片
              </button>
            </div>
            <div class="quote-empty-helper">支持 \`.xls\` / \`.xlsx\` 和图片报价单，进入后统一做人工收口。</div>
          </div>
          <div class="quote-empty-shortcuts">
            <a href="/catalog" class="quote-empty-shortcut-card">
              <span class="quote-empty-card-kicker">Catalog</span>
              <strong class="quote-empty-card-title">先补商品库</strong>
              <span class="quote-empty-card-copy">品牌、规格、供应商和图片越完整，自动匹配越稳，候选也更像人会选的结果。</span>
            </a>
            <a href="/templates" class="quote-empty-shortcut-card">
              <span class="quote-empty-card-kicker">Templates</span>
              <strong class="quote-empty-card-title">模板中心</strong>
              <span class="quote-empty-card-copy">确认完成后再去模板页选交付方式，把“确认”和“导出”明确拆开。</span>
            </a>
            <a href="/guide" class="quote-empty-shortcut-card">
              <span class="quote-empty-card-kicker">Guide</span>
              <strong class="quote-empty-card-title">上手说明</strong>
              <span class="quote-empty-card-copy">给同事看的短说明会放在这里，帮助快速理解字段、流程和模板差异。</span>
            </a>
          </div>
        </div>
      </div>
    `;
  }

  function getWorkbenchStatusLine(result) {
    const matchesCount = Array.isArray(result?.matches) ? result.matches.length : 0;
    if (result?.confirmed && result?.action === 'select') return '已确认，可进入导出。';
    if (!result?.confirmed && result?.action === 'select' && result?.selected_product) return '系统已预选，等待人工确认。';
    if (result?.action === 'no_match') return '当前标记为无匹配，请人工检索或补充商品库。';
    if (result?.action === 'ask_boss') return '当前需问老板，请补充说明或备选。';
    if (matchesCount > 0) return '已有候选商品，优先核对首选。';
    return '暂无自动候选，建议人工搜索。';
  }

  function getActiveSectionInfo(visibleItems, filters, activeEntry) {
    if (!activeEntry) {
      return { key: 'empty', title: '暂无数据', subtitle: '调整筛选条件后继续。', count: 0, position: 0 };
    }

    const activeResult = activeEntry.result;
    const activePosition = visibleItems.findIndex(item => item.itemIndex === activeEntry.itemIndex);

    if (filters.rawSearchText || filters.statusFilter !== 'all' || filters.sortFilter !== 'default') {
      return {
        key: 'filtered',
        title: '筛选结果',
        subtitle: filters.rawSearchText ? `关键词：${filters.rawSearchText}` : '当前按筛选条件显示。',
        count: visibleItems.length,
        position: activePosition + 1
      };
    }

    if (activeResult?.confirmed && isIssueResult(activeResult)) {
      return {
        key: 'issue',
        title: '异常项',
        subtitle: '优先处理异常或升级项。',
        count: visibleItems.filter(({ result }) => !!(result?.confirmed && isIssueResult(result))).length,
        position: activePosition + 1
      };
    }

    if (isMatchedResult(activeResult)) {
      return {
        key: 'matched',
        title: '已确认',
        subtitle: '当前项已确认，可直接复核。',
        count: visibleItems.filter(({ result }) => isMatchedResult(result)).length,
        position: activePosition + 1
      };
    }

    return {
      key: 'pending',
      title: '待确认',
      subtitle: '先确认当前项，再切换下一项。',
      count: visibleItems.filter(({ result }) => isPendingResult(result)).length,
      position: activePosition + 1
    };
  }

  function renderWorkbenchSummary() {
    return '';
  }

  function renderWorkbenchRail(visibleItems, filters, activeEntry) {
    const matchedCount = matchResults.filter(result => isMatchedResult(result)).length;
    const pendingCount = matchResults.filter(result => isPendingResult(result)).length;
    const issueCount = matchResults.filter(result => !!(result?.confirmed && isIssueResult(result))).length;
    const ocrCount = matchResults.filter(result => result?.query_item?.source_type === 'ocr').length;
    const queueItems = getPriorityQueueItems(visibleItems, 8);
    const filterLabels = getWorkbenchFilterLabels(filters);
    const queueTip = issueCount > 0
      ? `先处理 ${issueCount} 个异常项。`
      : (pendingCount > 0 ? `还有 ${pendingCount} 个待确认项。` : '当前可检查导出。');

    return `
      <aside class="match-rail">
        <div class="match-rail-card match-rail-card--pulse">
          <div class="match-rail-heading">处理队列</div>
          <div class="match-rail-copy">左侧只负责排队和跳转，不占用主工作区。</div>
          <div class="match-rail-stat-grid">
            <div class="match-rail-stat"><strong>${matchResults.length}</strong><span>报价项</span></div>
            <div class="match-rail-stat"><strong>${matchedCount}</strong><span>已确认</span></div>
            <div class="match-rail-stat"><strong>${pendingCount}</strong><span>待确认</span></div>
            <div class="match-rail-stat"><strong>${ocrCount}</strong><span>OCR</span></div>
          </div>
          <div class="match-rail-focus-note">${queueTip}</div>
        </div>
        <div class="match-rail-card match-rail-card--queue">
          <div class="match-rail-heading">待处理项</div>
          <div class="match-rail-inline-pills">
            <span class="match-rail-inline-pill">状态 · ${filterLabels.statusLabel}</span>
            <span class="match-rail-inline-pill">排序 · ${filterLabels.sortLabel}</span>
            ${filters.rawSearchText ? `<span class="match-rail-inline-pill">搜索 · ${escapeHtml(filters.rawSearchText)}</span>` : ''}
          </div>
          <ul class="match-rail-list mt-3">
            ${queueItems.length ? queueItems.map(({ result, itemIndex }) => {
              const primary = getPrimaryCandidate(result);
              const statusMeta = getMatchStatusMeta(result);
              const queueNote = primary
                ? `${statusMeta.statusText} · ${Math.round((primary.score || 0) * 100)}% · ${escapeHtml(primary.product?.name || '未命名商品')}`
                : `${statusMeta.statusText} · 暂无候选商品`;
              const itemClasses = [
                itemIndex === activeWorkbenchIndex ? 'is-active' : '',
                (!result?.confirmed || isIssueResult(result)) ? 'is-warning' : ''
              ].filter(Boolean).join(' ');

              return `
                <li class="${itemClasses}">
                  <button class="match-rail-focus-btn" type="button" data-item-index="${itemIndex}">
                    <strong>ITEM ${itemIndex + 1} · ${escapeHtml(result?.query_item?.name || '未命名询价项')}</strong>
                    <span>${queueNote}</span>
                  </button>
                </li>
              `;
            }).join('') : '<li><strong>没有可处理项</strong><span>请调整筛选条件。</span></li>'}
          </ul>
          ${activeEntry ? `<div class="match-rail-focus-note mt-2">当前：ITEM ${activeEntry.itemIndex + 1} · ${escapeHtml(activeEntry.result?.query_item?.name || '未命名询价项')}</div>` : ''}
        </div>
      </aside>
    `;
  }

  function renderWorkbenchStream(visibleItems, filters, activeEntry) {
    if (!visibleItems.length) {
      return `
        <section class="match-stream">
          <div class="match-stream-header">
            <div class="match-stream-heading">没有命中结果</div>
            <div class="match-stream-subtitle">请放宽搜索词或点击重置筛选。</div>
          </div>
          <div class="match-inspector-empty match-stream-empty">
            <div>
              <div class="fw-semibold mb-2">当前没有可处理项</div>
              <div class="small">调整筛选后再继续。</div>
            </div>
          </div>
        </section>
      `;
    }

    const sectionInfo = getActiveSectionInfo(visibleItems, filters, activeEntry);
    const activePosition = visibleItems.findIndex(item => item.itemIndex === activeEntry.itemIndex);
    const previousEntry = activePosition > 0 ? visibleItems[activePosition - 1] : null;
    const nextEntry = activePosition < visibleItems.length - 1 ? visibleItems[activePosition + 1] : null;
    const jumpItems = getPriorityQueueItems(visibleItems, 4).filter(item => item.itemIndex !== activeEntry.itemIndex).slice(0, 3);

    return `
      <section class="match-stream">
        <div class="match-stream-header">
          <div class="match-stream-heading">当前报价项</div>
          <div class="match-stream-subtitle">中间只展开当前项，避免在长列表里来回滚动。</div>
        </div>
        <div class="match-stream-section-overview">
          <span class="match-stream-section-pill is-${sectionInfo.key}">${sectionInfo.title}</span>
          <span class="match-stream-section-pill">位置 ${Math.max(sectionInfo.position || 1, 1)} / ${visibleItems.length}</span>
          <span class="match-stream-section-pill">同组 ${sectionInfo.count || 0} 项</span>
        </div>
        <div class="match-stream-nav">
          ${previousEntry ? `<button class="match-stream-jump" type="button" data-item-index="${previousEntry.itemIndex}"><i class="bi bi-arrow-left"></i>上一项</button>` : ''}
          ${nextEntry ? `<button class="match-stream-jump" type="button" data-item-index="${nextEntry.itemIndex}">下一项<i class="bi bi-arrow-right"></i></button>` : ''}
          ${jumpItems.map(entry => `<button class="match-stream-jump is-priority" type="button" data-item-index="${entry.itemIndex}">跳至 ITEM ${entry.itemIndex + 1}</button>`).join('')}
        </div>
        <div class="match-stream-section" data-section-key="${sectionInfo.key}">
          <div class="match-stream-section-header">
            <div>
              <div class="match-stream-section-title">ITEM ${activeEntry.itemIndex + 1} · ${escapeHtml(activeEntry.result?.query_item?.name || '未命名询价项')}</div>
              <div class="match-stream-section-meta">${escapeHtml(sectionInfo.subtitle || '')}</div>
            </div>
          </div>
          <ul class="match-stream-list">
            ${renderWorkbenchCard(activeEntry.result, activeEntry.itemIndex, true)}
          </ul>
        </div>
      </section>
    `;
  }

  function renderWorkbenchInspector(activeEntry) {
    if (!activeEntry) {
      return `
        <aside class="match-inspector">
          <div class="match-inspector-empty match-stream-empty">当前筛选下没有可核查的报价项。</div>
        </aside>
      `;
    }

    const { result, itemIndex } = activeEntry;
    const queryItem = result?.query_item || {};
    const primary = getPrimaryCandidate(result);
    const product = primary?.product || {};
    const marketPrice = parseNumericPrice(product.market_price) || 0;
    const adjustedPrice = getAdjustedPrice(marketPrice, itemIndex) || marketPrice;
    const costMeta = getCostPriceMeta(product);
    const costPrice = costMeta.hasValue ? (parseNumericPrice(product.cost_price) || 0) : null;
    const budgetPrice = parseNumericPrice(queryItem.price) || adjustedPrice || marketPrice;
    let marginText = '待补充';
    let marginClass = '';

    if (costPrice && budgetPrice) {
      const margin = budgetPrice - costPrice;
      const marginRate = costPrice ? ((margin / costPrice) * 100).toFixed(1) : '0.0';
      marginText = `${margin >= 0 ? '+' : ''}¥${margin.toFixed(2)} (${marginRate}%)`;
      marginClass = margin >= 0 ? 'text-success' : 'text-danger';
    }

    const optionItems = [
      ...((result?.matches || []).slice(0, 2).map(match => ({ type: 'match', label: '候选', candidate: match }))),
      ...((result?.alternatives || []).slice(0, 1).map(match => ({ type: 'alt', label: '备选', candidate: match })))
    ];

    return `
      <aside class="match-inspector">
        <div class="match-inspector-card">
          <div class="match-inspector-heading">核查面板</div>
          <div class="match-inspector-copy">价格、候选商品、人工搜索和确认动作都在这里。</div>
          <div class="match-inspector-media">
            <div class="candidate-visual">
              ${ProductImageManager.createImageHtml(product, 'small')}
            </div>
            <div>
              <div class="fw-semibold match-inspector-media-title">${escapeHtml(product.name || queryItem.name || '未命名商品')}</div>
              <div class="small text-muted mt-1">ITEM ${itemIndex + 1} · ${escapeHtml(queryItem.name || '未命名询价项')}</div>
              <div class="small text-muted">${escapeHtml(product.supplier || '供应商待补充')} ${product.code ? '· 编码 ' + escapeHtml(product.code) : ''}</div>
            </div>
          </div>
          <div class="match-inspector-metrics">
            <div class="match-inspector-metric">
              <span class="match-inspector-metric-label">当前状态</span>
              <span class="match-inspector-metric-value">${escapeHtml(getMatchStatusMeta(result).statusText)}</span>
            </div>
            <div class="match-inspector-metric">
              <span class="match-inspector-metric-label">候选数量</span>
              <span class="match-inspector-metric-value">${escapeHtml(String((result?.matches || []).length))}</span>
            </div>
            <div class="match-inspector-metric">
              <span class="match-inspector-metric-label">预算单价</span>
              <span class="match-inspector-metric-value">${formatNumericPrice(queryItem.price)}</span>
            </div>
            <div class="match-inspector-metric">
              <span class="match-inspector-metric-label">利润 / 倒挂</span>
              <span class="match-inspector-metric-value ${marginClass}">${marginText}</span>
            </div>
          </div>
          <div class="match-inspector-section">
            <div class="match-inspector-section-title">当前建议</div>
            <ul class="match-inspector-option-list">
              ${primary ? `
                <li class="match-inspector-option">
                  <strong>${escapeHtml(product.name || '未命名商品')}</strong>
                  <span>${escapeHtml(product.brand || '品牌待补充')} · ${escapeHtml(product.supplier || '供应商待补充')}</span>
                  <span>建议售价 ${formatPriceOrDash(product.market_price)}</span>
                </li>
              ` : '<li class="match-inspector-option"><strong>暂无稳定候选</strong><span>请使用下方人工搜索。</span></li>'}
            </ul>
          </div>
          <div class="match-inspector-section">
            <div class="match-inspector-section-title">候选与备选</div>
            <ul class="match-inspector-option-list">
              ${optionItems.length ? optionItems.map(({ label, candidate }) => `
                <li class="match-inspector-option">
                  <strong>${escapeHtml(label)} · ${escapeHtml(candidate?.product?.name || '未命名商品')}</strong>
                  <span>${escapeHtml(candidate?.product?.supplier || '供应商待补充')} · ${Math.round((Number(candidate?.score || 0) || 0) * 100)}%</span>
                </li>
              `).join('') : '<li class="match-inspector-option"><strong>暂无候选</strong><span>请人工搜索或补充商品库。</span></li>'}
            </ul>
          </div>
          <div class="match-inspector-section">
            <div class="match-inspector-section-title">人工补充</div>
            <ul class="match-inspector-option-list">
              <li class="match-inspector-option">
                <strong>预算单价</strong>
                <span>${formatNumericPrice(queryItem.price)}</span>
              </li>
              <li class="match-inspector-option">
                <strong>当前说明</strong>
                <span>${escapeHtml(queryItem.spec || queryItem.remark || '暂无补充说明')}</span>
              </li>
            </ul>
          </div>
          <div class="match-inspector-actions">
            <button class="btn btn-primary btn-sm" type="button" onclick="confirmWorkbenchSelection(${itemIndex})"><i class="bi bi-check2-circle me-1"></i>确认当前建议</button>
            <button class="btn btn-outline-secondary btn-sm quote-catalog-search-btn" type="button" data-item-index="${itemIndex}"><i class="bi bi-search me-1"></i>人工搜索</button>
            <button class="btn btn-outline-secondary btn-sm mark-no-match" type="button" data-index="${itemIndex}"><i class="bi bi-x-circle me-1"></i>无匹配</button>
            <button class="btn btn-outline-secondary btn-sm mark-ask-boss" type="button" data-index="${itemIndex}"><i class="bi bi-question-circle me-1"></i>问老板</button>
          </div>
        </div>
      </aside>
    `;
  }
})();
