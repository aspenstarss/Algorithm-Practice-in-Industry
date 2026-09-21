// 分级折叠与核心/沾边双列表切换交互（由 generate_arxiv_html 拆出）
document.addEventListener('DOMContentLoaded', function() {
    // 双列表（核心榜单 + 沾边速览）各自初始化展开/折叠控件
    document.querySelectorAll('.paper-list').forEach(function(papersContainer) {
        // 添加展开/折叠全部按钮
        const expandAllButton = document.createElement('div');
        expandAllButton.className = 'expand-toggle';
        expandAllButton.textContent = '展开/折叠全部非精选论文';
        expandAllButton.addEventListener('click', function() {
            papersContainer.classList.toggle('expanded-all');
            this.textContent = papersContainer.classList.contains('expanded-all') ?
                '收起全部非精选论文' : '展开全部非精选论文';

            if (!papersContainer.classList.contains('expanded-all')) {
                papersContainer.querySelectorAll('.paper-details').forEach(details => {
                    details.style.display = '';
                });
            }

            // 更新所有论文标题前的图标状态
            const collapsedPapers = papersContainer.querySelectorAll('.collapsed-level-1');
            collapsedPapers.forEach(paper => {
                const iconElement = paper.querySelector('.expand-icon');
                if (iconElement) {
                    iconElement.className = papersContainer.classList.contains('expanded-all') ?
                        'expand-icon fa fa-eye' : 'expand-icon fa fa-eye-slash';
                }
            });
        });

        // 找到第一个非精选论文的位置
        const firstNormalPaper = papersContainer.querySelector('.simple-paper-card');
        if (firstNormalPaper) {
            papersContainer.insertBefore(expandAllButton, firstNormalPaper);
        }

        // 添加分割线用于展开分数<=1的论文（新管道两榜单均 >= 分数线，此处兼容历史数据）
        const divider = document.createElement('div');
        divider.className = 'papers-divider';

        const dividerLabel = document.createElement('div');
        dividerLabel.className = 'papers-divider-label';
        dividerLabel.textContent = '点击展开更多论文（评分较低）';
        dividerLabel.addEventListener('click', function() {
            papersContainer.classList.toggle('expanded-level-2');
            this.textContent = papersContainer.classList.contains('expanded-level-2') ?
                '点击收起低分论文' : '点击展开更多论文（评分较低）';
        });

        divider.appendChild(dividerLabel);

        // 将分割线放到第一篇低分论文前，确保文案和展开区域语义一致
        const firstLowScorePaper = papersContainer.querySelector('.collapsed-level-2');
        if (firstLowScorePaper) {
            papersContainer.insertBefore(divider, firstLowScorePaper);
        }
    });

    // 为每个非精选论文添加点击标题展开/折叠详情的功能
    const collapsedPapers = document.querySelectorAll('.collapsed-level-1');
    collapsedPapers.forEach(paper => {
        const titleElement = paper.querySelector('h3');
        if (titleElement) {
            titleElement.style.cursor = 'pointer';

            // 创建展开/折叠图标元素并设置样式
            const iconElement = document.createElement('i');
            iconElement.className = 'expand-icon fa fa-eye-slash cursor-pointer';
            iconElement.style.marginRight = '8px';

            // 将图标插入到标题链接之前，作为同级元素
            const linkElement = titleElement.querySelector('a');
            if (linkElement) {
                // 将图标直接添加到标题元素中，位于链接之前
                titleElement.insertBefore(iconElement, linkElement);

                // 为图标单独添加点击事件处理展开/折叠
                iconElement.addEventListener('click', function(e) {
                    e.stopPropagation(); // 阻止事件冒泡到标题元素
                    const details = paper.querySelector('.paper-details');
                    if (details) {
                        const isExpanded = details.style.display === 'block';
                        details.style.display = isExpanded ? 'none' : 'block';

                        // 更新图标状态
                        this.className = isExpanded ?
                            'expand-icon fa fa-eye-slash cursor-pointer' : 'expand-icon fa fa-eye cursor-pointer';
                        this.style.marginRight = '8px';
                    }
                });
            }

            // 为标题元素添加点击事件，也可以展开/折叠，但会检查点击目标
            titleElement.addEventListener('click', function(e) {
                // 仅当点击的是标题本身（非链接、非图标）时才展开/折叠
                if (!e.target.closest('a') && !e.target.closest('.expand-icon')) {
                    const details = paper.querySelector('.paper-details');
                    if (details) {
                        const isExpanded = details.style.display === 'block';
                        details.style.display = isExpanded ? 'none' : 'block';
                        // 更新图标状态
                        const iconElement = this.querySelector('.expand-icon');
                        if (iconElement) {
                            iconElement.className = isExpanded ?
                                'expand-icon fa fa-eye-slash cursor-pointer' : 'expand-icon fa fa-eye cursor-pointer';
                            iconElement.style.marginRight = '8px';
                        }
                    }
                }
            });
        }
    });

    // 核心/沾边快捷筛选：点击只看该榜单，再点同一按钮恢复双榜单
    const BUTTON_BASE = 'px-3 py-1 bg-gray-200 text-gray-700 rounded text-sm hover:bg-gray-300 transition-colors';
    const BUTTON_ACTIVE = 'px-3 py-1 bg-primary text-white rounded text-sm hover:bg-primary/90 transition-colors';
    const sections = {
        core: document.getElementById('core-section'),
        related: document.getElementById('related-section'),
    };
    const buttons = {
        core: document.getElementById('show-core'),
        related: document.getElementById('show-related'),
    };
    const displayCountElement = document.getElementById('display-count');
    const defaultCounts = displayCountElement ? displayCountElement.textContent : '';

    function countCards(section) {
        return section ? section.querySelectorAll('.paper-card, .simple-paper-card').length : 0;
    }

    function applyFilter(active) {
        Object.keys(sections).forEach(function(track) {
            const section = sections[track];
            if (!section) return;
            const visible = !active || active === track;
            section.style.display = visible ? '' : 'none';
            if (buttons[track]) {
                buttons[track].className = (active === track) ? BUTTON_ACTIVE : BUTTON_BASE;
            }
        });
        if (displayCountElement) {
            displayCountElement.textContent = active
                ? '只看' + (active === 'core' ? '核心' : '沾边') + ' ' + countCards(sections[active]) + ' 篇'
                : defaultCounts;
        }
    }

    Object.keys(buttons).forEach(function(track) {
        const button = buttons[track];
        if (!button) return;
        button.addEventListener('click', function() {
            applyFilter(this.className === BUTTON_ACTIVE ? null : track);
        });
    });
});
