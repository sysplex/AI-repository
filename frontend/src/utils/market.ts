export interface MarketStatus {
  status: 'open' | 'pre' | 'after' | 'closed';
  label: string;
  sublabel: string;
  badgeClass: string;
  dotClass: string;
}

export function getUSMarketStatus(now = new Date()): MarketStatus {
  // Convert current time to US Eastern Time (America/New_York)
  const estString = now.toLocaleString('en-US', { timeZone: 'America/New_York' });
  const estDate = new Date(estString);

  const dayOfWeek = estDate.getDay(); // 0 is Sunday, 6 is Saturday
  const hours = estDate.getHours();
  const minutes = estDate.getMinutes();
  const timeInMinutes = hours * 60 + minutes;

  // Weekend
  if (dayOfWeek === 0 || dayOfWeek === 6) {
    return {
      status: 'closed',
      label: '已休市',
      sublabel: '周末休市',
      badgeClass: 'bg-slate-800 text-slate-400 border-slate-700',
      dotClass: 'bg-slate-500',
    };
  }

  // Pre-market: 04:00 - 09:30 (240 min to 570 min)
  if (timeInMinutes >= 240 && timeInMinutes < 570) {
    return {
      status: 'pre',
      label: '盘前交易',
      sublabel: '04:00-09:30 EST',
      badgeClass: 'bg-blue-950/70 text-blue-300 border-blue-500/30',
      dotClass: 'bg-blue-400 animate-pulse',
    };
  }

  // Regular market: 09:30 - 16:00 (570 min to 960 min)
  if (timeInMinutes >= 570 && timeInMinutes < 960) {
    return {
      status: 'open',
      label: '美股开盘中',
      sublabel: '09:30-16:00 EST',
      badgeClass: 'bg-emerald-950/70 text-emerald-300 border-emerald-500/30',
      dotClass: 'bg-emerald-400 animate-ping',
    };
  }

  // After-hours: 16:00 - 20:00 (960 min to 1200 min)
  if (timeInMinutes >= 960 && timeInMinutes < 1200) {
    return {
      status: 'after',
      label: '盘后交易',
      sublabel: '16:00-20:00 EST',
      badgeClass: 'bg-amber-950/70 text-amber-300 border-amber-500/30',
      dotClass: 'bg-amber-400 animate-pulse',
    };
  }

  // Night closed
  return {
    status: 'closed',
    label: '已休市',
    sublabel: '次日04:00开盘',
    badgeClass: 'bg-slate-800 text-slate-400 border-slate-700',
    dotClass: 'bg-slate-500',
  };
}
