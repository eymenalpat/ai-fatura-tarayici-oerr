'use client';

import { useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useDropzone } from 'react-dropzone';
import { apiClient } from '@/lib/api-client';

interface UploadedFile {
  file: File;
  id: string;
  progress: number;
  status: 'uploading' | 'processing' | 'completed' | 'error';
  invoiceId?: string;
  error?: string;
}

export default function UploadPage() {
  const router = useRouter();
  const [files, setFiles] = useState<UploadedFile[]>([]);
  const [isUploading, setIsUploading] = useState(false);

  const pollInvoiceStatus = async (invoiceId: string, fileId: string) => {
    const maxAttempts = 60;
    let attempts = 0;

    const poll = async () => {
      try {
        const response = await apiClient.get(`/invoices/${invoiceId}/status`);
        const status = response.data.status;

        if (status === 'completed' || status === 'extracted') {
          setFiles(prev => prev.map(f => 
            f.id === fileId 
              ? { ...f, status: 'completed', progress: 100 }
              : f
          ));
          
          setTimeout(() => {
            router.push(`/invoice/${invoiceId}/edit`);
          }, 1000);
          
          return true;
        } else if (status === 'failed' || status === 'error') {
          setFiles(prev => prev.map(f => 
            f.id === fileId 
              ? { ...f, status: 'error', error: 'İşleme sırasında hata oluştu' }
              : f
          ));
          return true;
        } else {
          attempts++;
          if (attempts < maxAttempts) {
            setTimeout(poll, 2000);
          } else {
            setFiles(prev => prev.map(f => 
              f.id === fileId 
                ? { ...f, status: 'error', error: 'İşlem zaman aşımına uğradı' }
                : f
            ));
          }
        }
      } catch (error: any) {
        console.error('Polling error:', error);
        setFiles(prev => prev.map(f => 
          f.id === fileId 
            ? { ...f, status: 'error', error: 'Durum kontrol edilemedi' }
            : f
        ));
      }
    };

    poll();
  };

  const uploadFile = async (file: File) => {
    const fileId = `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    
    setFiles(prev => [...prev, {
      file,
      id: fileId,
      progress: 0,
      status: 'uploading'
    }]);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await apiClient.post('/invoices/upload', formData, {
        headers: {
          'Content-Type': 'multipart/form-data'
        },
        onUploadProgress: (progressEvent) => {
          const percentCompleted = progressEvent.total
            ? Math.round((progressEvent.loaded * 100) / progressEvent.total)
            : 0;
          
          setFiles(prev => prev.map(f => 
            f.id === fileId 
              ? { ...f, progress: percentCompleted }
              : f
          ));
        }
      });

      const invoiceId = response.data.invoice_id;

      setFiles(prev => prev.map(f => 
        f.id === fileId 
          ? { ...f, status: 'processing', invoiceId, progress: 100 }
          : f
      ));

      pollInvoiceStatus(invoiceId, fileId);

    } catch (error: any) {
      console.error('Upload error:', error);
      const errorMessage = error.response?.data?.detail || 'Yükleme başarısız oldu';
      
      setFiles(prev => prev.map(f => 
        f.id === fileId 
          ? { ...f, status: 'error', error: errorMessage }
          : f
      ));
    }
  };

  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    if (isUploading) return;

    const validFiles = acceptedFiles.filter(file => {
      const isValidType = ['image/jpeg', 'image/png', 'application/pdf'].includes(file.type);
      const isValidSize = file.size <= 10 * 1024 * 1024;
      
      if (!isValidType) {
        alert(`${file.name}: Geçersiz dosya formatı. Sadece JPEG, PNG ve PDF kabul edilir.`);
        return false;
      }
      
      if (!isValidSize) {
        alert(`${file.name}: Dosya boyutu 10MB'ı aşamaz.`);
        return false;
      }
      
      return true;
    });

    if (validFiles.length === 0) return;

    setIsUploading(true);

    for (const file of validFiles) {
      await uploadFile(file);
    }

    setIsUploading(false);
  }, [isUploading]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'image/jpeg': ['.jpg', '.jpeg'],
      'image/png': ['.png'],
      'application/pdf': ['.pdf']
    },
    maxSize: 10 * 1024 * 1024,
    multiple: true,
    disabled: isUploading
  });

  const removeFile = (fileId: string) => {
    setFiles(prev => prev.filter(f => f.id !== fileId));
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
  };

  const getStatusText = (status: string): string => {
    switch (status) {
      case 'uploading': return 'Yükleniyor...';
      case 'processing': return 'İşleniyor...';
      case 'completed': return 'Tamamlandı';
      case 'error': return 'Hata';
      default: return 'Bekliyor';
    }
  };

  const getStatusColor = (status: string): string => {
    switch (status) {
      case 'uploading': return 'bg-blue-500';
      case 'processing': return 'bg-yellow-500';
      case 'completed': return 'bg-green-500';
      case 'error': return 'bg-red-500';
      default: return 'bg-gray-500';
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 py-8">
      <div className="max-w-4xl mx-auto px-4">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">Fatura Yükle</h1>
          <p className="text-gray-600">
            Fatura dosyalarınızı sürükleyip bırakın veya seçin. JPEG, PNG ve PDF formatları desteklenir (max 10MB).
          </p>
        </div>

        <div
          {...getRootProps()}
          className={`
            border-2 border-dashed rounded-lg p-12 text-center cursor-pointer
            transition-colors duration-200
            ${isDragActive 
              ? 'border-blue-500 bg-blue-50' 
              : 'border-gray-300 bg-white hover:border-gray-400'
            }
            ${isUploading ? 'opacity-50 cursor-not-allowed' : ''}
          `}
        >
          <input {...getInputProps()} />
          <div className="flex flex-col items-center">
            <svg
              className={`w-16 h-16 mb-4 ${isDragActive ? 'text-blue-500' : 'text-gray-400'}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
              />
            </svg>
            <p className="text-lg font-medium text-gray-700 mb-2">
              {isDragActive
                ? 'Dosyaları buraya bırakın...'
                : 'Dosyaları sürükleyin veya tıklayın'}
            </p>
            <p className="text-sm text-gray-500">
              JPEG, PNG, PDF (Maksimum 10MB)
            </p>
          </div>
        </div>

        {files.length > 0 && (
          <div className="mt-8 space-y-4">
            <h2 className="text-xl font-semibold text-gray-900 mb-4">
              Yüklenen Dosyalar ({files.length})
            </h2>
            
            {files.map((fileItem) => (
              <div
                key={fileItem.id}
                className="bg-white rounded-lg shadow p-4 border border-gray-200"
              >
                <div className="flex items-start justify-between mb-3">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-900 truncate">
                      {fileItem.file.name}
                    </p>
                    <p className="text-xs text-gray-500 mt-1">
                      {formatFileSize(fileItem.file.size)}
                    </p>
                  </div>
                  
                  <div className="flex items-center gap-3 ml-4">
                    <span className={`
                      px-3 py-1 rounded-full text-xs font-medium text-white
                      ${getStatusColor(fileItem.status)}
                    `}>
                      {getStatusText(fileItem.status)}
                    </span>
                    
                    {fileItem.status === 'error' && (
                      <button
                        onClick={() => removeFile(fileItem.id)}
                        className="text-gray-400 hover:text-gray-600"
                      >
                        <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                          <path
                            fillRule="evenodd"
                            d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
                            clipRule="evenodd"
                          />
                        </svg>
                      </button>
                    )}
                  </div>
                </div>

                {fileItem.status !== 'error' && (
                  <div className="w-full bg-gray-200 rounded-full h-2">
                    <div
                      className={`h-2 rounded-full transition-all duration-300 ${
                        fileItem.status === 'completed' 
                          ? 'bg-green-500' 
                          : fileItem.status === 'processing'
                          ? 'bg-yellow-500'
                          : 'bg-blue-500'
                      }`}
                      style={{ width: `${fileItem.progress}%` }}
                    />
                  </div>
                )}

                {fileItem.error && (
                  <div className="mt-2 text-sm text-red-600">
                    {fileItem.error}
                  </div>
                )}

                {fileItem.status === 'processing' && (
                  <div className="mt-2 text-sm text-gray-600">
                    <div className="flex items-center gap-2">
                      <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                        <circle
                          className="opacity-25"
                          cx="12"
                          cy="12"
                          r="10"
                          stroke="currentColor"
                          strokeWidth="4"
                          fill="none"
                        />
                        <path
                          className="opacity-75"
                          fill="currentColor"
                          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                        />
                      </svg>
                      <span>OCR ve AI ile fatura bilgileri çıkarılıyor...</span>
                    </div>
                  </div>
                )}

                {fileItem.status === 'completed' && fileItem.invoiceId && (
                  <div className="mt-2">
                    <button
                      onClick={() => router.push(`/invoice/${fileItem.invoiceId}/edit`)}
                      className="text-sm text-blue-600 hover:text-blue-800 font-medium"
                    >
                      Faturayı Düzenle →
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {files.length === 0 && (
          <div className="mt-8 text-center text-gray-500">
            <p>Henüz dosya yüklenmedi</p>
          </div>
        )}
      </div>
    </div>
  );
}