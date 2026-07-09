import axios from 'axios';

export const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
});

// ---------------------------------------------------------------------------
// Business Outcomes
// ---------------------------------------------------------------------------
export const businessOutcomesApi = {
  list: (params) => api.get('/business-outcomes', { params }),
  create: (payload) => api.post('/business-outcomes', payload),
  update: (id, payload) => api.put(`/business-outcomes/${id}`, payload),
  remove: (id) => api.delete(`/business-outcomes/${id}`),
};

// ---------------------------------------------------------------------------
// L1 Metrics
// ---------------------------------------------------------------------------
export const l1MetricsApi = {
  list: (params) => api.get('/l1-metrics', { params }),
  create: (payload) => api.post('/l1-metrics', payload),
  update: (id, payload) => api.put(`/l1-metrics/${id}`, payload),
  remove: (id) => api.delete(`/l1-metrics/${id}`),
};

// ---------------------------------------------------------------------------
// L2 Metrics
// ---------------------------------------------------------------------------
export const l2MetricsApi = {
  list: (params) => api.get('/l2-metrics', { params }),
  create: (payload) => api.post('/l2-metrics', payload),
  update: (id, payload) => api.put(`/l2-metrics/${id}`, payload),
  remove: (id) => api.delete(`/l2-metrics/${id}`),
};

// ---------------------------------------------------------------------------
// Interventions
// ---------------------------------------------------------------------------
export const interventionsApi = {
  list: (params) => api.get('/interventions', { params }),
  create: (payload) => api.post('/interventions', payload),
  update: (id, payload) => api.put(`/interventions/${id}`, payload),
  remove: (id) => api.delete(`/interventions/${id}`),
};

// ---------------------------------------------------------------------------
// Excel Upload
// ---------------------------------------------------------------------------
export const uploadExcel = (file) => {
  const formData = new FormData();
  formData.append('file', file);
  return api.post('/upload-excel', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
};

// ---------------------------------------------------------------------------
// Simulation / filters
// ---------------------------------------------------------------------------
export const simulationApi = {
  snapshot: (params) => api.get('/simulation/snapshot', { params }),
  reset: () => api.post('/simulation/reset'),
};

export const filtersApi = {
  verticals: () => api.get('/filters/verticals'),
  lobs: (params) => api.get('/filters/lobs', { params }),
};

// ---------------------------------------------------------------------------
// Structure & Access Control: Mapping (Verticals / LOBs)
// ---------------------------------------------------------------------------
export const structureApi = {
  listVerticalsDetailed: () => api.get('/verticals/detailed'),
  createVertical: (payload) => api.post('/verticals', payload),
  updateVertical: (id, payload) => api.put(`/verticals/${id}`, payload),
  deleteVertical: (id) => api.delete(`/verticals/${id}`),
  addLob: (verticalId, payload) => api.post(`/verticals/${verticalId}/lobs`, payload),
  updateLob: (lobId, payload) => api.put(`/lobs/${lobId}`, payload),
  deleteLob: (lobId) => api.delete(`/lobs/${lobId}`),
};

// ---------------------------------------------------------------------------
// Structure & Access Control: User Onboarding
// ---------------------------------------------------------------------------
export const usersApi = {
  roster: () => api.get('/users/roster'),
  list: () => api.get('/users'),
  create: (payload) => api.post('/users', payload),
  update: (id, payload) => api.put(`/users/${id}`, payload),
  remove: (id) => api.delete(`/users/${id}`),
};
