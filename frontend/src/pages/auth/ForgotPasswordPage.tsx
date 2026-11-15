import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import authApi from '../../api/auth';
import { AppError } from '../../utils/errors';
import { AlertCircle, ArrowLeft, CheckCircle2, KeyRound, Loader2, Mail } from 'lucide-react';

export const ForgotPasswordPage: React.FC = () => {
  const [email, setEmail] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSubmitted, setIsSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!email.trim()) {
      setError('请输入注册时填写的邮箱地址');
      return;
    }

    setIsSubmitting(true);
    try {
      await authApi.requestPasswordReset({ email: email.trim() });
      setIsSubmitted(true);
    } catch (err: unknown) {
      if (err instanceof AppError) {
        setError(err.message);
      } else {
        setError('请求提交异常，请稍后重试');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-[75vh] items-center justify-center px-4 py-12">
      <div className="w-full max-w-md rounded-2xl border border-gray-200 bg-white p-8 shadow-sm">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-amber-500 text-white shadow">
            <KeyRound className="h-6 w-6" />
          </div>
          <h2 className="text-2xl font-bold tracking-tight text-gray-900">找回登录密码</h2>
          <p className="mt-1 text-sm text-gray-500">输入您的注册邮箱以获取密码重置凭证</p>
        </div>

        {error && (
          <div className="mb-6 flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 p-3.5 text-sm text-red-700">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-red-600" />
            <div className="flex-1 font-medium">{error}</div>
          </div>
        )}

        {isSubmitted ? (
          <div className="rounded-xl bg-emerald-50 border border-emerald-200 p-5 text-center">
            <CheckCircle2 className="mx-auto h-8 w-8 text-emerald-600 mb-2" />
            <h3 className="text-base font-bold text-gray-900 mb-1">重置请求已接收</h3>
            <p className="text-xs text-gray-600 leading-relaxed mb-4">
              如果该邮箱存在于系统中，重置邮件及一次性 Token 已发送至您的邮箱。请在邮件中查收一次性 Token，并点击下方前往重置页面完成修改。
            </p>
            <div className="flex flex-col gap-2">
              <Link
                to="/reset-password"
                className="w-full rounded-lg bg-emerald-600 py-2 text-xs font-semibold text-white hover:bg-emerald-700 transition-colors"
              >
                前往输入 Token 重置密码
              </Link>
              <Link
                to="/login"
                className="w-full rounded-lg border border-gray-300 py-2 text-xs font-medium text-gray-700 hover:bg-gray-50 transition-colors"
              >
                返回登录页面
              </Link>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-gray-600 mb-1.5">
                电子邮箱
              </label>
              <div className="relative">
                <Mail className="absolute left-3.5 top-3 h-4 w-4 text-gray-400" />
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@example.com"
                  className="w-full rounded-lg border border-gray-300 py-2.5 pl-10 pr-3.5 text-sm text-gray-900 placeholder-gray-400 focus:border-brand-600 focus:outline-none focus:ring-1 focus:ring-brand-600"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={isSubmitting}
              className="mt-2 flex w-full items-center justify-center gap-2 rounded-lg bg-brand-600 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-brand-700 focus:outline-none focus:ring-2 focus:ring-brand-600 focus:ring-offset-2 disabled:opacity-60 transition-colors"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  正在提交...
                </>
              ) : (
                '发送重置邮件'
              )}
            </button>

            <div className="pt-2 text-center">
              <Link to="/login" className="inline-flex items-center gap-1.5 text-xs font-medium text-gray-600 hover:text-gray-900">
                <ArrowLeft className="h-3.5 w-3.5" /> 返回登录
              </Link>
            </div>
          </form>
        )}
      </div>
    </div>
  );
};

export default ForgotPasswordPage;
