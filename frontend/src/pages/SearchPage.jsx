import React, { useState } from 'react';
import { 
  Search, SlidersHorizontal, Sparkles, FileText, Globe, 
  Edit3, ArrowRight, Loader2, AlertCircle, ExternalLink 
} from 'lucide-react';
import { api } from '../api/client';

export default function SearchPage({ onSelectDocument, onOpenCitation }) {
  const [query, setQuery] = useState('');
  const [mode, setMode] = useState('hybrid'); // 'hybrid' | 'semantic' | 'keyword'
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [error, setError] = useState(null);

  const handleSearch = async (e) => {
    if (e) e.preventDefault();
    if (!query.trim()) return;

    setLoading(true);
    setError(null);
    setHasSearched(true);

    try {
      const data = await api.search(query.trim(), mode, 60, 15);
      setResults(data?.results || []);
    } catch (err) {
      setError(err.message || 'Search execution failed');
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  const getSourceIcon = (type) => {
    switch (type) {
      case 'pdf':
        return <FileText className="w-4 h-4 text-rose-500" />;
      case 'link':
        return <Globe className="w-4 h-4 text-sky-500" />;
      case 'note':
      default:
        return <Edit3 className="w-4 h-4 text-indigo-500" />;
    }
  };

  const formatScore = (score, currentMode) => {
    if (score === undefined || score === null) return null;
    if (currentMode === 'hybrid') {
      return `RRF Score: ${score.toFixed(4)}`;
    } else if (currentMode === 'semantic') {
      return `Similarity: ${(score * 100).toFixed(1)}%`;
    } else {
      return `Rank Score: ${score.toFixed(2)}`;
    }
  };

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
          Retrieval Search
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Explore your indexed chunks using Hybrid RRF (pgvector + full-text), Semantic cosine, or Keyword search.
        </p>
      </div>

      {/* Search Bar & Mode Selector */}
      <div className="bg-white p-4 rounded-2xl border border-slate-200/80 shadow-sm mb-6 space-y-4">
        <form onSubmit={handleSearch} className="flex gap-2">
          <div className="relative flex-1">
            <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
              <Search className="w-5 h-5" />
            </div>
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search concepts, quotes, topics, or exact keywords..."
              className="w-full pl-11 pr-4 py-3 text-sm border border-slate-200 rounded-xl bg-slate-50/50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-colors"
            />
          </div>
          <button
            type="submit"
            disabled={loading || !query.trim()}
            className="inline-flex items-center gap-2 px-6 py-3 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white font-semibold text-sm rounded-xl shadow-sm transition-all"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
            <span className="hidden sm:inline">Search</span>
          </button>
        </form>

        {/* Mode Selector Toggle */}
        <div className="flex items-center gap-2 pt-2 border-t border-slate-100">
          <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-1.5 mr-1">
            <SlidersHorizontal className="w-3.5 h-3.5" />
            <span>Mode:</span>
          </span>
          <div className="flex bg-slate-100 p-1 rounded-xl">
            <button
              type="button"
              onClick={() => {
                setMode('hybrid');
                if (hasSearched && query.trim()) {
                  api.search(query.trim(), 'hybrid', 60, 15).then((d) => setResults(d?.results || []));
                }
              }}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-1.5 ${
                mode === 'hybrid'
                  ? 'bg-white text-indigo-700 shadow-sm'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <Sparkles className="w-3.5 h-3.5 text-indigo-600" />
              <span>Hybrid (RRF)</span>
            </button>

            <button
              type="button"
              onClick={() => {
                setMode('semantic');
                if (hasSearched && query.trim()) {
                  api.search(query.trim(), 'semantic', 60, 15).then((d) => setResults(d?.results || []));
                }
              }}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                mode === 'semantic'
                  ? 'bg-white text-indigo-700 shadow-sm'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Semantic Vector
            </button>

            <button
              type="button"
              onClick={() => {
                setMode('keyword');
                if (hasSearched && query.trim()) {
                  api.search(query.trim(), 'keyword', 60, 15).then((d) => setResults(d?.results || []));
                }
              }}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                mode === 'keyword'
                  ? 'bg-white text-indigo-700 shadow-sm'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Keyword (BM25/tsvector)
            </button>
          </div>
        </div>
      </div>

      {/* Error state */}
      {error && (
        <div className="mb-6 p-4 rounded-xl bg-rose-50 border border-rose-200 flex items-center gap-3 text-rose-700 text-sm">
          <AlertCircle className="w-5 h-5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Search Results */}
      {loading ? (
        <div className="flex flex-col items-center justify-center py-16 text-slate-400">
          <Loader2 className="w-8 h-8 animate-spin text-indigo-600 mb-3" />
          <p className="text-sm font-medium">Searching chunks with {mode} retrieval...</p>
        </div>
      ) : hasSearched && results.length === 0 ? (
        <div className="bg-white rounded-2xl border border-dashed border-slate-200 p-12 text-center max-w-lg mx-auto">
          <p className="text-base font-semibold text-slate-800 mb-1">
            No matching chunks found
          </p>
          <p className="text-xs text-slate-500">
            Try adjusting your query, switching to Hybrid or Semantic mode, or verifying that your documents have finished processing.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {results.map((result, idx) => (
            <div
              key={result.chunk_id || idx}
              className="bg-white rounded-2xl border border-slate-200/80 p-5 shadow-sm hover:shadow-md hover:border-indigo-200 transition-all"
            >
              <div className="flex items-start justify-between gap-3 mb-2">
                <div className="flex items-center gap-2">
                  <span className="w-6 h-6 rounded-lg bg-indigo-50 text-indigo-700 font-bold text-xs flex items-center justify-center">
                    #{idx + 1}
                  </span>
                  <div className="p-1.5 bg-slate-50 rounded-lg">
                    {getSourceIcon(result.source_type)}
                  </div>
                  <button
                    onClick={() => onSelectDocument && onSelectDocument(result.document_id)}
                    className="font-semibold text-slate-900 hover:text-indigo-600 text-sm sm:text-base transition-colors text-left line-clamp-1"
                  >
                    {result.document_title || 'Untitled Document'}
                  </button>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  {result.page_number && (
                    <span className="text-[11px] font-medium text-slate-500 bg-slate-100 px-2 py-0.5 rounded">
                      Page {result.page_number}
                    </span>
                  )}
                  {result.score !== undefined && (
                    <span className="text-[11px] font-semibold text-indigo-700 bg-indigo-50 px-2.5 py-0.5 rounded-full border border-indigo-100">
                      {formatScore(result.score, mode)}
                    </span>
                  )}
                </div>
              </div>

              {/* Chunk Snippet */}
              <div className="mt-3 p-3.5 bg-slate-50/70 rounded-xl border border-slate-100 text-xs sm:text-sm text-slate-700 leading-relaxed font-mono whitespace-pre-wrap">
                {result.content || result.snippet}
              </div>

              {/* Bottom Actions */}
              <div className="mt-3 flex items-center justify-between text-xs text-slate-400">
                <span className="text-[11px]">Chunk #{result.chunk_id}</span>
                <div className="flex items-center gap-3">
                  {onOpenCitation && (
                    <button
                      onClick={() => onOpenCitation({
                        chunk_id: result.chunk_id,
                        document_id: result.document_id,
                        document_title: result.document_title,
                        source_type: result.source_type,
                        page_number: result.page_number,
                        snippet: result.content || result.snippet,
                      })}
                      className="text-xs font-medium text-indigo-600 hover:text-indigo-800 transition-colors"
                    >
                      View Source
                    </button>
                  )}
                  {onSelectDocument && (
                    <button
                      onClick={() => onSelectDocument(result.document_id)}
                      className="inline-flex items-center gap-1 text-xs font-medium text-slate-600 hover:text-slate-900 transition-colors"
                    >
                      <span>Open Document</span>
                      <ExternalLink className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
