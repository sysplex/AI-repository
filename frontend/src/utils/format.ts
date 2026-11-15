/**
 * 金融数值、价格、百分比与日期格式化工具。
 */

export function formatPrice(val: number | string | null | undefined, decimals = 2): string {
  if (val === null || val === undefined || val === '') return '--';
  const num = typeof val === 'number' ? val : parseFloat(val);
  if (isNaN(num)) return '--';

  // 小于 1 美元的美股显示 4 位小数
  const targetDecimals = Math.abs(num) < 1 && Math.abs(num) > 0 ? 4 : decimals;
  return `$${num.toLocaleString('en-US', {
    minimumFractionDigits: targetDecimals,
    maximumFractionDigits: targetDecimals,
  })}`;
}

export function formatPercent(val: number | string | null | undefined, withSign = true): string {
  if (val === null || val === undefined || val === '') return '--';
  const num = typeof val === 'number' ? val : parseFloat(val);
  if (isNaN(num)) return '--';

  const sign = withSign && num > 0 ? '+' : '';
  return `${sign}${num.toFixed(2)}%`;
}

export function formatLargeNumber(val: number | string | null | undefined): string {
  if (val === null || val === undefined || val === '') return '--';
  const num = typeof val === 'number' ? val : parseFloat(val);
  if (isNaN(num)) return '--';

  const abs = Math.abs(num);
  if (abs >= 1e12) return `${(num / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `${(num / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${(num / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `${(num / 1e3).toFixed(2)}K`;
  return num.toLocaleString('en-US');
}

export function formatDateTime(isoString: string | null | undefined): string {
  if (!isoString) return '--';
  try {
    const d = new Date(isoString);
    return d.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    });
  } catch {
    return isoString;
  }
}
