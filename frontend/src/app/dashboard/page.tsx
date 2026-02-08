'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { apiClient } from '@/lib/api-client';
import { InvoiceCard } from '@/components/InvoiceCard';

interface InvoiceSummary {
  total_count: number;
  total_amount: number;
  pending_kdv: number;
  monthly_amount: number;
}

interface Invoice {
  id: string;
  filename: string;
  status: string;
  total_amount: number | null;
  invoice_date: string | null;
  supplier_name: string | null;
  created_at: string;
  updated_at: string;
  extracted_data: any;
}

interface InvoiceListResponse {
  invoices: Invoice[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export default function DashboardPage() {
  const router = useRouter();
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [summary, setSummary] = useState<InvoiceSummary>({
    total_count: 0,
    total_amount: 0,
    pending_kdv: 0,
    monthly_amount: 0,
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [hasMore, setHasMore] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [dateFrom, setDateFrom] = useState<string>('');
  const [dateTo, setDateTo] = useState<string>('');
  const [loadingMore, setLoadingMore] = useState(false);

  const calculateSummary = useCallback((invoiceList: Invoice[]) => {
    const totalCount = invoiceList.length;
    const totalAmount = invoiceList.reduce(
      (sum, inv) => sum + (inv.total_amount || 0),
      0
    );

    const now = new Date();
    const currentMonth = now.getMonth();
    const currentYear = now.getFullYear();

    const monthlyAmount = invoiceList
      .filter((inv) => {
        if (!inv.invoice_date) return false;
        const invDate = new Date(inv.invoice_date);
        return (
          invDate.getMonth() === currentMonth &&
          invDate.getFullYear() === currentYear
        );
      })
      .reduce((sum, inv) => sum + (inv.total_amount || 0), 0);

    const pendingKdv = invoiceList
      .filter((inv) => inv.status === 'processed' || inv.status === 'pending_review')
      .reduce((sum, inv) => {
        if (inv.extracted_data?.kdv_amount) {
          return sum + parseFloat(inv.extracted_data.kdv_amount);
        }
        return sum;
      }, 0);

    setSummary({
      total_count: totalCount,
      total_amount: totalAmount,
      pending_kdv: pendingKdv,
      monthly_amount: monthlyAmount,
    });
  }, []);

  const fetchInvoices = useCallback(
    async (pageNum: number, append: boolean = false) => {
      try {
        if (append) {
          setLoadingMore(true);
        } else {
          setLoading(true);
        }
        setError(null);

        const params: any = {
          page: pageNum,
          page_size: 12,
        };

        if (statusFilter && statusFilter !== 'all') {
          params.status = statusFilter;
        }

        if (dateFrom) {
          params.date_from = dateFrom;
        }

        if (dateTo) {
          params.date_to = dateTo;
        }

        if (searchQuery) {
          params.search = searchQuery;
        }

        const response = await apiClient.get<InvoiceListResponse>(
          '/invoices',
          { params }
        );

        if (append) {
          setInvoices((prev) => [...prev, ...response.data.invoices]);
        } else {
          setInvoices(response.data.invoices);
        }

        setTotalPages(response.data.total_pages);
        setHasMore(pageNum < response.data.total_pages);

        if (!append) {
          calculateSummary(response.data.invoices);
        }
      } catch (err: any) {
        console.error('Error fetching invoices:', err);
        if (err.response?.status === 401) {
          router.push('/login');
        } else {
          setError(
            err.response?.data?.message ||
              'Faturalar yüklenirken bir hata oluştu'
          );
        }
      } finally {
        setLoading(false);
        setLoadingMore(false);
      }
    },
    [statusFilter, dateFrom, dateTo, searchQuery, router, calculateSummary]
  );

  useEffect(() => {
    setPage(1);
    fetchInvoices(1, false);
  }, [statusFilter, dateFrom, dateTo, searchQuery, fetchInvoices]);

  const handleLoadMore = () => {
    if (!loadingMore && hasMore) {
      const nextPage = page + 1;
      setPage(nextPage);
      fetchInvoices(nextPage, true);
    }
  };

  const handleRefresh = () => {
    setPage(1);
    fetchInvoices(1, false);
  };

  const handleInvoiceUpdate = (updatedInvoice: Invoice) => {
    setInvoices((prev) =>
      prev.map((inv) =>
        inv.id === updatedInvoice.id ? updatedInvoice : inv
      )
    );
    calculateSummary(
      invoices.map((inv) =>
        inv.id === updatedInvoice.id ? updatedInvoice : inv
      )
    );
  };

  const handleInvoiceDelete = (deletedId: string) => {
    setInvoices((prev) => prev.filter((inv) => inv.id !== deletedId));
    calculateSummary(invoices.filter((inv) => inv.id !== deletedId));
  };

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('tr-TR', {
      style: 'currency',
      currency: 'TRY',
    }).format(amount);
  };

  if (loading && page === 1) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
          <p className="mt-4 text-gray-600">Yükleniyor...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900">Dashboard</h1>
          <p className="mt-2 text-gray-600">Fatura yönetim paneliniz</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          <div className="bg-white rounded-lg shadow p-6">
            <div className="flex items-center">
              <div className="flex-1">
                <p className="text-sm font-medium text-gray-600">
                  Toplam Fatura
                </p>
                <p className="text-2xl font-bold text-gray-900 mt-1">
                  {summary.total_count}
                </p>
              </div>
              <div className="ml-4 bg-blue-100 rounded-full p-3">
                <svg
                  className="w-6 h-6 text-blue-600"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                  />
                </svg>
              </div>
            </div>
          </div>

          <div className="bg-white rounded-lg shadow p-6">
            <div className="flex items-center">
              <div className="flex-1">
                <p className="text-sm font-medium text-gray-600">
                  Toplam Tutar
                </p>
                <p className="text-2xl font-bold text-gray-900 mt-1">
                  {formatCurrency(summary.total_amount)}
                </p>
              </div>
              <div className="ml-4 bg-green-100 rounded-full p-3">
                <svg
                  className="w-6 h-6 text-green-600"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
              </div>
            </div>
          </div>

          <div className="bg-white rounded-lg shadow p-6">
            <div className="flex items-center">
              <div className="flex-1">
                <p className="text-sm font-medium text-gray-600">
                  Bu Ay
                </p>
                <p className="text-2xl font-bold text-gray-900 mt-1">
                  {formatCurrency(summary.monthly_amount)}
                </p>
              </div>
              <div className="ml-4 bg-purple-100 rounded-full p-3">
                <svg
                  className="w-6 h-6 text-purple-600"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"
                  />
                </svg>
              </div>
            </div>
          </div>

          <div className="bg-white rounded-lg shadow p-6">
            <div className="flex items-center">
              <div className="flex-1">
                <p className="text-sm font-medium text-gray-600">
                  Bekleyen KDV
                </p>
                <p className="text-2xl font-bold text-gray-900 mt-1">
                  {formatCurrency(summary.pending_kdv)}
                </p>
              </div>
              <div className="ml-4 bg-yellow-100 rounded-full p-3">
                <svg
                  className="w-6 h-6 text-yellow-600"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
              </div>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-lg shadow mb-6">
          <div className="p-6 border-b border-gray-200">
            <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
              <div className="flex-1">
                <input
                  type="text"
                  placeholder="Fatura ara (tedarikçi, dosya adı...)"
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
              </div>

              <div className="flex flex-col sm:flex-row gap-4">
                <select
                  className="px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                >
                  <option value="all">Tüm Durumlar</option>
                  <option value="uploaded">Yüklendi</option>
                  <option value="processing">İşleniyor</option>
                  <option value="processed">İşlendi</option>
                  <option value="pending_review">İnceleme Bekliyor</option>
                  <option value="exported">Aktarıldı</option>
                  <option value="failed">Hatalı</option>
                </select>

                <input
                  type="date"
                  className="px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  value={dateFrom}
                  onChange={(e) => setDateFrom(e.target.value)}
                  placeholder="Başlangıç"
                />

                <input
                  type="date"
                  className="px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  value={dateTo}
                  onChange={(e) => setDateTo(e.target.value)}
                  placeholder="Bitiş"
                />

                <button
                  onClick={handleRefresh}