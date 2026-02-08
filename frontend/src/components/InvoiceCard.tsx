import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { MoreVertical, Edit, Trash2, Send, AlertCircle } from 'lucide-react';
import { apiClient } from '@/lib/api-client';

export interface InvoiceCardProps {
  id: string;
  filename: string;
  status: string;
  total_amount: number | null;
  invoice_date: string | null;
  supplier_name: string | null;
  created_at: string;
  updated_at: string;
  extracted_data?: any;
  onDelete?: () => void;
  onExport?: () => void;
}

const statusConfig = {
  uploaded: { label: 'Yüklendi', color: 'bg-gray-100 text-gray-800' },
  processing: { label: 'İşleniyor', color: 'bg-blue-100 text-blue-800' },
  extracted: { label: 'Çıkarıldı', color: 'bg-yellow-100 text-yellow-800' },
  validated: { label: 'Doğrulandı', color: 'bg-green-100 text-green-800' },
  exported: { label: 'Aktarıldı', color: 'bg-purple-100 text-purple-800' },
  error: { label: 'Hata', color: 'bg-red-100 text-red-800' },
};

export const InvoiceCard: React.FC<InvoiceCardProps> = ({
  id,
  filename,
  status,
  total_amount,
  invoice_date,
  supplier_name,
  created_at,
  updated_at,
  extracted_data,
  onDelete,
  onExport,
}) => {
  const router = useRouter();
  const [showMenu, setShowMenu] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const statusInfo = statusConfig[status as keyof typeof statusConfig] || statusConfig.uploaded;

  const formatDate = (dateString: string | null) => {
    if (!dateString) return '-';
    try {
      return new Date(dateString).toLocaleDateString('tr-TR', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      });
    } catch {
      return '-';
    }
  };

  const formatAmount = (amount: number | null) => {
    if (amount === null || amount === undefined) return '-';
    return new Intl.NumberFormat('tr-TR', {
      style: 'currency',
      currency: 'TRY',
    }).format(amount);
  };

  const handleEdit = () => {
    setShowMenu(false);
    router.push(`/invoice/${id}/edit`);
  };

  const handleDelete = async () => {
    setIsDeleting(true);
    setError(null);

    try {
      await apiClient.delete(`/invoices/${id}`);
      setShowDeleteConfirm(false);
      setShowMenu(false);
      if (onDelete) {
        onDelete();
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Fatura silinirken bir hata oluştu');
    } finally {
      setIsDeleting(false);
    }
  };

  const handleExport = async () => {
    setIsExporting(true);
    setError(null);
    setShowMenu(false);

    try {
      await apiClient.post(`/invoices/${id}/export`);
      if (onExport) {
        onExport();
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Fatura aktarılırken bir hata oluştu');
    } finally {
      setIsExporting(false);
    }
  };

  const handleCardClick = () => {
    router.push(`/invoice/${id}/edit`);
  };

  return (
    <>
      <div className="bg-white rounded-lg shadow hover:shadow-md transition-shadow border border-gray-200 relative">
        <div className="p-6 cursor-pointer" onClick={handleCardClick}>
          <div className="flex items-start justify-between mb-4">
            <div className="flex-1">
              <h3 className="text-lg font-semibold text-gray-900 mb-1 truncate">
                {filename}
              </h3>
              <p className="text-sm text-gray-600 truncate">
                {supplier_name || 'Tedarikçi belirtilmemiş'}
              </p>
            </div>
            <div className="relative ml-2" onClick={(e) => e.stopPropagation()}>
              <button
                onClick={() => setShowMenu(!showMenu)}
                className="p-2 hover:bg-gray-100 rounded-full transition-colors"
              >
                <MoreVertical className="w-5 h-5 text-gray-600" />
              </button>
              {showMenu && (
                <>
                  <div
                    className="fixed inset-0 z-10"
                    onClick={() => setShowMenu(false)}
                  />
                  <div className="absolute right-0 top-full mt-1 w-48 bg-white rounded-md shadow-lg border border-gray-200 py-1 z-20">
                    <button
                      onClick={handleEdit}
                      className="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-100 flex items-center gap-2"
                    >
                      <Edit className="w-4 h-4" />
                      Düzenle
                    </button>
                    <button
                      onClick={() => {
                        setShowDeleteConfirm(true);
                        setShowMenu(false);
                      }}
                      className="w-full px-4 py-2 text-left text-sm text-red-600 hover:bg-red-50 flex items-center gap-2"
                    >
                      <Trash2 className="w-4 h-4" />
                      Sil
                    </button>
                    {status === 'validated' && (
                      <button
                        onClick={handleExport}
                        disabled={isExporting}
                        className="w-full px-4 py-2 text-left text-sm text-purple-600 hover:bg-purple-50 flex items-center gap-2 disabled:opacity-50"
                      >
                        <Send className="w-4 h-4" />
                        {isExporting ? 'Aktarılıyor...' : "Parasüt'e Aktar"}
                      </button>
                    )}
                  </div>
                </>
              )}
            </div>
          </div>

          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-600">Durum:</span>
              <span className={`px-3 py-1 rounded-full text-xs font-medium ${statusInfo.color}`}>
                {statusInfo.label}
              </span>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-600">Tutar:</span>
              <span className="text-lg font-semibold text-gray-900">
                {formatAmount(total_amount)}
              </span>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-600">Fatura Tarihi:</span>
              <span className="text-sm text-gray-900">
                {formatDate(invoice_date)}
              </span>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-600">Yüklenme:</span>
              <span className="text-sm text-gray-900">
                {formatDate(created_at)}
              </span>
            </div>
          </div>

          {error && (
            <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-md flex items-start gap-2">
              <AlertCircle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
              <p className="text-sm text-red-800">{error}</p>
            </div>
          )}
        </div>
      </div>

      {showDeleteConfirm && (
        <>
          <div
            className="fixed inset-0 bg-black bg-opacity-50 z-40"
            onClick={() => !isDeleting && setShowDeleteConfirm(false)}
          />
          <div className="fixed inset-0 flex items-center justify-center z-50 p-4">
            <div className="bg-white rounded-lg shadow-xl max-w-md w-full p-6">
              <h3 className="text-lg font-semibold text-gray-900 mb-2">
                Faturayı Sil
              </h3>
              <p className="text-sm text-gray-600 mb-6">
                Bu faturayı silmek istediğinizden emin misiniz? Bu işlem geri alınamaz.
              </p>
              <div className="flex gap-3 justify-end">
                <button
                  onClick={() => setShowDeleteConfirm(false)}
                  disabled={isDeleting}
                  className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50"
                >
                  İptal
                </button>
                <button
                  onClick={handleDelete}
                  disabled={isDeleting}
                  className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-md hover:bg-red-700 disabled:opacity-50 flex items-center gap-2"
                >
                  {isDeleting ? (
                    <>
                      <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                      Siliniyor...
                    </>
                  ) : (
                    'Sil'
                  )}
                </button>
              </div>
            </div>
          </div>
        </>
      )}
    </>
  );
};