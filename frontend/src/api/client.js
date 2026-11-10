const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

class ApiClient {
  constructor() {
    this.token = localStorage.getItem('recallbox_token') || null;
  }

  setToken(token) {
    this.token = token;
    if (token) {
      localStorage.setItem('recallbox_token', token);
    } else {
      localStorage.removeItem('recallbox_token');
    }
  }

  getToken() {
    return this.token;
  }

  logout() {
    this.setToken(null);
  }

  async request(endpoint, options = {}) {
    const headers = options.headers || {};

    if (this.token && !headers['Authorization']) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }

    if (!(options.body instanceof FormData) && !headers['Content-Type']) {
      headers['Content-Type'] = 'application/json';
    }

    const config = {
      ...options,
      headers,
    };

    const url = `${BASE_URL}${endpoint}`;
    const response = await fetch(url, config);

    if (response.status === 401) {
      this.logout();
      window.dispatchEvent(new CustomEvent('auth:unauthorized'));
    }

    if (response.status === 204) {
      return null;
    }

    let data;
    try {
      data = await response.json();
    } catch {
      data = null;
    }

    if (!response.ok) {
      const errorMsg = data?.detail || data?.message || `HTTP error ${response.status}`;
      throw new Error(typeof errorMsg === 'string' ? errorMsg : JSON.stringify(errorMsg));
    }

    return data;
  }

  // Auth Endpoints
  async register(email, password) {
    return this.request('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
  }

  async login(email, password) {
    const data = await this.request('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
    if (data?.access_token) {
      this.setToken(data.access_token);
    }
    return data;
  }

  async getMe() {
    return this.request('/auth/me');
  }

  // Document Intake Endpoints
  async uploadPDF(file, title, category) {
    const formData = new FormData();
    formData.append('file', file);
    if (title) formData.append('title', title);
    if (category) formData.append('category', category);

    return this.request('/documents/upload', {
      method: 'POST',
      body: formData,
    });
  }

  async createLink(url, title, category) {
    return this.request('/documents/link', {
      method: 'POST',
      body: JSON.stringify({ url, title, category }),
    });
  }

  async createNote(title, content, category) {
    return this.request('/documents/note', {
      method: 'POST',
      body: JSON.stringify({ title, content, category }),
    });
  }

  // Document Library & Management
  async getDocuments(params = {}) {
    const searchParams = new URLSearchParams();
    if (params.page) searchParams.set('page', params.page);
    if (params.limit) searchParams.set('limit', params.limit);
    if (params.status) searchParams.set('status', params.status);
    if (params.category) searchParams.set('category', params.category);
    if (params.tag) searchParams.set('tag', params.tag);
    if (params.source_type) searchParams.set('source_type', params.source_type);

    const qs = searchParams.toString();
    return this.request(`/documents${qs ? `?${qs}` : ''}`);
  }

  async getDocument(id) {
    return this.request(`/documents/${id}`);
  }

  async deleteDocument(id) {
    return this.request(`/documents/${id}`, {
      method: 'DELETE',
    });
  }

  async reprocessDocument(id) {
    return this.request(`/documents/${id}/reprocess`, {
      method: 'POST',
    });
  }

  // Search & Q&A
  async search(query, mode = 'hybrid', k = 60, limit = 10, documentIds = null) {
    const searchParams = new URLSearchParams({
      q: query,
      mode,
      k: k.toString(),
      limit: limit.toString(),
    });

    if (documentIds && documentIds.length > 0) {
      documentIds.forEach(id => searchParams.append('document_ids', id));
    }

    return this.request(`/search?${searchParams.toString()}`);
  }

  async ask(question, documentIds = null, topK = 5) {
    const payload = {
      question,
      top_k: topK,
    };
    if (documentIds && documentIds.length > 0) {
      payload.document_ids = documentIds;
    }
    return this.request('/ask', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  // Tags & Related
  async getTags() {
    return this.request('/tags');
  }

  async addTag(documentId, name) {
    return this.request(`/documents/${documentId}/tags`, {
      method: 'POST',
      body: JSON.stringify({ name }),
    });
  }

  async removeTag(documentId, tagId) {
    return this.request(`/documents/${documentId}/tags/${tagId}`, {
      method: 'DELETE',
    });
  }

  async getRelatedDocuments(documentId, limit = 5) {
    return this.request(`/documents/${documentId}/related?limit=${limit}`);
  }
}

export const api = new ApiClient();
