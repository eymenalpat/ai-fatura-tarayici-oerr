'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter, useParams } from 'next/navigation';
import { useForm } from 'react-hook-form';
import { apiClient } from '@/lib/api-client';
import Image from 'next/image';

interface ExtractedData {
  supplier_name?: string;
  supplier_tax_number?: string;
  supplier_address?: string;
  invoice_number?: string;
  invoice_date?: string;
  due_date?: string;
  currency?: string;
  subtotal?: number;
  kdv_rate?: number;
  kdv_amount?: number;
  total_amount?: number;
  line_items?: Array<{
    description: string;
    quantity: number;
    unit_price: number;
    amount: number;
  }>;
}

interface Invoice {
  id: string;
  filename: string;
  file_url: string;
  status: string;
  supplier_name: string | null;
  invoice_number: string | null;
  invoice_date: string | null;
  total_amount: number | null;
  extracted_data: ExtractedData | null;
  created_at: string;
  updated_at: string;
}

interface FormData {
  supplier_name: string;
  supplier_tax_number: string;
  supplier_address: string;
  invoice_number: string;
  invoice_date: string;
  due_date: string;
  currency: string;
  subtotal: number;
  kdv_rate: number;
  kdv_amount: number;
  total_amount: number;
}

export default function InvoiceEditPage() {
  const router = useRouter();
  const params = useParams();
  const id = params.id as string;

  const [invoice, setInvoice] = useState<Invoice | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [imageScale, setImageScale] = useState(1);
  const [imagePosition, setImagePosition] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [kdvWarning, setKdvWarning] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const { register, handleSubmit, watch, setValue, formState: { errors } } = useForm<FormData>();

  const subtotal = watch('subtotal');
  const kdvRate = watch('kdv_rate');
  const kdvAmount = watch('kdv_amount');
  const totalAmount = watch('total_amount');

  useEffect(() => {
    loadInvoice();
  }, [id]);

  useEffect(() => {
    if (subtotal && kdvRate !== undefined) {
      const calculatedKdvAmount = Number((subtotal * kdvRate / 100).toFixed(2));
      const calculatedTotal = Number((subtotal + calculatedKdvAmount).toFixed(2));

      if (kdvAmount && Math.abs(kdvAmount - calculatedKdvAmount) > 0.01) {
        setKdvWarning(`KDV tutarı hesaplananla uyuşmuyor. Hesaplanan: ${calculatedKdvAmount.toFixed(2)} ${watch('currency') || 'TRY'}`);
      } else if (totalAmount && Math.abs(totalAmount - calculatedTotal) > 0.01) {
        setKdvWarning(`Toplam tutar hesaplananla uyuşmuyor. Hesaplanan: ${calculatedTotal.toFixed(2)} ${watch('currency') || 'TRY'}`);
      } else {
        setKdvWarning(null);
      }
    }
  }, [subtotal, kdvRate, kdvAmount, totalAmount]);

  const loadInvoice = async () => {
    try {
      setLoading(true);
      const response = await apiClient.get(`/invoices/${id}`);
      const invoiceData: Invoice = response.data;
      setInvoice(invoiceData);

      if (invoiceData.extracted_data) {
        const data = invoiceData.extracted_data;
        setValue('supplier_name', data.supplier_name || '');
        setValue('supplier_tax_number', data.supplier_tax_number || '');
        setValue('supplier_address', data.supplier_address || '');
        setValue('invoice_number', data.invoice_number || '');
        setValue('invoice_date', data.invoice_date || '');
        setValue('due_date', data.due_date || '');
        setValue('currency', data.currency || 'TRY');
        setValue('subtotal', data.subtotal || 0);
        setValue('kdv_rate', data.kdv_rate || 20);
        setValue('kdv_amount', data.kdv_amount || 0);
        setValue('total_amount', data.total_amount || 0);
      }
    } catch (error: any) {
      console.error('Failed to load invoice:', error);
      setErrorMessage(error.response?.data?.detail || 'Fatura yüklenirken hata oluştu');
    } finally {
      setLoading(false);
    }
  };

  const onSubmit = async (data: FormData) => {
    try {
      setSaving(true);
      setSuccessMessage(null);
      setErrorMessage(null);

      const updateData = {
        extracted_data: {
          supplier_name: data.supplier_name,
          supplier_tax_number: data.supplier_tax_number,
          supplier_address: data.supplier_address,
          invoice_number: data.invoice_number,
          invoice_date: data.invoice_date,
          due_date: data.due_date,
          currency: data.currency,
          subtotal: Number(data.subtotal),
          kdv_rate: Number(data.kdv_rate),
          kdv_amount: Number(data.kdv_amount),
          total_amount: Number(data.total_amount),
          line_items: invoice?.extracted_data?.line_items || []
        },
        supplier_name: data.supplier_name,
        invoice_number: data.invoice_number,
        invoice_date: data.invoice_date,
        total_amount: Number(data.total_amount)
      };

      await apiClient.put(`/invoices/${id}`, updateData);
      setSuccessMessage('Fatura başarıyla güncellendi');
      await loadInvoice();
    } catch (error: any) {
      console.error('Failed to save invoice:', error);
      setErrorMessage(error.response?.data?.detail || 'Fatura kaydedilirken hata oluştu');
    } finally {
      setSaving(false);
    }
  };

  const handleExportToParasut = async () => {
    try {
      setExporting(true);
      setSuccessMessage(null);
      setErrorMessage(null);

      await apiClient.post(`/invoices/${id}/export`);
      setSuccessMessage('Fatura Parasüt\'e başarıyla aktarıldı');
      await loadInvoice();
    } catch (error: any) {
      console.error('Failed to export to Parasut:', error);
      setErrorMessage(error.response?.data?.detail || 'Parasüt\'e aktarım sırasında hata oluştu');
    } finally {
      setExporting(false);
    }
  };

  const handleZoomIn = () => {
    setImageScale(prev => Math.min(prev + 0.2, 3));
  };

  const handleZoomOut = () => {
    setImageScale(prev => Math.max(prev - 0.2, 0.5));
  };

  const handleResetZoom = () => {
    setImageScale(1);
    setImagePosition({ x: 0, y: 0 });
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    setIsDragging(true);
    setDragStart({ x: e.clientX - imagePosition.x, y: e.clientY - imagePosition.y });
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (isDragging) {
      setImagePosition({
        x: e.clientX - dragStart.x,
        y: e.clientY - dragStart.y
      });
    }
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  const calculateKdvFromSubtotal = () => {
    if (subtotal && kdvRate !== undefined) {
      const calculatedKdv = Number((subtotal * kdvRate / 100).toFixed(2));
      const calculatedTotal = Number((subtotal + calculatedKdv).toFixed(2));
      setValue('kdv_amount', calculatedKdv);
      setValue('total_amount', calculatedTotal);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Fatura yükleniyor...</p>
        </div>
      </div>
    );
  }

  if (!invoice) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <p className="text-red-600 text-xl">Fatura bulunamadı</p>
          <button
            onClick={() => router.push('/dashboard')}
            className="mt-4 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
          >
            Panele Dön
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <button
              onClick={() => router.push('/dashboard')}
              className="text-blue-600 hover:text-blue-700 flex items-center mb-2"
            >
              ← Panele Dön
            </button>
            <h1 className="text-3xl font-bold text-gray-900">Fatura Düzenle</h1>
            <p className="text-gray-600 mt-1">{invoice.filename}</p>
          </div>
          <div className="flex gap-3">
            <button
              onClick={handleSubmit(onSubmit)}
              disabled={saving}
              className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
            >
              {saving ? 'Kaydediliyor...' : 'Kaydet'}
            </button>
            <button
              onClick={handleExportToParasut}
              disabled={exporting || invoice.status === 'exported'}
              className="px-6 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
            >
              {exporting ? 'Aktarılıyor...' : invoice.status === 'exported' ? 'Aktarıldı' : 'Parasüt\'e Aktar'}
            </button>
          </div>
        </div>

        {successMessage && (
          <div className="mb-4 p-4 bg-green-50 border border-green-200 rounded-lg text-green-800">
            {successMessage}
          </div>
        )}

        {errorMessage && (
          <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg text-red-800">
            {errorMessage}
          </div>
        )}

        {kdvWarning && (
          <div className="mb-4 p-4 bg-yellow-50 border border-yellow-200 rounded-lg text-yellow-800">
            <strong>Uyarı:</strong> {kdvWarning}
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-white rounded-lg shadow-md p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold text-gray-900">Fatura Görseli</h2>
              <div className="flex gap-2">
                <button
                  onClick={handleZoomOut}
                  className="p-2 border border-gray-300 rounded hover:bg-gray-50"
                  title="Uzaklaştır"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0zM13 10H7" />
                  </svg>
                </button>
                <button
                  onClick={handleResetZoom}
                  className="px-3 py-2 border border-gray-300 rounded hover:bg-gray-50 text-sm"
                >
                  Sıfırla
                </button>
                <button
                  onClick={handleZoomIn}
                  className="p-2 border border-gray-300 rounded hover:bg-gray-50"
                  title="Yakınlaştır"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0zM10 7v3m0 0v3m0-3h3m-3 0H7" />
                  </svg>
                </button>
              </div>
            </div>

            <div 
              className="border border-gray-300 rounded-lg overflow-hidden bg-gray-100 relative"
              style={{ height: '700px', cursor: isDragging ? 'grabbing' : 'grab' }}
              onMouseDown={handleMouseDown}
              onMouseMove={handleMouseMove}
              onMouseUp={handleMouseUp}
              onMouseLeave={handleMouseUp}
            >
              {invoice.file_url && (
                <div
                  style={{
                    transform: `translate(${imagePosition.x}px, ${imagePosition.y}px) scale(${imageScale})`,
                    transformOrigin: 'center center',
                    transition: isDragging ? 'none' : 'transform 0.1s',
                    position: 'absolute