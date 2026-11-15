import React, { useState } from 'react';
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronLeft, ChevronRight, Inbox } from 'lucide-react';
import { TableSkeleton } from '../common/Skeleton';
import { Button } from '../common/Button';
import { cn } from '../../utils/cn';

export interface Column<T> {
  key: string;
  title: string;
  dataIndex?: keyof T;
  render?: (value: any, record: T, index: number) => React.ReactNode;
  sortable?: boolean;
  align?: 'left' | 'center' | 'right';
  className?: string;
  width?: string;
}

export interface FinancialTableProps<T> {
  columns: Column<T>[];
  data: T[];
  rowKey: (record: T, index: number) => string | number;
  isLoading?: boolean;
  emptyText?: string;
  pagination?: {
    currentPage: number;
    pageSize: number;
    total: number;
    onPageChange: (page: number) => void;
  };
  onRowClick?: (record: T) => void;
  className?: string;
}

export function FinancialTable<T>({
  columns,
  data,
  rowKey,
  isLoading = false,
  emptyText = '暂无数据',
  pagination,
  onRowClick,
  className,
}: FinancialTableProps<T>) {
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc');

  const handleSort = (key: string) => {
    if (sortKey === key) {
      if (sortOrder === 'asc') {
        setSortOrder('desc');
      } else {
        setSortKey(null);
        setSortOrder('asc');
      }
    } else {
      setSortKey(key);
      setSortOrder('asc');
    }
  };

  const sortedData = React.useMemo(() => {
    if (!sortKey) return data;
    const col = columns.find((c) => c.key === sortKey);
    if (!col || !col.dataIndex) return data;

    return [...data].sort((a, b) => {
      const aVal = a[col.dataIndex!];
      const bVal = b[col.dataIndex!];
      if (aVal === bVal) return 0;
      if (aVal === null || aVal === undefined) return 1;
      if (bVal === null || bVal === undefined) return -1;

      if (typeof aVal === 'number' && typeof bVal === 'number') {
        return sortOrder === 'asc' ? aVal - bVal : bVal - aVal;
      }
      return sortOrder === 'asc'
        ? String(aVal).localeCompare(String(bVal))
        : String(bVal).localeCompare(String(aVal));
    });
  }, [data, sortKey, sortOrder, columns]);

  if (isLoading) {
    return <TableSkeleton rows={pagination?.pageSize || 6} cols={columns.length} />;
  }

  const totalPages = pagination ? Math.ceil(pagination.total / pagination.pageSize) : 1;

  return (
    <div className={cn('rounded-xl border border-slate-800 bg-slate-900/80 shadow-sm overflow-hidden', className)}>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs sm:text-sm">
          <thead className="bg-slate-950/70 border-b border-slate-800 text-slate-400 font-medium tracking-wider">
            <tr>
              {columns.map((col) => {
                const isSorted = sortKey === col.key;
                const alignClass =
                  col.align === 'right'
                    ? 'text-right'
                    : col.align === 'center'
                      ? 'text-center'
                      : 'text-left';

                return (
                  <th
                    key={col.key}
                    scope="col"
                    style={{ width: col.width }}
                    className={cn(
                      'px-4 py-3 select-none text-xs font-semibold',
                      alignClass,
                      col.sortable && 'cursor-pointer hover:text-slate-200 transition-colors',
                      col.className,
                    )}
                    onClick={() => col.sortable && handleSort(col.key)}
                  >
                    <div
                      className={cn(
                        'inline-flex items-center gap-1.5',
                        col.align === 'right' && 'justify-end w-full',
                        col.align === 'center' && 'justify-center w-full',
                      )}
                    >
                      <span>{col.title}</span>
                      {col.sortable && (
                        <span className="text-slate-500">
                          {isSorted ? (
                            sortOrder === 'asc' ? (
                              <ArrowUp className="h-3 w-3 text-blue-400" />
                            ) : (
                              <ArrowDown className="h-3 w-3 text-blue-400" />
                            )
                          ) : (
                            <ArrowUpDown className="h-3 w-3 opacity-40 hover:opacity-100" />
                          )}
                        </span>
                      )}
                    </div>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {sortedData.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="px-4 py-12 text-center text-slate-500">
                  <div className="flex flex-col items-center justify-center gap-2">
                    <Inbox className="h-8 w-8 text-slate-600" />
                    <p className="text-xs">{emptyText}</p>
                  </div>
                </td>
              </tr>
            ) : (
              sortedData.map((record, index) => {
                const key = rowKey(record, index);
                return (
                  <tr
                    key={key}
                    onClick={() => onRowClick && onRowClick(record)}
                    className={cn(
                      'hover:bg-slate-800/40 transition-colors',
                      onRowClick && 'cursor-pointer',
                    )}
                  >
                    {columns.map((col) => {
                      const alignClass =
                        col.align === 'right'
                          ? 'text-right'
                          : col.align === 'center'
                            ? 'text-center'
                            : 'text-left';

                      const rawVal = col.dataIndex ? record[col.dataIndex] : undefined;
                      const renderedVal = col.render
                        ? col.render(rawVal, record, index)
                        : (rawVal as React.ReactNode);

                      return (
                        <td
                          key={col.key}
                          className={cn('px-4 py-3 whitespace-nowrap text-slate-200', alignClass, col.className)}
                        >
                          {renderedVal ?? '--'}
                        </td>
                      );
                    })}
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination Footer */}
      {pagination && pagination.total > 0 && (
        <div className="flex flex-col sm:flex-row items-center justify-between gap-3 px-4 py-3 bg-slate-950/40 border-t border-slate-800 text-xs text-slate-400">
          <div>
            共 <span className="font-semibold text-slate-200">{pagination.total}</span> 条记录， 第{' '}
            <span className="font-semibold text-slate-200">{pagination.currentPage}</span> /{' '}
            <span className="font-semibold text-slate-200">{totalPages}</span> 页
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="xs"
              disabled={pagination.currentPage <= 1}
              onClick={() => pagination.onPageChange(pagination.currentPage - 1)}
              leftIcon={<ChevronLeft className="h-3 w-3" />}
            >
              上一页
            </Button>
            <Button
              variant="outline"
              size="xs"
              disabled={pagination.currentPage >= totalPages}
              onClick={() => pagination.onPageChange(pagination.currentPage + 1)}
              rightIcon={<ChevronRight className="h-3 w-3" />}
            >
              下一页
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
