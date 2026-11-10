import React, { useState, useEffect, useCallback, useRef } from 'react';
import { 
  BookOpen, Plus, Search, Filter, RefreshCw, FileText, 
  Globe, Edit3, Trash2, Tag, Calendar, ChevronRight, Loader2,
  AlertCircle
} from 'lucide-react';
import { api } from '../api/client';
import StatusBadge from '../components/StatusBadge';

export default function LibraryPage({ onSelectDocument, onNavigateAdd }) {
  const [documents, setDocuments] = useState([]);
  const [tags, setTags] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  
  // Filters
  const [statusFilter, setStatusFilter] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [tagFilter, setTagFilter] = useState('');
  const [sourceTypeFilter, setSourceTypeFilter] = useState('');
  
  const pollingRef = useRef(null);

  const fetchDocuments = useCallback(async (isPolling = false) => {
    try {
      if (!isPolling) setLoading(true);
      const params = {};
      if (statusFilter) params.status = statusFilter;
      if (categoryFilter) params.category = categoryFilter;
      if (tagFilter) params.tag = tagFilter;
      if (sourceTypeFilter) params.source_type = sourceTypeFilter;

      const data = await api.getDocuments(params);
      setDocuments(data || []);
      setError(null);
    } catch (err) {
      if (!isPolling) {
        setError(err.message || 'Failed to load documents');
      }
    } finally {
      if (!isPolling) setLoading(false);
    }
  }, [statusFilter, categoryFilter, tagFilter, sourceTypeFilter]);

  const fetchTags = async () => {
    try {
      const tagList = await api.getTags();
      setTags(tagList || []);
    } catch {
      // Non-blocking
    }
  };

  useEffect(() => {
    fetchDocuments();
    fetchTags();
  }, [fetchDocuments]);

  // Auto-polling for pending or processing documents
  useEffect(() => {
    const hasUnfinishedDocs = documents.some(
      (doc) => doc.status === 'pending' || doc.status === 'processing'
    );

    if (hasUnfinishedDocs) {
      pollingRef.current = setInterval(() => {
        fetchDocuments(true);
      }, 3000);
    } else {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    }

    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
      }
    };
  }, [documents, fetchDocuments]);

  const handleDelete = async (e, docId, docTitle) => {
    e.stopPropagation();
    if (!window.confirm(`Are you sure you want to delete "${docTitle}"?`)) return;

    try {
      await api.deleteDocument(docId);
      setDocuments((prev) => prev.filter((d) => d.id !== docId));
    } catch (err) {
      alert(`Failed to delete document: ${err.message}`);
    }
  };

  const getSourceIcon = (type) => {
    switch (type) {
      case 'pdf':
        return <FileText className="w-5 h-5 text-rose-500" />;
      case 'link':
        return <Globe className="w-5 h-5 text-sky-500" />;
      case 'note':
      default:
        return <Edit3 className="w-5 h-5 text-indigo-500" />;
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
            Knowledge Library
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Manage, organize, and monitor ingestion of your indexed documents.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => fetchDocuments()}
            className="p-2 text-slate-500 hover:text-slate-800 hover:bg-slate-100 rounded-xl transition-colors"
            title="Refresh documents"
          >
            <RefreshCw className={`w-5 h-5 ${loading ? 'animate-spin' : ''}`} />
          </button>
          <button
            onClick={onNavigateAdd}
            className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold rounded-xl shadow-sm shadow-indigo-100 transition-all hover:shadow"
          >
            <Plus className="w-4 h-4" />
            <span>Add Content</span>
          </button>
        </div>
      </div>

      {/* Filter Bar */}
      <div className="bg-white p-4 rounded-2xl border border-slate-200/80 shadow-sm mb-6 flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2 text-xs font-semibold text-slate-500 uppercase tracking-wider mr-2">
          <Filter className="w-3.5 h-3.5" />
          <span>Filters</span>
        </div>

        {/* Status Filter */}
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="text-xs bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 font-medium text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
        >
          <option value="">All Statuses</option>
          <option value="ready">Ready</option>
          <option value="processing">Processing</option>
          <option value="pending">Pending</option>
          <option value="failed">Failed</option>
        </select>

        {/* Source Type Filter */}
        <select
          value={sourceTypeFilter}
          onChange={(e) => setSourceTypeFilter(e.target.value)}
          className="text-xs bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 font-medium text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
        >
          <option value="">All Sources</option>
          <option value="pdf">PDF Documents</option>
          <option value="link">Web Links</option>
          <option value="note">Notes</option>
        </select>

        {/* Tag Filter */}
        {tags.length > 0 && (
          <select
            value={tagFilter}
            onChange={(e) => setTagFilter(e.target.value)}
            className="text-xs bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 font-medium text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
          >
            <option value="">All Tags</option>
            {tags.map((t) => (
              <option key={t.id} value={t.name}>
                #{t.name}
              </option>
            ))}
          </select>
        )}

        {(statusFilter || sourceTypeFilter || tagFilter || categoryFilter) && (
          <button
            onClick={() => {
              setStatusFilter('');
              setSourceTypeFilter('');
              setTagFilter('');
              setCategoryFilter('');
            }}
            className="text-xs text-indigo-600 hover:text-indigo-800 font-semibold px-2 py-1"
          >
            Reset Filters
          </button>
        )}
      </div>

      {/* Error state */}
      {error && (
        <div className="mb-6 p-4 rounded-xl bg-rose-50 border border-rose-200 flex items-center gap-3 text-rose-700 text-sm">
          <AlertCircle className="w-5 h-5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Content */}
      {loading && documents.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-slate-400">
          <Loader2 className="w-8 h-8 animate-spin text-indigo-600 mb-3" />
          <p className="text-sm font-medium">Loading documents...</p>
        </div>
      ) : documents.length === 0 ? (
        <div className="bg-white rounded-2xl border border-dashed border-slate-200 p-12 text-center max-w-lg mx-auto">
          <div className="w-12 h-12 rounded-2xl bg-indigo-50 text-indigo-600 flex items-center justify-center mx-auto mb-4">
            <BookOpen className="w-6 h-6" />
          </div>
          <h3 className="text-base font-semibold text-slate-800 mb-1">
            No documents found
          </h3>
          <p className="text-xs text-slate-500 mb-6 leading-relaxed">
            {statusFilter || sourceTypeFilter || tagFilter
              ? 'No documents match your active filters. Try clearing some filters.'
              : 'Your library is empty. Upload a PDF, save an online article, or create your first note to get started.'}
          </p>
          <button
            onClick={onNavigateAdd}
            className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold rounded-xl shadow-sm transition-all"
          >
            <Plus className="w-4 h-4" />
            <span>Add First Document</span>
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {documents.map((doc) => (
            <div
              key={doc.id}
              onClick={() => onSelectDocument(doc.id)}
              className="group bg-white rounded-2xl border border-slate-200/80 p-5 shadow-sm hover:shadow-md hover:border-indigo-200 transition-all cursor-pointer flex flex-col justify-between"
            >
              <div>
                {/* Card Top: Source Icon, Status, Category */}
                <div className="flex items-center justify-between gap-2 mb-3">
                  <div className="flex items-center gap-2">
                    <div className="p-2 bg-slate-50 rounded-xl group-hover:bg-indigo-50/50 transition-colors">
                      {getSourceIcon(doc.source_type)}
                    </div>
                    {doc.category && (
                      <span className="text-[11px] font-semibold tracking-wide text-slate-500 uppercase bg-slate-100 px-2 py-0.5 rounded-md">
                        {doc.category}
                      </span>
                    )}
                  </div>
                  <StatusBadge status={doc.status} />
                </div>

                {/* Title */}
                <h3 className="font-semibold text-slate-900 group-hover:text-indigo-600 transition-colors text-base line-clamp-2 mb-2">
                  {doc.title || 'Untitled Document'}
                </h3>

                {/* AI Summary Preview (if available) */}
                {doc.summary && (
                  <p className="text-xs text-slate-600 line-clamp-3 mb-3 leading-relaxed bg-slate-50/80 p-2.5 rounded-xl border border-slate-100">
                    {doc.summary}
                  </p>
                )}

                {/* Tags */}
                {doc.tags && doc.tags.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mb-3">
                    {doc.tags.map((t) => (
                      <span
                        key={t.id || t.name}
                        className="inline-flex items-center gap-1 text-[11px] font-medium text-indigo-700 bg-indigo-50/60 px-2 py-0.5 rounded-full"
                      >
                        <Tag className="w-2.5 h-2.5 text-indigo-500" />
                        {t.name}
                      </span>
                    ))}
                  </div>
                )}
              </div>

              {/* Card Footer */}
              <div className="pt-4 border-t border-slate-100 flex items-center justify-between text-xs text-slate-400 mt-2">
                <div className="flex items-center gap-1.5">
                  <Calendar className="w-3.5 h-3.5" />
                  <span>
                    {doc.created_at
                      ? new Date(doc.created_at).toLocaleDateString(undefined, {
                          month: 'short',
                          day: 'numeric',
                          year: 'numeric',
                        })
                      : 'Just now'}
                  </span>
                </div>
                <div className="flex items-center gap-1">
                  <button
                    onClick={(e) => handleDelete(e, doc.id, doc.title)}
                    title="Delete document"
                    className="p-1.5 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition-colors"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                  <span className="p-1.5 text-slate-300 group-hover:text-indigo-600 group-hover:translate-x-0.5 transition-all">
                    <ChevronRight className="w-4 h-4" />
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
