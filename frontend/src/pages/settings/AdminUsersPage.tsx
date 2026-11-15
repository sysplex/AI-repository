import React, { useEffect, useState } from 'react';
import authApi from '../../api/auth';
import type { PaginatedUsers, UserPublic } from '../../api/types';
import { AppError } from '../../utils/errors';
import { formatDateTime } from '../../utils/format';
import { AlertCircle, ChevronLeft, ChevronRight, Loader2, ShieldCheck, Users } from 'lucide-react';

export const AdminUsersPage: React.FC = () => {
  const [data, setData] = useState<PaginatedUsers | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const limit = 20;

  const fetchUsers = async (targetPage: number) => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await authApi.getAdminUsers({
        offset: targetPage * limit,
        limit,
      });
      setData(res);
      setPage(targetPage);
    } catch (err: unknown) {
      if (err instanceof AppError) {
        setError(err.message);
      } else {
        setError('加载用户列表失败，请检查管理员权限');
      }
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void fetchUsers(0);
  }, []);

  const total = data?.total ?? 0;
  const items: UserPublic[] = data?.items ?? [];
  const totalPages = Math.ceil(total / limit) || 1;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between border-b pb-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-gray-900">用户管理控制台</h1>
            <span className="inline-flex items-center gap-1 rounded-md bg-purple-50 px-2 py-0.5 text-xs font-semibold text-purple-700 border border-purple-200">
              <ShieldCheck className="h-3.5 w-3.5" /> 仅系统管理员可见
            </span>
          </div>
          <p className="mt-1 text-sm text-gray-500">
            监控全平台多租户用户账号状态、权限分配与注册概览（共 {total} 名用户）
          </p>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-3 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          <AlertCircle className="h-5 w-5 text-red-600 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {isLoading ? (
        <div className="flex min-h-[40vh] items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-brand-600" />
        </div>
      ) : (
        <div className="rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-gray-50 text-xs uppercase font-semibold text-gray-500 border-b">
                <tr>
                  <th className="px-6 py-3.5">电子邮箱</th>
                  <th className="px-6 py-3.5">角色</th>
                  <th className="px-6 py-3.5">状态</th>
                  <th className="px-6 py-3.5">投资风险偏好</th>
                  <th className="px-6 py-3.5">租户 ID</th>
                  <th className="px-6 py-3.5">注册时间</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {items.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-6 py-12 text-center text-gray-500">
                      <Users className="mx-auto h-8 w-8 text-gray-300 mb-2" />
                      暂无用户数据
                    </td>
                  </tr>
                ) : (
                  items.map((u) => (
                    <tr key={u.id} className="hover:bg-gray-50 transition-colors">
                      <td className="px-6 py-4 font-medium text-gray-900">{u.email}</td>
                      <td className="px-6 py-4">
                        <span
                          className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                            u.role === 'admin'
                              ? 'bg-purple-100 text-purple-800 border border-purple-200'
                              : 'bg-gray-100 text-gray-700'
                          }`}
                        >
                          {u.role === 'admin' ? '系统管理员' : '标准用户'}
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        <span
                          className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                            u.status === 'active'
                              ? 'bg-emerald-100 text-emerald-800'
                              : 'bg-red-100 text-red-800'
                          }`}
                        >
                          {u.status === 'active' ? '正常' : '已禁用'}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-gray-600 capitalize">
                        {u.settings?.risk_profile || '--'}
                      </td>
                      <td className="px-6 py-4 font-mono text-xs text-gray-500">
                        {u.id.substring(0, 8)}...
                      </td>
                      <td className="px-6 py-4 text-xs text-gray-500">
                        {formatDateTime(u.created_at)}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="flex items-center justify-between border-t px-6 py-3 text-sm text-gray-500">
            <div>
              显示第 <span className="font-semibold">{total === 0 ? 0 : page * limit + 1}</span> 至{' '}
              <span className="font-semibold">{Math.min((page + 1) * limit, total)}</span> 条，共{' '}
              <span className="font-semibold">{total}</span> 条
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => void fetchUsers(page - 1)}
                disabled={page === 0}
                className="flex items-center gap-1 rounded-md border border-gray-300 px-3 py-1.5 text-xs font-semibold hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <ChevronLeft className="h-4 w-4" /> 上一页
              </button>
              <span className="text-xs text-gray-700 font-medium">
                {page + 1} / {totalPages}
              </span>
              <button
                onClick={() => void fetchUsers(page + 1)}
                disabled={page + 1 >= totalPages}
                className="flex items-center gap-1 rounded-md border border-gray-300 px-3 py-1.5 text-xs font-semibold hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                下一页 <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AdminUsersPage;
