/**
 * Global formatting utilities for dates and amounts
 * 
 * Used across all pages in the application for consistent formatting.
 */

/**
 * Format date from ISO format (YYYY-MM-DD) or Date object to DD/MM/YYYY
 * @param {string|Date} dateStr - Date string in ISO format or Date object
 * @returns {string} Formatted date string in DD/MM/YYYY format, or empty string if invalid
 */
function formatDateDDMMYYYY(dateStr) {
    if (!dateStr) return '';
    
    try {
        let date;
        if (typeof dateStr === 'string') {
            date = new Date(dateStr + 'T00:00:00');
        } else {
            date = dateStr;
        }
        
        if (isNaN(date.getTime())) return '';
        
        const day = String(date.getDate()).padStart(2, '0');
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const year = date.getFullYear();
        
        return day + '/' + month + '/' + year;
    } catch (e) {
        return '';
    }
}

/**
 * Convert date from DD/MM/YYYY to YYYY-MM-DD (for HTML date input)
 * @param {string} dateStr - Date string in DD/MM/YYYY format or ISO format
 * @returns {string} Formatted date string in YYYY-MM-DD format, or empty string if invalid
 */
function convertToDateInputFormat(dateStr) {
    if (!dateStr) return '';
    
    try {
        let date;
        
        // Check if already in YYYY-MM-DD format
        if (/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
            return dateStr;
        }
        
        // Try ISO format first
        date = new Date(dateStr + 'T00:00:00');
        if (!isNaN(date.getTime())) {
            const year = date.getFullYear();
            const month = String(date.getMonth() + 1).padStart(2, '0');
            const day = String(date.getDate()).padStart(2, '0');
            return year + '-' + month + '-' + day;
        }
        
        return '';
    } catch (e) {
        return '';
    }
}

/**
 * Format amount to Indian rupee display format (x,xx,xx,xxx)
 * 
 * Examples:
 *   100 -> "100.00"
 *   1000 -> "1,000.00"
 *   100000 -> "1,00,000.00"
 *   1000000 -> "10,00,000.00" (10 lakhs)
 *   10000000 -> "1,00,00,000.00" (1 crore)
 * 
 * @param {number|string} amount - Amount to format
 * @returns {string} Formatted amount string in Indian rupee format
 */
function formatIndianRupee(amount) {
    if (amount === null || amount === undefined || isNaN(amount)) {
        return '0.00';
    }
    
    try {
        const num = Math.abs(Number(amount)).toFixed(2);
        const parts = num.split('.');
        let intPart = parts[0];
        const decPart = parts[1];
        
        if (intPart.length <= 3) {
            return intPart + '.' + decPart;
        }
        
        // Apply Indian numbering format (x,xx,xx,xxx)
        const lastThree = intPart.substring(intPart.length - 3);
        let remaining = intPart.substring(0, intPart.length - 3);
        
        let result = '';
        for (let i = 0; i < remaining.length; i++) {
            if (i > 0 && (remaining.length - i) % 2 === 0) {
                result += ',';
            }
            result += remaining[i];
        }
        
        return result + ',' + lastThree + '.' + decPart;
    } catch (e) {
        return '0.00';
    }
}

/**
 * Format currency with Indian rupee symbol
 * @param {number|string} amount - Amount to format
 * @returns {string} Formatted amount string with ₹ symbol
 */
function formatCurrencyINR(amount) {
    return '₹' + formatIndianRupee(amount);
}
