import React, { useEffect, useState } from 'react';
import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { Navbar } from './Navbar';
import { MobileMenu } from './MobileMenu';
import { ComplianceDisclaimer } from '../compliance/ComplianceDisclaimer';
import { QuotaExceededModal } from '../compliance/QuotaExceededModal';
import { CircuitBreakerAlert } from '../compliance/CircuitBreakerAlert';
import { storage } from '../../utils/storage';

const SIDEBAR_COLLAPSED_KEY = 'stockpilot_sidebar_collapsed';

export interface AppLayoutProps {
  children?: React.ReactNode;
}

export const AppLayout: React.FC<AppLayoutProps> = ({ children }) => {
  const [isCollapsed, setIsCollapsed] = useState<boolean>(() => {
    return storage.get(SIDEBAR_COLLAPSED_KEY) === 'true';
  });
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState<boolean>(false);
  const [isQuotaModalOpen, setIsQuotaModalOpen] = useState<boolean>(false);
  const [isCircuitAlertOpen, setIsCircuitAlertOpen] = useState<boolean>(false);

  const toggleCollapse = () => {
    setIsCollapsed((prev) => {
      const next = !prev;
      storage.set(SIDEBAR_COLLAPSED_KEY, String(next));
      return next;
    });
  };

  useEffect(() => {
    const handleQuotaExceeded = () => setIsQuotaModalOpen(true);
    const handleCircuitBreaker = () => setIsCircuitAlertOpen(true);

    window.addEventListener('api:quota_exceeded', handleQuotaExceeded);
    window.addEventListener('api:circuit_breaker', handleCircuitBreaker);

    return () => {
      window.removeEventListener('api:quota_exceeded', handleQuotaExceeded);
      window.removeEventListener('api:circuit_breaker', handleCircuitBreaker);
    };
  }, []);

  return (
    <div className="min-h-screen flex bg-slate-950 text-slate-100 font-sans antialiased">
      {/* Desktop Sidebar */}
      <Sidebar isCollapsed={isCollapsed} onToggleCollapse={toggleCollapse} />

      {/* Mobile Menu Drawer */}
      <MobileMenu isOpen={isMobileMenuOpen} onClose={() => setIsMobileMenuOpen(false)} />

      {/* Main Area */}
      <div className="flex-1 flex flex-col min-w-0 min-h-screen">
        {/* Top Navbar */}
        <Navbar onOpenMobileMenu={() => setIsMobileMenuOpen(true)} />

        {/* Content Body */}
        <main className="flex-1 w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          {children || <Outlet />}
        </main>

        {/* Global Compliance Disclaimer Footer */}
        <footer className="mt-auto">
          <ComplianceDisclaimer variant="banner" />
        </footer>
      </div>

      {/* Global Modals for 429 and 503 */}
      <QuotaExceededModal
        isOpen={isQuotaModalOpen}
        onClose={() => setIsQuotaModalOpen(false)}
      />
      <CircuitBreakerAlert
        isOpen={isCircuitAlertOpen}
        onClose={() => setIsCircuitAlertOpen(false)}
      />
    </div>
  );
};
