import React, { useState } from 'react';
import { 
  MessageSquare, Send, Copy, Check, BookOpen, Sparkles, 
  Loader2, AlertCircle, Trash2, ArrowUpRight 
} from 'lucide-react';
import { api } from '../api/client';

export default function AskPage({ onOpenCitation, onSelectDocument }) {
  const [question, setQuestion] = useState('');
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [copiedIndex, setCopiedIndex] = useState(null);

  const handleAsk = async (e) => {
    e.preventDefault();
    if (!question.trim()) return;

    const currentQuestion = question.trim();
    setQuestion('');
    setError(null);
    setLoading(true);

    try {
      const data = await api.ask(currentQuestion, null, 5);
      
      const newEntry = {
        question: currentQuestion,
        answer: data.answer,
        citations: data.citations || [],
        confidence: data.confidence,
        timestamp: new Date().toISOString(),
      };

      setHistory((prev) => [newEntry, ...prev]);
    } catch (err) {
      setError(err.message || 'Failed to generate cited answer');
    } finally {
      setLoading(false);
    }
  };

  const copyToClipboard = (text, index) => {
    navigator.clipboard.writeText(text);
    setCopiedIndex(index);
    setTimeout(() => setCopiedIndex(null), 2000);
  };

  /**
   * Render answer text and turn [Chunk 123] or [123] patterns into clickable citation badges
   */
  const renderFormattedAnswer = (answer, citations) => {
    if (!answer) return null;

    // Build a lookup map of chunk_id -> citation
    const citationMap = new Map();
    citations.forEach((c) => {
      citationMap.set(Number(c.chunk_id), c);
      citationMap.set(String(c.chunk_id), c);
    });

    // Match [Chunk 123] or [123]
    const regex = /\[(?:Chunk\s*)?(\d+)\]/gi;
    const parts = [];
    let lastIndex = 0;
    let match;

    while ((match = regex.exec(answer)) !== null) {
      const matchStart = match.index;
      const matchEnd = regex.lastIndex;
      const chunkId = match[1];

      // Text before match
      if (matchStart > lastIndex) {
        parts.push(answer.substring(lastIndex, matchStart));
      }

      const citation = citationMap.get(Number(chunkId)) || citationMap.get(chunkId);

      // Render clickable citation badge
      parts.push(
        <button
          key={`${chunkId}-${matchStart}`}
          onClick={() => {
            if (citation && onOpenCitation) {
              onOpenCitation(citation);
            }
          }}
          title={citation ? `${citation.document_title || 'Document'} (Page ${citation.page_number || 1})` : `Chunk ${chunkId}`}
          className="inline-flex items-center px-1.5 py-0.5 mx-1 my-0.5 rounded-md text-xs font-semibold bg-indigo-100 text-indigo-700 hover:bg-indigo-200 border border-indigo-200 transition-colors cursor-pointer"
        >
          <span>[{citation ? `${citation.document_title?.slice(0, 15) || 'Chunk'} #${chunkId}` : `Chunk #${chunkId}`}]</span>
        </button>
      );

      lastIndex = matchEnd;
    }

    if (lastIndex < answer.length) {
      parts.push(answer.substring(lastIndex));
    }

    return (
      <div className="text-slate-800 text-sm leading-relaxed whitespace-pre-wrap">
        {parts}
      </div>
    );
  };

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <span>Cited Q&A</span>
            <span className="p-1 bg-indigo-50 text-indigo-600 rounded-lg">
              <Sparkles className="w-4 h-4" />
            </span>
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Ask questions strictly grounded in your library. Every statement links to verifiable source chunks.
          </p>
        </div>

        {history.length > 0 && (
          <button
            onClick={() => setHistory([])}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-500 hover:text-rose-600 hover:bg-rose-50 rounded-xl transition-colors"
          >
            <Trash2 className="w-3.5 h-3.5" />
            <span>Clear History</span>
          </button>
        )}
      </div>

      {/* Input Box */}
      <div className="bg-white p-4 rounded-2xl border border-slate-200/80 shadow-sm mb-8">
        <form onSubmit={handleAsk} className="flex gap-2">
          <div className="relative flex-1">
            <input
              type="text"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="e.g. What were the core findings in our Q3 analysis report?"
              className="w-full pl-4 pr-4 py-3 text-sm border border-slate-200 rounded-xl bg-slate-50/50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-colors"
            />
          </div>
          <button
            type="submit"
            disabled={loading || !question.trim()}
            className="inline-flex items-center gap-2 px-6 py-3 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white font-semibold text-sm rounded-xl shadow-sm transition-all"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
            <span className="hidden sm:inline">Ask AI</span>
          </button>
        </form>
      </div>

      {/* Error state */}
      {error && (
        <div className="mb-6 p-4 rounded-xl bg-rose-50 border border-rose-200 flex items-center gap-3 text-rose-700 text-sm">
          <AlertCircle className="w-5 h-5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* In-Flight Spinner */}
      {loading && (
        <div className="bg-white rounded-2xl border border-slate-200/80 p-6 shadow-sm mb-6 animate-pulse">
          <div className="flex items-center gap-2 text-indigo-600 mb-3">
            <Loader2 className="w-4 h-4 animate-spin" />
            <span className="text-xs font-semibold uppercase tracking-wider">
              Retrieving relevant chunks & formulating grounded response...
            </span>
          </div>
          <div className="space-y-2">
            <div className="h-4 bg-slate-100 rounded w-3/4"></div>
            <div className="h-4 bg-slate-100 rounded w-full"></div>
            <div className="h-4 bg-slate-100 rounded w-5/6"></div>
          </div>
        </div>
      )}

      {/* Q&A Stream */}
      {history.length === 0 && !loading ? (
        <div className="bg-white rounded-2xl border border-dashed border-slate-200 p-12 text-center max-w-lg mx-auto">
          <div className="w-12 h-12 rounded-2xl bg-indigo-50 text-indigo-600 flex items-center justify-center mx-auto mb-4">
            <MessageSquare className="w-6 h-6" />
          </div>
          <h3 className="text-base font-semibold text-slate-800 mb-1">
            Ask your documents anything
          </h3>
          <p className="text-xs text-slate-500 leading-relaxed">
            RecallBox synthesizes answers solely from retrieved evidence in your library. If an answer cannot be grounded, the engine explicitly declines to answer to avoid hallucinations.
          </p>
        </div>
      ) : (
        <div className="space-y-6">
          {history.map((item, idx) => (
            <div
              key={idx}
              className="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden"
            >
              {/* Question Banner */}
              <div className="px-6 py-4 bg-slate-50/70 border-b border-slate-100 flex items-start justify-between gap-4">
                <div className="flex items-start gap-3">
                  <span className="p-1.5 bg-indigo-600 text-white rounded-lg mt-0.5">
                    <MessageSquare className="w-3.5 h-3.5" />
                  </span>
                  <div>
                    <h3 className="text-sm sm:text-base font-semibold text-slate-900">
                      {item.question}
                    </h3>
                    <span className="text-[11px] text-slate-400">
                      {new Date(item.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>
                </div>

                <button
                  onClick={() => copyToClipboard(item.answer, idx)}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-500 hover:text-slate-800 hover:bg-slate-100 rounded-lg transition-colors shrink-0"
                  title="Copy answer"
                >
                  {copiedIndex === idx ? (
                    <>
                      <Check className="w-3.5 h-3.5 text-emerald-600" />
                      <span className="text-emerald-600">Copied!</span>
                    </>
                  ) : (
                    <>
                      <Copy className="w-3.5 h-3.5" />
                      <span>Copy</span>
                    </>
                  )}
                </button>
              </div>

              {/* Answer Body */}
              <div className="p-6">
                {renderFormattedAnswer(item.answer, item.citations)}

                {/* Grounding Source Cards */}
                {item.citations && item.citations.length > 0 && (
                  <div className="mt-6 pt-5 border-t border-slate-100">
                    <div className="flex items-center gap-2 mb-3">
                      <BookOpen className="w-3.5 h-3.5 text-slate-400" />
                      <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                        Cited Evidence ({item.citations.length})
                      </span>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      {item.citations.map((c) => (
                        <div
                          key={c.chunk_id}
                          onClick={() => onOpenCitation && onOpenCitation(c)}
                          className="group p-3 bg-slate-50 hover:bg-indigo-50/40 rounded-xl border border-slate-200/70 hover:border-indigo-200 transition-all cursor-pointer"
                        >
                          <div className="flex items-center justify-between text-xs mb-1.5">
                            <span className="font-semibold text-indigo-700">
                              Chunk #{c.chunk_id}
                            </span>
                            {c.page_number && (
                              <span className="text-[10px] bg-slate-200/60 px-1.5 py-0.5 rounded text-slate-600">
                                Page {c.page_number}
                              </span>
                            )}
                          </div>
                          <p className="text-xs font-medium text-slate-800 line-clamp-1 mb-1">
                            {c.document_title || 'Document'}
                          </p>
                          <p className="text-[11px] text-slate-500 line-clamp-2 italic font-mono">
                            "{c.snippet}"
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
