// 分级折叠与精选/全部切换交互（由 generate_arxiv_html 拆出）
document.addEventListener('DOMContentLoaded', function() {
    // 在精选论文和普通论文之间添加展开/折叠按钮
    const papersContainer = document.querySelector('#papers-container');
    if (papersContainer) {
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
        
        // 添加分割线用于展开分数<=1的论文
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
    }
    
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
    
    // 实现"仅显示精选"按钮功能
    const showSelectedButton = document.getElementById('show-selected');
    if (showSelectedButton) {
        showSelectedButton.addEventListener('click', function() {
            // 显示所有精选论文，隐藏所有普通论文
            const selectedPapers = document.querySelectorAll('.paper-card');
            const normalPapers = document.querySelectorAll('.simple-paper-card');
            
            selectedPapers.forEach(paper => {
                paper.style.display = 'block';
            });
            
            normalPapers.forEach(paper => {
                paper.style.display = 'none';
            });
            
            // 更新显示计数
            const displayCountElement = document.getElementById('display-count');
            if (displayCountElement) {
                displayCountElement.textContent = `显示 ${selectedPapers.length} 篇论文 (共 ${selectedPapers.length + normalPapers.length} 篇)`;
            }
            
            // 更新按钮样式
            this.className = 'px-3 py-1 bg-primary text-white rounded text-sm hover:bg-primary/90 transition-colors';
            document.getElementById('show-all').className = 'px-3 py-1 bg-gray-200 text-gray-700 rounded text-sm hover:bg-gray-300 transition-colors';
            
            // 隐藏展开/折叠按钮和分割线
            const expandToggle = document.querySelector('.expand-toggle');
            if (expandToggle) expandToggle.style.display = 'none';
            
            const papersDivider = document.querySelector('.papers-divider');
            if (papersDivider) papersDivider.style.display = 'none';
        });
    }
    
    // 实现"全部论文"按钮功能
    const showAllButton = document.getElementById('show-all');
    if (showAllButton) {
        showAllButton.addEventListener('click', function() {
            // 显示所有论文
            const allPapers = document.querySelectorAll('.paper-card, .simple-paper-card');
            allPapers.forEach(paper => {
                paper.style.display = 'block';
            });
            
            // 重置折叠状态
            papersContainer.classList.remove('expanded-all');
            papersContainer.classList.remove('expanded-level-2');
            papersContainer.querySelectorAll('.paper-details').forEach(details => {
                details.style.display = '';
            });
            
            // 更新显示计数
            const displayCountElement = document.getElementById('display-count');
            if (displayCountElement) {
                displayCountElement.textContent = `显示 ${allPapers.length} 篇论文 (共 ${allPapers.length} 篇)`;
            }
            
            // 更新按钮样式
            this.className = 'px-3 py-1 bg-primary text-white rounded text-sm hover:bg-primary/90 transition-colors';
            document.getElementById('show-selected').className = 'px-3 py-1 bg-gray-200 text-gray-700 rounded text-sm hover:bg-gray-300 transition-colors';
            
            // 重新显示展开/折叠按钮和分割线
            const expandToggle = document.querySelector('.expand-toggle');
            if (expandToggle) {
                expandToggle.style.display = 'block';
                expandToggle.textContent = '展开全部非精选论文';
            }
            
            const papersDivider = document.querySelector('.papers-divider');
            if (papersDivider) papersDivider.style.display = 'block';
        });
    }
});
