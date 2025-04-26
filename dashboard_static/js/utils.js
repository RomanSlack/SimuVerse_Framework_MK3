// Utilities for SimuExo Agent Dashboard

/**
 * Safely formats a date object or string to a readable format
 * @param {Date|string} date - Date object or ISO string
 * @param {Object} options - Formatting options
 * @returns {string} Formatted date string
 */
function formatDate(date, options = {}) {
    if (!date) return 'Unknown';
    
    try {
        const dateObj = typeof date === 'string' ? new Date(date) : date;
        
        if (isNaN(dateObj.getTime())) {
            return 'Invalid Date';
        }
        
        const defaultOptions = { 
            year: 'numeric', 
            month: 'short', 
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        };
        
        return dateObj.toLocaleString(undefined, { ...defaultOptions, ...options });
    } catch (e) {
        console.error('Error formatting date:', e);
        return 'Error';
    }
}

/**
 * Truncates a string to a maximum length and adds ellipsis if needed
 * @param {string} str - String to truncate
 * @param {number} maxLength - Maximum length
 * @returns {string} Truncated string
 */
function truncateString(str, maxLength = 100) {
    if (!str) return '';
    
    if (str.length <= maxLength) {
        return str;
    }
    
    return str.substring(0, maxLength) + '...';
}

/**
 * Debounce function to limit the rate at which a function can fire
 * @param {Function} func - Function to debounce
 * @param {number} wait - Wait time in milliseconds
 * @returns {Function} Debounced function
 */
function debounce(func, wait = 300) {
    let timeout;
    
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

/**
 * Escapes HTML characters to prevent XSS
 * @param {string} html - String to escape
 * @returns {string} Escaped string
 */
function escapeHtml(html) {
    if (!html) return '';
    
    const div = document.createElement('div');
    div.textContent = html;
    return div.innerHTML;
}

/**
 * Creates a throttled function that only invokes func at most once per every wait milliseconds
 * @param {Function} func - Function to throttle
 * @param {number} wait - Wait time in milliseconds
 * @returns {Function} Throttled function
 */
function throttle(func, wait = 300) {
    let lastFunc;
    let lastRan;
    
    return function executedFunction(...args) {
        if (!lastRan) {
            func(...args);
            lastRan = Date.now();
        } else {
            clearTimeout(lastFunc);
            lastFunc = setTimeout(() => {
                if ((Date.now() - lastRan) >= wait) {
                    func(...args);
                    lastRan = Date.now();
                }
            }, wait - (Date.now() - lastRan));
        }
    };
}

/**
 * Parses a JSON string safely
 * @param {string} jsonString - JSON string to parse
 * @param {*} fallback - Fallback value if parsing fails
 * @returns {*} Parsed object or fallback value
 */
function safeJsonParse(jsonString, fallback = {}) {
    try {
        return JSON.parse(jsonString);
    } catch (e) {
        console.error('Error parsing JSON:', e);
        return fallback;
    }
}

/**
 * Gets a readable difference between two dates
 * @param {Date|string} date - Date to compare
 * @param {Date|string} [baseDate=new Date()] - Base date to compare with
 * @returns {string} Human readable time difference
 */
function getTimeDifference(date, baseDate = new Date()) {
    if (!date) return 'Unknown';
    
    try {
        const dateObj = typeof date === 'string' ? new Date(date) : date;
        const baseDateObj = typeof baseDate === 'string' ? new Date(baseDate) : baseDate;
        
        if (isNaN(dateObj.getTime()) || isNaN(baseDateObj.getTime())) {
            return 'Invalid Date';
        }
        
        const diffMs = Math.abs(baseDateObj - dateObj);
        const diffSeconds = Math.floor(diffMs / 1000);
        
        if (diffSeconds < 60) {
            return diffSeconds + ' second' + (diffSeconds === 1 ? '' : 's') + ' ago';
        }
        
        const diffMinutes = Math.floor(diffSeconds / 60);
        
        if (diffMinutes < 60) {
            return diffMinutes + ' minute' + (diffMinutes === 1 ? '' : 's') + ' ago';
        }
        
        const diffHours = Math.floor(diffMinutes / 60);
        
        if (diffHours < 24) {
            return diffHours + ' hour' + (diffHours === 1 ? '' : 's') + ' ago';
        }
        
        const diffDays = Math.floor(diffHours / 24);
        
        if (diffDays < 30) {
            return diffDays + ' day' + (diffDays === 1 ? '' : 's') + ' ago';
        }
        
        const diffMonths = Math.floor(diffDays / 30);
        
        if (diffMonths < 12) {
            return diffMonths + ' month' + (diffMonths === 1 ? '' : 's') + ' ago';
        }
        
        const diffYears = Math.floor(diffMonths / 12);
        return diffYears + ' year' + (diffYears === 1 ? '' : 's') + ' ago';
    } catch (e) {
        console.error('Error calculating time difference:', e);
        return 'Error';
    }
}