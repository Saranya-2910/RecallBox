import React, { useState, useEffect, useCallback } from 'react';
import { 
  ArrowLeft, FileText, Globe, Edit3, Trash2, RefreshCw, 
  Tag as TagIcon, Plus, X, Sparkles, BookOpen, ExternalLink, 
  Loader2, AlertCircle, Calendar, Hash, Layers
} from 'lucide-react';
import { api } from '../api/client';
import StatusBadge from '../components/StatusBadge';

export default function DocumentDetailPage({ documentId, onBack, onSelectDocument }) {
  const [document, setDocument] = useState(null);
  const [relatedDocs, setRelatedDocs] = useState([]);
  const [newTagName, setNewTagName] = useState('');
  const [loading, setLoading] = useState(true);
  const [reprocessing, setReprocessing] = useState(false);
  const [tagLoading, setTagLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchDocumentData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const [docData, relatedData] = await Promise.all([
        api.getDocument(documentId),
        api.getRelatedDocuments(documentId).catch(() => ({ related: [] })),
      ]);
      setDocument(docData);
      setRelatedDocs(Array.isArray(relatedData) ? relatedData : (relatedData?.related || []));
    } catch (err) {
      setError(err.message || 'Failed to load document details');
    } finally {
      setLoading(false);
    }
  }, [documentId]);

  useEffect(() => {
    fetchDocumentData();
  }, [fetchDocumentData]);

  // Handle Tag addition
  const handleAddTag = async (e) => {
    e.preventDefault();
    if (!newTagName.trim()) return;

    try {
      setTagLoading(true);
      const addedTag = await api.addTag(documentId, newTagName.trim());
      setDocument((prev) => {
        const existing = Array.isArray(prev?.tags) ? prev.tags : [];
        const alreadyPresent = existing.some((t) => t.id === addedTag.id);
        return {
          ...prev,
          tags: alreadyPresent ? existing : [...existing, addedTag],
        };
      });
      setNewTagName('');
    } catch (err) {
      alert(`Failed to add tag: ${err.message}`);
    } finally {
      setTagLoading(false);
    }
  };

  // Handle Tag removal
  const handleRemoveTag = async (tagId) => {
    try {
      await api.removeTag(documentId, tagId);
      setDocument((prev) => ({
        ...prev,
        tags: prev.tags.filter((t) => t.id !== tagId),
      }));
    } catch (err) {
      alert(`Failed to remove tag: ${err.message}`);
    }
  };

  // Handle Reprocess
  const handleReprocess = async () => {
    try {
      setReprocessing(true);
      await api.reprocessDocument(documentId);
      await fetchDocumentData();
    } catch (err) {
      alert(`Failed to reprocess: ${err.message}`);
    } finally {
      setReprocessing(false);
    }
  };

  // Handle Delete
  const handleDelete = async () => {
    if (!window.confirm('Are you sure you want to delete this document and all its chunks?')) return;
    try {
      await api.deleteDocument(documentId);
      onBack();
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

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-16 flex flex-col items-center justify-center text-slate-400">
        <Loader2 className="w-8 h-8 animate-spin text-indigo-600 mb-3" />
        <p className="text-sm font-medium">Loading document details...</p>
      </div>
    );
  }

  if (error || !document) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-12">
        <button
          onClick={onBack}
          className="inline-flex items-center gap-2 text-sm font-semibold text-slate-600 hover:text-slate-900 mb-6"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Back to Library</span>
        </button>
        <div className="p-6 rounded-2xl bg-rose-50 border border-rose-200 text-rose-700 flex items-center gap-3">
          <AlertCircle className="w-6 h-6 shrink-0" />
          <span>{error || 'Document not found'}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Top Navigation */}
      <div className="flex items-center justify-between mb-6">
        <button
          onClick={onBack}
          className="inline-flex items-center gap-2 text-sm font-semibold text-slate-600 hover:text-slate-900 px-3 py-1.5 rounded-xl hover:bg-slate-100 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Back to Library</span>
        </button>

        <div className="flex items-center gap-2">
          <button
            onClick={handleReprocess}
            disabled={reprocessing}
            title="Reprocess chunks and embeddings"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:text-indigo-600 hover:bg-indigo-50 border border-slate-200 rounded-xl transition-all"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${reprocessing ? 'animate-spin' : ''}`} />
            <span>Reprocess</span>
          </button>
          <button
            onClick={handleDelete}
            title="Delete Document"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-rose-600 hover:bg-rose-50 border border-rose-200 rounded-xl transition-all"
          >
            <Trash2 className="w-3.5 h-3.5" />
            <span>Delete</span>
          </button>
        </div>
      </div>

      {/* Main Document Card */}
      <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm p-6 sm:p-8 mb-6">
        {/* Header row */}
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
          <div className="flex items-center gap-2.5">
            <div className="p-2.5 bg-slate-50 rounded-xl">
              {getSourceIcon(document.source_type)}
            </div>
            <span className="text-xs font-bold uppercase tracking-wider text-slate-500 bg-slate-100 px-2.5 py-1 rounded-md">
              {document.source_type}
            </span>
            {document.category && (
              <span className="text-xs font-medium text-indigo-700 bg-indigo-50 px-2.5 py-1 rounded-md">
                {document.category}
              </span>
            )}
          </div>
          <StatusBadge status={document.status} />
        </div>

        {/* Title */}
        <h1 className="text-2xl font-bold text-slate-900 tracking-tight mb-4">
          {document.title || 'Untitled Document'}
        </h1>

        {/* Metadata Details Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 py-4 border-y border-slate-100 text-xs">
          <div>
            <span className="text-slate-400 block mb-0.5">Created</span>
            <span className="font-semibold text-slate-700 flex items-center gap-1">
              <Calendar className="w-3.5 h-3.5 text-slate-400" />
              {new Date(document.created_at).toLocaleDateString()}
            </span>
          </div>
          <div>
            <span className="text-slate-400 block mb-0.5">Chunks</span>
            <span className="font-semibold text-slate-700 flex items-center gap-1">
              <Layers className="w-3.5 h-3.5 text-slate-400" />
              {document.chunk_count || document.chunks?.length || 0} chunks
            </span>
          </div>
          <div>
            <span className="text-slate-400 block mb-0.5">SHA256 Hash</span>
            <span className="font-mono text-slate-700 truncate block" title={document.sha256}>
              {document.sha256 ? `${document.sha256.slice(0, 10)}...` : 'N/A'}
            </span>
          </div>
          <div>
            <span className="text-slate-400 block mb-0.5">Source URI</span>
            <span className="font-medium text-slate-700 truncate block" title={document.source_url || document.file_path}>
              {document.source_url || document.file_path || 'Direct note'}
            </span>
          </div>
        </div>

        {/* AI Summary Section */}
        {document.summary ? (
          <div className="mt-6 p-5 rounded-2xl bg-indigo-50/40 border border-indigo-100/80">
            <div className="flex items-center gap-2 mb-2">
              <Sparkles className="w-4 h-4 text-indigo-600" />
              <h3 className="text-xs font-bold text-indigo-900 uppercase tracking-wider">
                AI Executive Summary
              </h3>
            </div>
            <p className="text-sm text-slate-700 leading-relaxed">
              {document.summary}
            </p>
          </div>
        ) : (
          <div className="mt-6 p-4 rounded-xl bg-slate-50 border border-slate-100 text-xs text-slate-500">
            AI Summary not yet generated for this document.
          </div>
        )}

        {/* Tags Section */}
        <div className="mt-6">
          <div className="flex items-center gap-2 mb-3">
            <TagIcon className="w-4 h-4 text-slate-400" />
            <h3 className="text-xs font-bold text-slate-700 uppercase tracking-wider">
              Document Tags
            </h3>
          </div>

          <div className="flex flex-wrap items-center gap-2 mb-3">
            {document.tags && document.tags.length > 0 ? (
              document.tags.map((t) => (
                <span
                  key={t.id || t.name}
                  className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-indigo-50 text-indigo-700 border border-indigo-100"
                >
                  <span>#{t.name}</span>
                  <button
                    onClick={() => handleRemoveTag(t.id)}
                    className="hover:text-rose-600 transition-colors"
                    title="Remove tag"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </span>
              ))
            ) : (
              <span className="text-xs text-slate-400 italic">No tags assigned.</span>
            )}
          </div>

          <form onSubmit={handleAddTag} className="flex gap-2 max-w-xs">
            <input
              type="text"
              value={newTagName}
              onChange={(e) => setNewTagName(e.target.value)}
              placeholder="Add tag (e.g. ai, q3)..."
              className="px-3 py-1.5 text-xs border border-slate-200 rounded-xl bg-slate-50/50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 flex-1"
            />
            <button
              type="submit"
              disabled={tagLoading || !newTagName.trim()}
              className="inline-flex items-center gap-1 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-xs font-semibold rounded-xl shadow-sm transition-all"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Add</span>
            </button>
          </form>
        </div>
      </div>

      {/* Related Documents Section */}
      <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm p-6 sm:p-8">
        <div className="flex items-center gap-2 mb-4">
          <BookOpen className="w-4 h-4 text-indigo-600" />
          <h2 className="text-base font-bold text-slate-900 tracking-tight">
            Related Documents (Centroid Similarity)
          </h2>
        </div>

        {relatedDocs.length === 0 ? (
          <p className="text-xs text-slate-500 italic">
            No related documents found with high cosine similarity, or document has not finished embedding.
          </p>
        ) : (
          <div className="space-y-3">
            {relatedDocs.map((item) => {
              const relatedId = item.document_id ?? item.id;
              const sim = item.similarity ?? item.similarity_score;
              return (
              <div
                key={relatedId}
                onClick={() => onSelectDocument(relatedId)}
                className="group flex items-center justify-between p-3.5 rounded-xl border border-slate-100 hover:border-indigo-200 hover:bg-indigo-50/30 transition-all cursor-pointer"
              >
                <div className="flex items-center gap-3">
                  <div className="p-2 bg-slate-50 rounded-lg group-hover:bg-white transition-colors">
                    {getSourceIcon(item.source_type)}
                  </div>
                  <div>
                    <h4 className="text-sm font-semibold text-slate-800 group-hover:text-indigo-600 transition-colors line-clamp-1">
                      {item.title || 'Untitled Document'}
                    </h4>
                    <span className="text-[11px] text-slate-400 capitalize">
                      {item.source_type} • {item.category || 'General'}
                    </span>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  {sim !== undefined && sim !== null && (
                    <span className="text-xs font-bold text-indigo-700 bg-indigo-50 px-2.5 py-1 rounded-full border border-indigo-100">
                      {(sim * 100).toFixed(0)}% match
                    </span>
                  )}
                  <ExternalLink className="w-4 h-4 text-slate-300 group-hover:text-indigo-600 transition-colors" />
                </div>
              </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
