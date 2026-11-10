import React, { useState, useEffect } from 'react';
import { api } from './api/client';
import Navbar from './components/Navbar';
import CitationModal from './components/CitationModal';
import AuthPage from './pages/AuthPage';
import LibraryPage from './pages/LibraryPage';
import AddPage from './pages/AddPage';
import SearchPage from './pages/SearchPage';
import AskPage from './pages/AskPage';
import DocumentDetailPage from './pages/DocumentDetailPage';
import { Loader2 } from 'lucide-react';

export default function App() {
  const [currentUser, setCurrentUser] = useState(null);
  const [loadingInitial, setLoadingInitial] = useState(true);
  const [activeTab, setActiveTab] = useState('library'); // 'library' | 'add' | 'search' | 'ask' | 'detail'
  const [selectedDocumentId, setSelectedDocumentId] = useState(null);
  const [activeCitation, setActiveCitation] = useState(null);

  // Check auth session on startup
  useEffect(() => {
    const checkAuth = async () => {
      const token = api.getToken();
      if (!token) {
        setLoadingInitial(false);
        return;
      }
      try {
        const user = await api.getMe();
        setCurrentUser(user);
      } catch {
        api.logout();
        setCurrentUser(null);
      } finally {
        setLoadingInitial(false);
      }
    };

    checkAuth();

    const handleUnauthorized = () => {
      setCurrentUser(null);
    };

    window.addEventListener('auth:unauthorized', handleUnauthorized);
    return () => {
      window.removeEventListener('auth:unauthorized', handleUnauthorized);
    };
  }, []);

  const handleLoginSuccess = (user) => {
    setCurrentUser(user);
    setActiveTab('library');
  };

  const handleLogout = () => {
    api.logout();
    setCurrentUser(null);
    setActiveTab('library');
    setSelectedDocumentId(null);
  };

  const handleSelectDocument = (docId) => {
    setSelectedDocumentId(docId);
    setActiveTab('detail');
  };

  const handleBackToLibrary = () => {
    setSelectedDocumentId(null);
    setActiveTab('library');
  };

  if (loadingInitial) {
    return (
      <div className="min-h-screen bg-slate-50 flex flex-col items-center justify-center text-slate-400">
        <Loader2 className="w-10 h-10 animate-spin text-indigo-600 mb-4" />
        <p className="text-sm font-semibold text-slate-600">Initializing RecallBox...</p>
      </div>
    );
  }

  if (!currentUser) {
    return <AuthPage onLoginSuccess={handleLoginSuccess} />;
  }

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col selection:bg-indigo-500 selection:text-white">
      {/* Top Navigation */}
      <Navbar
        activeTab={activeTab === 'detail' ? 'library' : activeTab}
        onSelectTab={(tab) => {
          setSelectedDocumentId(null);
          setActiveTab(tab);
        }}
        currentUser={currentUser}
        onLogout={handleLogout}
      />

      {/* Main Content Area */}
      <main className="flex-1 pb-16">
        {activeTab === 'library' && (
          <LibraryPage
            onSelectDocument={handleSelectDocument}
            onNavigateAdd={() => setActiveTab('add')}
          />
        )}

        {activeTab === 'add' && (
          <AddPage
            onNavigateLibrary={() => setActiveTab('library')}
          />
        )}

        {activeTab === 'search' && (
          <SearchPage
            onSelectDocument={handleSelectDocument}
            onOpenCitation={(citation) => setActiveCitation(citation)}
          />
        )}

        {activeTab === 'ask' && (
          <AskPage
            onOpenCitation={(citation) => setActiveCitation(citation)}
            onSelectDocument={handleSelectDocument}
          />
        )}

        {activeTab === 'detail' && selectedDocumentId && (
          <DocumentDetailPage
            documentId={selectedDocumentId}
            onBack={handleBackToLibrary}
            onSelectDocument={handleSelectDocument}
          />
        )}
      </main>

      {/* Global Citation Inspection Modal */}
      <CitationModal
        citation={activeCitation}
        onClose={() => setActiveCitation(null)}
        onOpenDocument={(docId) => {
          setActiveCitation(null);
          handleSelectDocument(docId);
        }}
      />
    </div>
  );
}
