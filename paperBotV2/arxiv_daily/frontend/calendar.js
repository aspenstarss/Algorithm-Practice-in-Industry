// 日历导航（由 generate_arxiv_html 拆出；数据注入见 index.html 的 window.CALENDAR_CONFIG）

    // 初始化日历
    document.addEventListener('DOMContentLoaded', () => {
try {
    console.log('Attempting to initialize calendar...');
    initCalendar();
} catch (error) {
    console.error('Error initializing calendar:', error);
}
    });

    // 日历初始化函数
    function initCalendar() {
const toggleBtn = document.getElementById('date-picker-toggle');
const datePicker = document.getElementById('date-picker');
const calendarGrid = document.getElementById('calendar-grid');
const prevMonthBtn = document.getElementById('prev-month');
const nextMonthBtn = document.getElementById('next-month');
const currentMonthEl = document.getElementById('current-month');
const selectedDateText = document.getElementById('selected-date-text');

// 当前页面日期由后端注入，避免从展示文本反解析和new Date(date-only)时区差异
const currentDateConfig = window.CALENDAR_CONFIG.currentDateConfig;
const currentPageDate = currentDateConfig.display;
const currentDate = new Date(
    currentDateConfig.year,
    currentDateConfig.month - 1,
    currentDateConfig.day
);
let displayYear = currentDateConfig.year;
let displayMonth = currentDateConfig.month - 1;

// 有论文数据的日期列表
const availableDates = window.CALENDAR_CONFIG.availableDates;

const savedDate = localStorage.getItem('selectedDate');
const savedYear = localStorage.getItem('selectedYear');
const savedMonth = localStorage.getItem('selectedMonth');

// 页面日期始终以当前HTML为准，localStorage只用于恢复上次打开的月份视图
selectedDateText.textContent = currentPageDate;
localStorage.setItem('selectedDate', currentPageDate);
if (savedDate === currentPageDate && savedYear && savedMonth) {
    const parsedYear = parseInt(savedYear, 10);
    const parsedMonth = parseInt(savedMonth, 10);
    if (!Number.isNaN(parsedYear) && !Number.isNaN(parsedMonth)) {
        displayYear = parsedYear;
        displayMonth = parsedMonth;
    }
}

// 切换日历显示状态
toggleBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    
    // 显式控制hidden类的添加和移除
    if (datePicker.classList.contains('hidden')) {
        // 显示日历 - 确保移除hidden类
        datePicker.classList.remove('hidden');
        renderCalendar();
    } else {
        // 隐藏日历
        datePicker.classList.add('hidden');
    }
});

// 点击其他区域关闭日历
document.addEventListener('click', () => {
    if (!datePicker.classList.contains('hidden')) {
        datePicker.classList.add('hidden');
    }
});

// 阻止日历内部点击事件冒泡
datePicker.addEventListener('click', (e) => {
    e.stopPropagation();
});

// 上月和下月按钮
prevMonthBtn.addEventListener('click', () => {
    displayMonth--;
    if (displayMonth < 0) {
        displayMonth = 11;
        displayYear--;
    }
    renderCalendar();
});

nextMonthBtn.addEventListener('click', () => {
    displayMonth++;
    if (displayMonth > 11) {
        displayMonth = 0;
        displayYear++;
    }
    renderCalendar();
});

/**
 * 渲染日历
 */
function renderCalendar() {
    // 清空日历网格
    calendarGrid.innerHTML = '';
    
    // 更新当前月份显示
    const monthNames = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月'];
    currentMonthEl.textContent = displayYear + '年' + monthNames[displayMonth];
    
    // 计算当前月份的第一天是星期几
    const firstDay = new Date(displayYear, displayMonth, 1);
    const firstDayOfWeek = firstDay.getDay();
    
    // 计算当前月份的天数
    const daysInMonth = new Date(displayYear, displayMonth + 1, 0).getDate();
    
    // 添加上月的占位天数
    for (let i = 0; i < firstDayOfWeek; i++) {
        const emptyDay = document.createElement('div');
        emptyDay.classList.add('py-1', 'text-gray-300');
        calendarGrid.appendChild(emptyDay);
    }
    
    // 获取当前日期（用于高亮显示）
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    
    // 添加当前月份的天数
    for (let day = 1; day <= daysInMonth; day++) {
        const dayElement = document.createElement('div');
        const currentDateObj = new Date(displayYear, displayMonth, day);
        const dateStr = displayYear + String(displayMonth + 1).padStart(2, '0') + String(day).padStart(2, '0');
        const displayDateStr = displayYear + '-' + String(displayMonth + 1).padStart(2, '0') + '-' + String(day).padStart(2, '0');
        
        // 设置日期元素基本样式
        dayElement.textContent = day;
        
        // 检查该日期是否有论文数据
        const hasPapers = availableDates.includes(dateStr);
        
        if (hasPapers) {
            // 有论文数据的日期样式
            dayElement.classList.add('py-1', 'cursor-pointer', 'hover:bg-gray-100', 'rounded', 'bg-blue-50', 'font-medium');
            
            // 添加点击事件，跳转到对应日期的页面
            dayElement.addEventListener('click', () => {
                console.log('Date clicked:', displayDateStr);
                selectedDateText.textContent = displayDateStr;
                
                // 保存选择状态到localStorage
                localStorage.setItem('selectedDate', displayDateStr);
                localStorage.setItem('selectedYear', displayYear.toString());
                localStorage.setItem('selectedMonth', displayMonth.toString());
                
                datePicker.classList.add('hidden');
                
                // 构造目标URL并跳转
                const targetUrl = 'arxiv_' + dateStr + '.html';
                window.location.href = targetUrl;
            });
        } else {
            // 没有论文数据的日期样式（置灰不可点击）
            dayElement.classList.add('py-1', 'text-gray-400', 'cursor-not-allowed');
        }
        
        // 高亮显示当天日期（覆盖之前的样式）
        if (currentDateObj.getTime() === today.getTime()) {
            dayElement.classList.remove('bg-blue-50');
            dayElement.classList.add('bg-primary', 'text-white', 'font-bold', 'shadow');
            if (!hasPapers) {
                // 当天没有论文时，仍然置灰但保持背景色
                dayElement.classList.add('opacity-70');
            }
        }
        
        // 高亮显示当前选中的日期
        if (dateStr === currentDateConfig.ymd) {
            dayElement.classList.add('font-bold', 'border-2', 'border-primary', 'rounded-lg', 'shadow-md');
        }
        
        // 增强有论文数据的日期样式，使其更明显
        if (hasPapers && currentDateObj.getTime() !== today.getTime()) {
            dayElement.classList.add('bg-blue-100', 'hover:bg-blue-200', 'transition-colors', 'duration-200');
        }
        
        calendarGrid.appendChild(dayElement);
    }
}
    }
